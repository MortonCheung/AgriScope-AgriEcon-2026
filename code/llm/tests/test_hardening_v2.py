"""Behavioral regression checks use fake transport, never fake capability metrics."""
from __future__ import annotations

import copy
import json
import types
import numpy as np
import pandas as pd
import pytest

from llm.common import canonical_json
from llm.context import build_case_context, build_blind_packet, build_packet, restore_forecast, packet_hash, audit_packet
from llm.evaluation.harness import ExperimentConfig, _call_once, stability_test, learn_max_adjustment
from llm.evaluation.v2 import (PilotConfig, BudgetedProvider, prepared_target, learn_baseline,
                              learn_adjustment_bounds, run_v2_experiment, hybrid_evaluation)
from llm.providers import LLMProvider, LLMUnavailable, OpenAICompatProvider, StubProvider
from llm.schemas import hard_bounds, validate_forecast, validate_residual
from llm.cache import store


@pytest.fixture
def history():
    dates = pd.date_range("2021-01-01", "2024-12-31", freq="D")
    t = np.arange(len(dates))
    return pd.DataFrame({"date": dates, "crop": "土豆", "price_per_kg": 4 + .002*t + .2*np.sin(t/20)})


@pytest.fixture(autouse=True)
def isolated_cache(tmp_path, monkeypatch):
    cache = tmp_path / "cache"
    cache.mkdir()
    monkeypatch.setattr(store, "LLM_CACHE", cache)
    monkeypatch.setattr(store, "ensure_llm_dirs", lambda: None)


class CountingProvider(LLMProvider):
    name, model, is_real_llm, seed_supported = "fake_transport_only", "schema_fixture", True, True
    def __init__(self, invalid=False, config="first"):
        self.calls, self.requests, self.invalid, self.config = 0, [], invalid, config
    def cache_config(self):
        return {**self.describe(), "endpoint_config": self.config}
    def complete_json(self, **kwargs):
        self.calls += 1
        self.requests.append(kwargs)
        context = kwargs["context"]
        binding = {"method": context["method"], "context_hash": context["context_hash"]}
        if kwargs["schema_name"] == "residual":
            return {**binding, "adjustment_pct": 5., "confidence": .5, "rationale": "fixture"}
        value = context["current_price"] * (1 + self.calls/1000)
        if self.invalid:
            binding["context_hash"] = "different_packet"
        return {**binding, "forecast_horizon": context["horizon"], "point_forecast": value,
                "range_low": value*.9, "range_high": value*1.1, "direction": "up",
                "confidence": .5, "drivers": [], "downside_risks": [], "assumptions": [],
                "uncertainty": "fixture", "unit": context["unit"]}


def test_blind_is_anonymous_normalized_and_reversible(history):
    packet, host = build_case_context("土豆", "2023-06-01", 90, mode="blind", dataset=history,
                                      config={"private_path": "/沈阳/土豆/2023-06-01"})
    text = canonical_json(packet)
    for prohibited in ("沈阳", "土豆", "shenyang", "2023-06-01", "private_path", "scale"):
        assert prohibited not in text
    assert packet["current_price"] == 1
    assert packet["unit"] == "ratio_to_current_price"
    assert packet["seasonality"]["historical_profile"].keys() <= {f"M-{n}" for n in range(12)}
    raw = build_packet("土豆", "2023-06-01", 90, dataset=history)
    # 压缩后逐日明细只保留最近 N 个观测，且必须是宿主 cutoff 切片的**尾部**逐值相等。
    assert len(packet["history_recent"]) <= len(raw["history_recent"])
    assert np.allclose([x["price"]*host["scale"] for x in packet["history_recent"]],
                       [x["price"] for x in raw["history_recent"]])
    assert [x["month_offset"] for x in packet["history_monthly"]] == \
           [x["month_offset"] for x in raw["history_monthly"]]
    assert np.allclose([x["mean"]*host["scale"] for x in packet["history_monthly"]],
                       [x["mean"] for x in raw["history_monthly"]])
    for key in ("mean_30", "median_30"):
        assert packet["rolling"][key]*host["scale"] == pytest.approx(raw["rolling"][key])
    for key in ("seasonal_p10", "seasonal_p50", "seasonal_p90"):
        assert packet["seasonality"][key]*host["scale"] == pytest.approx(raw["seasonality"][key])
    restored = restore_forecast({"point_forecast": 1., "range_low": .9, "range_high": 1.1}, host)
    assert restored["point_forecast"] == host["scale"] and restored["unit"] == "CNY/kg"
    assert audit_packet(packet, history, host)["passed"]


def test_blind_transform_is_scale_and_name_invariant(history):
    one = build_blind_packet("土豆", "2023-06-01", 90, dataset=history)
    other = history.assign(crop="陌生作物", price_per_kg=history.price_per_kg*100)
    two = build_blind_packet("陌生作物", "2023-06-01", 90, dataset=other)
    assert packet_hash(one) == packet_hash(two)


def test_future_price_changes_do_not_affect_packet_or_bounds(history):
    changed = history.copy()
    changed.loc[changed.date > "2023-06-01", "price_per_kg"] *= 100000
    one, host1 = build_case_context("土豆", "2023-06-01", 90, mode="blind", dataset=history)
    two, host2 = build_case_context("土豆", "2023-06-01", 90, mode="blind", dataset=changed)
    assert packet_hash(one) == packet_hash(two) and host1 == host2
    with pytest.raises(ValueError, match="bounds"):
        hard_bounds(history, "CROP_A", cutoff="2023-06-01")


def test_packet_recomputes_features_and_never_calls_final(history, monkeypatch):
    fake = types.SimpleNamespace(predict=lambda *_: pytest.fail("post-cutoff Final artifact loaded"))
    monkeypatch.setitem(__import__("sys").modules, "decision_engine.final.artifacts", fake)
    poisoned = history.assign(price_ma30=1e15, seasonal_p50=-1000, target_mean_price_next_90d=1e15)
    packet = build_packet("土豆", "2023-06-01", 90, dataset=poisoned)
    clean = build_packet("土豆", "2023-06-01", 90, dataset=history)
    assert packet_hash(packet) == packet_hash(clean)
    assert all(not model["is_short_model"] for model in packet["short_model"].values())


@pytest.mark.parametrize("event", [
    {"source": "https://source.example/event", "publication_date": "2023-06-02", "available_at_cutoff": True},
    {"publication_date": "2023-05-31", "available_at_cutoff": True},
    {"source": "https://source.example/event", "publication_date": "2023-05-31"},
])
def test_external_context_requires_source_publication_and_availability(history, event):
    packet = build_packet("土豆", "2023-06-01", 90, dataset=history)
    packet["events"] = [event]
    assert not audit_packet(packet)["passed"]


def test_future_feature_and_mutated_blind_history_are_rejected(history):
    packet = build_packet("土豆", "2023-06-01", 90, dataset=history)
    packet["feature_available_at"] = "2023-06-02"
    assert not audit_packet(packet)["passed"]
    blind, host = build_case_context("土豆", "2023-06-01", 90, mode="blind", dataset=history)
    # 篡改最近逐日明细：被尾值重建校验拒绝
    blind["history_recent"][0]["price"] *= 2
    assert not audit_packet(blind, history, host)["passed"]
    # 篡改月份聚合：mean 越出 [min,max] 被拒绝
    mutated_mean = build_case_context("土豆", "2023-06-01", 90, mode="blind", dataset=history)[0]
    mutated_mean["history_monthly"][0]["mean"] = mutated_mean["history_monthly"][0]["max"] * 2
    assert not audit_packet(mutated_mean)["passed"]
    # 把「更早历史」伪装成当前月（offset=0）：被拒绝
    mutated_offset = build_case_context("土豆", "2023-06-01", 90, mode="blind", dataset=history)[0]
    mutated_offset["history_monthly"][0]["month_offset"] = 0
    assert not audit_packet(mutated_offset)["passed"]


def test_cache_separates_config_schema_baseline_and_rendered_ablation(history):
    packet, host = build_case_context("土豆", "2023-06-01", 90, mode="blind", dataset=history)
    provider = CountingProvider()
    config = ExperimentConfig()
    first = _call_once(provider, packet, 1., "forecast", config, host_metadata=host)
    assert _call_once(provider, packet, 1., "forecast", config, host_metadata=host)["cache_hit"]
    changed = [
        _call_once(provider, packet, 1.1, "forecast", config, host_metadata=host),
        _call_once(provider, packet, 1., "residual", config, host_metadata=host),
        _call_once(provider, packet, 1., "forecast", ExperimentConfig(include_sections=[]), host_metadata=host),
        _call_once(provider, packet, 1., "forecast", ExperimentConfig(temperature=.1), host_metadata=host),
        _call_once(CountingProvider(config="second"), packet, 1., "forecast", config, host_metadata=host),
    ]
    assert len({first["key"], *[call["key"] for call in changed]}) == 6
    assert all(not call["cache_hit"] for call in changed)
    assert "seasonal_p50" not in provider.requests[3]["user"]
    assert "scale" not in provider.requests[0]["user"] and "土豆" not in provider.requests[0]["user"]


def test_invalid_responses_are_never_cached_and_tampered_hits_are_revalidated(history):
    packet, host = build_case_context("土豆", "2023-06-01", 90, mode="blind", dataset=history)
    bad = CountingProvider(invalid=True)
    for _ in range(2):
        assert not _call_once(bad, packet, None, "forecast", ExperimentConfig(), host_metadata=host)["valid"]
    assert bad.calls == 2 and not list(store.LLM_CACHE.glob("*.json"))
    provider = CountingProvider()
    result = _call_once(provider, packet, None, "forecast", ExperimentConfig(), host_metadata=host)
    path = store.LLM_CACHE / f"{result['key']}.json"
    cached = json.loads(path.read_text())
    cached["payload"]["point_forecast"] = 1e12
    path.write_text(json.dumps(cached))
    assert not _call_once(provider, packet, None, "forecast", ExperimentConfig(), host_metadata=host)["cache_hit"]
    assert provider.calls == 2


def test_repeatability_makes_real_adapter_calls_and_bypasses_existing_cache(history):
    provider = CountingProvider()
    config = ExperimentConfig()
    packet, host = build_case_context("土豆", "2023-06-01", 90, mode="blind", dataset=history)
    _call_once(provider, packet, None, "forecast", config, host_metadata=host)
    result = stability_test(provider, config, "土豆", 90, "2023-06-01", repeats=4, dataset=history)
    assert provider.calls == 5 and result["api_calls"] == 4 and result["cache_hits"] == 0
    assert result["point_std"] > 0


def test_output_binding_unit_scale_and_finiteness_are_checked(history):
    packet, host = build_case_context("土豆", "2023-06-01", 90, mode="blind", dataset=history)
    result = _call_once(CountingProvider(), packet, None, "forecast", ExperimentConfig(), host_metadata=host)
    original = result["payload"]
    for field, value in (("context_hash", "wrong"), ("method", "wrong"), ("unit", "CNY/kg"),
                         ("point_forecast", float("nan")), ("range_high", 1e10), ("drivers", [123])):
        changed = {**original, field: value}
        assert not validate_forecast(changed, 90, tuple(host["bounds"]), unit=packet["unit"],
                                     method=result["method"], context_hash=result["context_hash"])["ok"]
    assert not validate_residual({"adjustment_pct": 1., "confidence": .5, "rationale": "missing binding"})["ok"]


def test_provider_records_actual_usage_and_never_exposes_secret(monkeypatch):
    body = {"id": "response-fixture", "model": "actual-model", "usage": {"prompt_tokens": 11, "completion_tokens": 7, "total_tokens": 18},
            "choices": [{"finish_reason": "stop", "message": {"content": '{"ok": true}'}}]}
    class Response:
        def __enter__(self): return self
        def __exit__(self, *_): return False
        def read(self): return json.dumps(body).encode()
    requests = []
    def urlopen(req, timeout):
        requests.append(req)
        return Response()
    monkeypatch.setattr("urllib.request.urlopen", urlopen)
    provider = OpenAICompatProvider(api_key="fixture-credential", model="requested-model")
    assert provider.complete_json(task="fixture", system="JSON", user="JSON", schema_name="forecast") == {"ok": True}
    assert provider.call_metadata()["token_usage"]["total_tokens"] == 18
    assert provider.call_metadata()["estimated_cost_usd"] == "unknown"
    assert provider.call_metadata()["response_model"] == "actual-model"
    assert "fixture-credential" not in canonical_json(provider.cache_config())
    body["choices"][0]["finish_reason"] = "length"
    with pytest.raises(LLMUnavailable, match="incomplete"):
        provider.complete_json(task="fixture", system="JSON", user="JSON", schema_name="forecast")
    assert provider.call_metadata()["token_usage"]["total_tokens"] == 18


@pytest.mark.parametrize("url", ["http://api.example/v1", "https://credential@api.example/v1", "https://api.example/v1?key=credential"])
def test_provider_rejects_secret_bearing_or_insecure_endpoint(url):
    with pytest.raises(ValueError):
        OpenAICompatProvider(api_key="fixture", base_url=url)


def test_maturity_prevents_future_harvest_labels_from_learning_guardrails(history):
    frame, _ = prepared_target(history, 90, "harvest_market_price", "harvest_post_14")
    first = learn_adjustment_bounds(frame, "土豆", "2023-12-31", "last_value")
    changed = history.copy()
    changed.loc[changed.date > "2023-12-31", "price_per_kg"] *= 1000
    other, _ = prepared_target(changed, 90, "harvest_market_price", "harvest_post_14")
    second = learn_adjustment_bounds(other, "土豆", "2023-12-31", "last_value")
    assert first == second and first["max_label_end"] <= "2023-12-31"
    assert first["low_pct"] > -100
    old1 = learn_max_adjustment(history, "土豆", 90, "2023-12-31")
    old2 = learn_max_adjustment(changed, "土豆", 90, "2023-12-31")
    assert old1 == old2


def test_v2_has_two_separate_targets_phase_safe_labels_and_no_production(history):
    phase = {"name": "development", "start": "2023-01-01", "end": "2023-12-31", "train_end": "2022-12-31"}
    config = PilotConfig(crops=["土豆"], horizons=[60], phases=[phase])
    result = run_v2_experiment(CountingProvider(), config, history, "harvest_post_14")
    assert set(result.target_type) == {"cycle_market_average", "harvest_market_price"}
    assert result.valid.all() and (result.label_end <= phase["end"]).all()
    assert set(result.production_status) == {"RESEARCH_ONLY"} and (result.final_effective_n == 0).all()
    assert all(selection["max_label_end"] <= phase["train_end"] for selection in result.baseline_selection)
    assert all(meta["scale"] != 1 for meta in result.inverse_transform)
    with pytest.raises(ValueError, match="NO_STUB"):
        run_v2_experiment(StubProvider(), config, history, "harvest_post_14")


def test_pilot_budget_is_hard_and_cache_does_not_spend_new_call(history):
    provider = BudgetedProvider(CountingProvider(), max_calls=1)
    packet, host = build_case_context("土豆", "2023-06-01", 90, mode="blind", dataset=history)
    config = ExperimentConfig()
    assert _call_once(provider, packet, None, "forecast", config, host_metadata=host)["valid"]
    assert _call_once(provider, packet, None, "forecast", config, host_metadata=host)["cache_hit"]
    call = _call_once(provider, packet, 1.1, "forecast", config, host_metadata=host)
    assert not call["valid"] and not call["api_called"] and provider.calls == 1


def test_missing_secret_generates_blocked_reports_without_stub_or_metrics(tmp_path, monkeypatch):
    import llm.run_real_pilot as pilot
    monkeypatch.delenv("AGRISCOPE_LLM_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.setattr(pilot, "ROOT", tmp_path)
    monkeypatch.setattr(pilot, "LLM_REPORTS", tmp_path / "reports")
    (tmp_path / "reports").mkdir()
    monkeypatch.setattr(pilot, "ARTIFACT_DIR", tmp_path / "artifacts")
    monkeypatch.setattr(pilot, "_target_lock", lambda: (None, {"status": "NOT_FOUND"}))
    monkeypatch.setattr(pilot, "load_frozen_dataset", lambda: pytest.fail("no benchmark should run without key"))
    result = pilot.run_all()
    assert result["status"] == pilot.BLOCKED and result["real_api_calls"] == 0
    assert result["llm_improvement"] == "UNKNOWN" and not result["llm_production"]
    assert all((tmp_path/name).exists() for name in pilot.REPORT_NAMES)
    assert not (tmp_path / "artifacts" / "real_metrics.csv").exists()


def test_real_pilot_branch_is_auditable_under_mock_transport_and_call_cap(history, tmp_path, monkeypatch):
    import llm.run_real_pilot as pilot
    provider = CountingProvider()
    monkeypatch.setattr(pilot, "OpenAICompatProvider", lambda: provider)
    monkeypatch.setattr(pilot, "ROOT", tmp_path)
    monkeypatch.setattr(pilot, "LLM_REPORTS", tmp_path / "reports")
    (tmp_path / "reports").mkdir()
    monkeypatch.setattr(pilot, "ARTIFACT_DIR", tmp_path / "artifacts")
    monkeypatch.setattr(pilot, "load_frozen_dataset", lambda: history)
    monkeypatch.setattr(pilot, "_target_lock", lambda: ("harvest_post_14", {"status": "TEST_FIXTURE"}))
    result = pilot.run_all(max_calls=2)
    assert result["real_api_calls"] == provider.calls == 2
    assert not result["llm_production"] and result["final_effective_n"] == 0
    records = json.loads((tmp_path / "artifacts" / "real_call_records.json").read_text())
    assert any(not row["valid"] and row["fallback_used"] for row in records)
    assert all(row["point"] == row["baseline_point"] for row in records if not row["valid"])
    assert all(not row["api_called"] for row in records if not row["valid"])
    assert all("scale" not in request["user"] and "土豆" not in request["user"] for request in provider.requests)
    assert all((tmp_path/name).exists() for name in pilot.REPORT_NAMES)
