# -*- coding: utf-8 -*-
"""Phase 11–13：LLM 评估 harness。

在**同一批折、同一批 anchor**上与统计 baseline 比较：
  - 实验 A `blind_numeric_forecast`（匿名化 + 相对时间索引）
  - 实验 B `context_augmented_forecast`（cutoff-safe 上下文）
  - LLM Residual（unbounded / bounded / confidence-gated）
  - Hybrid A（baseline + LLM 残差）/ B（加权集成，权重由 dev OOT 程序选）/ C（regime 门控）

诚实性：本 harness 只负责「跑通与度量」。若 provider 不是真实 LLM（stub），
所有输出必须标记 `is_real_llm=false`，报告中 LLM 数值增益一律写「未评估」。
"""
from __future__ import annotations
from dataclasses import dataclass, field
import copy
import time
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

from decision_engine.models.backtest import FOLDS, fold_mask, metrics_table
from long_horizon.common import load_frozen_dataset
from long_horizon.targets import add_long_horizon_targets
from long_horizon.target_definition import primary_target_col
from long_horizon.baselines import rowwise_baselines

from llm.common import (canonical_json, stable_hash, prompt_meta, read_prompt,
                        LLM_RESULTS, ensure_llm_dirs, write_json)
from llm.context import (build_packet, build_blind_packet, build_case_context,
                         restore_forecast, packet_hash, audit_packet)
from llm.schemas import validate_forecast, validate_residual, validate_critic, hard_bounds
from llm.schemas import FORECAST_SCHEMA, RESIDUAL_SCHEMA, CRITIC_SCHEMA
from llm import cache as CACHE
from llm.providers import LLMProvider, LLMUnavailable

CROPS = ["土豆", "西红柿", "黄瓜", "韭菜", "青椒", "尖椒", "茄子", "芹菜", "芸豆", "甘蓝"]
LH_HORIZONS = [60, 90, 120]
PILOT_HORIZONS = [60, 90, 120]
MAX_ANCHORS_PER_FOLD = 8          # §46 控成本：pilot 阶段限制 cutoff 数


# ---------------------------------------------------------------- 统计 baseline
def best_rowwise_method(crop: str, horizon: int) -> str:
    # RC1 summary was selected on reused 2024..2026. Never use it in a PIT benchmark.
    return "b_last_value"


def _baseline_series(dataset: pd.DataFrame, horizon: int) -> pd.DataFrame:
    return rowwise_baselines(dataset, horizon)


# ---------------------------------------------------------------- case grid
@dataclass
class ExperimentConfig:
    experiment: str = "blind_numeric_forecast"      # 或 context_augmented_forecast
    horizons: List[int] = field(default_factory=lambda: list(PILOT_HORIZONS))
    crops: List[str] = field(default_factory=lambda: list(CROPS))
    max_anchors_per_fold: int = MAX_ANCHORS_PER_FOLD
    temperature: float = 0.0
    seed: Optional[int] = 42
    repeats: int = 1
    residual_mode: Optional[str] = None             # unbounded|bounded|confidence_gated
    include_sections: Optional[List[str]] = None    # 消融用：限制进入 prompt 的上下文块
    fold_names: Optional[List[str]] = None          # 限定折（如仅 dev=fold1）


def case_grid(cfg: ExperimentConfig, dataset: pd.DataFrame) -> List[Dict[str, Any]]:
    cases = []
    for horizon in cfg.horizons:
        tcol = primary_target_col(horizon)
        for crop in cfg.crops:
            sub = dataset[(dataset["crop"] == crop) & (dataset[tcol].notna())]
            for fold in FOLDS:
                if cfg.fold_names is not None and fold["name"] not in cfg.fold_names:
                    continue
                _, te = fold_mask(sub, fold)
                anchors = sub[te].sort_values("date")
                if not len(anchors):
                    continue
                step = max(1, len(anchors) // cfg.max_anchors_per_fold)
                picks = anchors.iloc[::step].head(cfg.max_anchors_per_fold)
                for _, r in picks.iterrows():
                    cases.append({"crop": crop, "horizon": horizon, "fold": fold["name"],
                                  "anchor": str(pd.Timestamp(r["date"]).date()),
                                  "actual": float(r[tcol])})
    return cases


# ---------------------------------------------------------------- prompt 渲染
def _render(prompt_name: str, packet: Dict[str, Any], baseline_point: Optional[float],
            sections: Optional[List[str]] = None, *, method: str = "forecast",
            context_hash: Optional[str] = None) -> Tuple[str, str]:
    text = read_prompt(prompt_name)
    system = text.split("## system", 1)[1].split("## user", 1)[0].strip()
    user_tpl = text.split("## user", 1)[1].strip() if "## user" in text else ""

    selected = copy.deepcopy(packet)
    if sections is not None:
        for name in ("seasonality", "short_model", "risk", "events", "climate"):
            if name not in sections:
                selected.pop(name, None)
        # Avoid a climate ablation leaking the climate context through the risk block.
        if "climate" not in sections and isinstance(selected.get("risk"), dict):
            selected["risk"].pop("climate_exposure", None)
        if "events" not in sections:
            selected.pop("events_available", None)
            selected.pop("events_status", None)
    fields = {"packet_json": canonical_json(selected), "method": method,
              "context_hash": context_hash or packet_hash(packet),
              "unit": packet["unit"], "horizon": packet["horizon"],
              "baseline_point": baseline_point}
    user = user_tpl
    for k, v in fields.items():
        user = user.replace("{" + k + "}", str(v))
    return system, user


# ---------------------------------------------------------------- 单次调用
def _call_once(provider: LLMProvider, packet: Dict[str, Any], baseline_point: Optional[float],
               schema_name: str, cfg: ExperimentConfig, *, host_metadata: Optional[dict] = None,
               bypass_cache: bool = False) -> Dict[str, Any]:
    prompt_name = {"forecast": "forecast_v2.md", "residual": "residual_v2.md",
                   "critic": "critic_v2.md"}[schema_name]
    pm = prompt_meta(prompt_name)
    chash = packet_hash(packet)
    method = f"{cfg.experiment}:{schema_name}"
    system, user = _render(prompt_name, packet, baseline_point, cfg.include_sections,
                           method=method, context_hash=chash)
    pm["rendered_prompt_hash"] = stable_hash({"system": system, "user": user}, n=64)
    schema = copy.deepcopy({"forecast": FORECAST_SCHEMA, "residual": RESIDUAL_SCHEMA,
                            "critic": CRITIC_SCHEMA}[schema_name])
    if schema_name == "forecast":
        schema["properties"]["unit"] = {"const": packet["unit"]}
    bounds = tuple(host_metadata["bounds"]) if host_metadata else hard_bounds_placeholder(packet)
    request_config = {"temperature": cfg.temperature, "seed": cfg.seed,
                      "actual_seed": cfg.seed if provider.seed_supported else None,
                      "task": cfg.experiment, "schema_name": schema_name,
                      "baseline_point": baseline_point, "include_sections": cfg.include_sections}
    key = CACHE.cache_key(chash, pm["rendered_prompt_hash"], provider.model,
                          provider_config=provider.cache_config(), schema=schema,
                          request_config=request_config)

    def validate(out):
        if schema_name == "forecast":
            return validate_forecast(out, packet["horizon"], bounds, unit=packet["unit"],
                                     context_hash=chash, method=method)
        return (validate_residual if schema_name == "residual" else validate_critic)(
            out, context_hash=chash, method=method)

    base = {"prompt_meta": pm, "context_hash": chash, "key": key,
            "method": method, "provider_config": provider.cache_config(), "request_config": request_config}
    hit = None if bypass_cache else CACHE.get(key)
    if hit is not None and validate(hit["payload"])["ok"]:
        return {**base, "payload": hit["payload"], "cache_hit": True, "valid": True,
                "errors": [], "latency_ms": 0., "api_called": False,
                "response_model": hit.get("meta", {}).get("response_model", "unknown"),
                "response_id": hit.get("meta", {}).get("response_id", "unknown"),
                "system_fingerprint": hit.get("meta", {}).get("system_fingerprint", "unknown"),
                "token_usage": {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0},
                "estimated_cost_usd": 0.}
    ctx = {"context_hash": chash, "baseline_point": baseline_point,
           "current_price": packet["current_price"], "horizon": packet["horizon"],
           "unit": packet["unit"], "method": method}
    started = time.perf_counter()
    try:
        out = provider.complete_json(task=cfg.experiment, system=system, user=user,
                                     schema_name=schema_name, context=ctx,
                                     temperature=cfg.temperature,
                                     seed=cfg.seed if provider.seed_supported else None)
    except LLMUnavailable as e:
        # 必须保留真实失败原因（timeout / http_429 / incomplete_response_finish_reason:length …），
        # 否则审计只能看到笼统的 "LLMUnavailable"，无法区分瞬时网络与确定性失败。
        detail = str(e) or type(e).__name__
        return {**base, "payload": None, "cache_hit": False, "valid": False,
                "errors": [f"llm_unavailable:{type(e).__name__}:{detail}"],
                "latency_ms": (time.perf_counter() - started) * 1000,
                "api_called": getattr(provider, "last_call_attempted", provider.is_available()),
                **provider.call_metadata()}
    elapsed = (time.perf_counter() - started) * 1000
    v = validate(out)
    metadata = {**provider.call_metadata(), "latency_ms": elapsed, "api_called": True}
    if v["ok"]:
        if not bypass_cache:
            CACHE.put(key, out, {**base, **metadata, "provider": provider.describe(),
                                "is_real_llm": provider.is_real_llm}, validated=True)
    return {**base, **metadata, "payload": out, "cache_hit": False,
            "valid": v["ok"], "errors": v["errors"]}


def hard_bounds_placeholder(packet: Dict[str, Any]) -> Tuple[float, float]:
    """用**该作物全量历史价格分布**推出的量级边界（程序化，非手写常数）。

    压缩后明细只含最近 N 个观测，因此必须使用 packet 自带的 `price_bounds`
    （由全量历史在 build_packet 时计算），否则会把合法输出误判为越界。
    """
    bounds = packet.get("price_bounds")
    if isinstance(bounds, (list, tuple)) and len(bounds) == 2 \
            and all(np.isfinite(bounds)) and bounds[0] > 0 and bounds[1] >= bounds[0]:
        return float(bounds[0]), float(bounds[1])
    prices = np.array([row["price"] for row in packet.get("history_recent", [])], dtype=float)
    if not len(prices) or not np.isfinite(prices).all() or min(prices) <= 0:
        raise ValueError("missing_cutoff_safe_packet_bounds")
    return float(min(prices) * .5), float(max(prices) * 3.)


# ---------------------------------------------------------------- 主运行
def run_experiment(provider: LLMProvider, cfg: ExperimentConfig,
                   dataset: Optional[pd.DataFrame] = None) -> Dict[str, Any]:
    ensure_llm_dirs()
    ds = dataset if dataset is not None else load_frozen_dataset()
    ds = add_long_horizon_targets(ds, horizons=cfg.horizons)

    cases = case_grid(cfg, ds)
    records: List[Dict[str, Any]] = []
    baseline_series: Dict[int, pd.DataFrame] = {}
    for h in cfg.horizons:
        baseline_series[h] = _baseline_series(ds, h)

    for c in cases:
        h = c["horizon"]
        crop = c["crop"]
        packet, host = build_case_context(crop, c["anchor"], h, dataset=ds,
            mode="blind" if cfg.experiment == "blind_numeric_forecast" else "context")
        packet["target_type"] = "cycle_market_average"
        packet["target_window"] = {"start_offset": 1, "end_offset": h}
        leak = audit_packet(packet, dataset=ds, host_metadata=host)
        if not leak["passed"]:
            raise ValueError("packet_leakage_audit_failed")

        bser = baseline_series[h]
        brow = bser[(bser["crop"] == crop) & (bser["date"] == pd.Timestamp(c["anchor"]))]
        bmethod = best_rowwise_method(crop, h)
        bpoint = float(brow.iloc[0][bmethod]) if len(brow) and pd.notna(brow.iloc[0][bmethod]) else None
        pct = (float(brow.iloc[0]["expanding_price_percentile"])
               if len(brow) and pd.notna(brow.iloc[0].get("expanding_price_percentile")) else None)
        regime = ("low" if (pct is not None and pct < 1 / 3)
                  else "high" if (pct is not None and pct > 2 / 3) else "mid")

        schema = "residual" if cfg.residual_mode else "forecast"
        call = _call_once(provider, packet, bpoint / host["scale"] if bpoint is not None else None,
                          schema, cfg, host_metadata=host)
        rec = {
            "crop": crop, "horizon": h, "fold": c["fold"], "anchor": c["anchor"],
            "experiment": cfg.experiment, "schema": schema,
            "actual": c["actual"], "baseline_method": bmethod, "baseline_point": bpoint,
            "target_type": "cycle_market_average", "evidence_status": "RETROSPECTIVE_ONLY_NO_UNTOUCHED",
            "untouched_metric": None, "production_status": "RESEARCH_ONLY",
            "price_percentile": pct, "regime": regime,
            "provider": provider.name, "is_real_llm": provider.is_real_llm,
            "context_hash": call["context_hash"], "prompt_version": call["prompt_meta"]["prompt_version"],
            "prompt_hash": call["prompt_meta"]["prompt_hash"], "cache_hit": call["cache_hit"],
            "valid": call["valid"], "errors": ";".join(call["errors"]),
            "leakage_passed": leak["passed"],
            "temperature": cfg.temperature, "residual_mode": cfg.residual_mode,
            "latency_ms": call["latency_ms"], "token_usage": call["token_usage"],
            "estimated_cost_usd": call["estimated_cost_usd"],
            "rendered_prompt_hash": call["prompt_meta"]["rendered_prompt_hash"],
        }
        if call["valid"] and call["payload"]:
            p = restore_forecast(call["payload"], host) if schema == "forecast" else call["payload"]
            if schema == "forecast":
                rec.update({"point": float(p["point_forecast"]), "low": float(p["range_low"]),
                            "high": float(p["range_high"]), "direction": p["direction"],
                            "confidence": float(p["confidence"])})
            else:
                rec.update({"adjustment_pct": float(p["adjustment_pct"]),
                            "confidence": float(p["confidence"])})
        records.append(rec)

    df = pd.DataFrame(records)
    return {"records": df, "cases": len(cases), "cases_with_response": int(df["valid"].sum()),
            "provider": provider.describe()}


# ---------------------------------------------------------------- 指标
def point_metrics(records: pd.DataFrame) -> pd.DataFrame:
    if not records.empty and ("is_real_llm" not in records or not records["is_real_llm"].all()):
        raise ValueError("LLM_CAPABILITY_METRICS_REQUIRE_REAL_PROVIDER")
    rows = []
    ok = records[records["valid"] & records["point"].notna()] if "point" in records else records
    for (exp, h), sub in ok.groupby(["experiment", "horizon"]):
        base = sub.dropna(subset=["baseline_point"])
        m_llm = metrics_table(sub["actual"].values, sub["point"].values)
        m_base = metrics_table(base["actual"].values, base["baseline_point"].values) if len(base) else {}
        rows.append({"experiment": exp, "horizon": int(h), "n": len(sub),
                     "llm_WAPE": m_llm["WAPE"], "llm_MAE": m_llm["MAE"],
                     "llm_sMAPE": m_llm["sMAPE"],
                     "baseline_WAPE": m_base.get("WAPE"),
                     "delta_WAPE": (m_base.get("WAPE") - m_llm["WAPE"]) if m_base else None})
    return pd.DataFrame(rows)


def stability_test(provider: LLMProvider, cfg: ExperimentConfig, crop: str, horizon: int,
                   anchor: str, repeats: int = 4, dataset: Optional[pd.DataFrame] = None) -> Dict[str, Any]:
    ds = dataset if dataset is not None else load_frozen_dataset()
    packet, host = build_case_context(crop, anchor, horizon, dataset=ds,
        mode="blind" if cfg.experiment == "blind_numeric_forecast" else "context")
    pts, dirs, los, his, calls = [], [], [], [], []
    for _ in range(repeats):
        c = _call_once(provider, packet, None, "forecast", cfg, host_metadata=host, bypass_cache=True)
        calls.append(c)
        if c["valid"]:
            p = restore_forecast(c["payload"], host)
            pts.append(float(p["point_forecast"])); dirs.append(p["direction"])
            los.append(float(p["range_low"])); his.append(float(p["range_high"]))
    return {"repeats": repeats, "n_ok": len(pts),
            "api_calls": sum(bool(c["api_called"]) for c in calls),
            "cache_hits": sum(bool(c["cache_hit"]) for c in calls),
            "is_real_llm": provider.is_real_llm,
            "latency_ms": [c["latency_ms"] for c in calls],
            "token_usage": [c["token_usage"] for c in calls],
            "estimated_cost_usd": [c["estimated_cost_usd"] for c in calls],
            "point_std": float(np.std(pts)) if pts else None,
            "point_cv": float(np.std(pts) / np.mean(pts)) if pts and np.mean(pts) else None,
            "direction_unique": sorted(set(dirs)),
            "range_std": float(np.std(np.array(his) - np.array(los))) if len(los) else None}


# ---------------------------------------------------------------- 残差边界（dev 学习）
def learn_max_adjustment(dataset: pd.DataFrame, crop: str, horizon: int,
                         train_end: str, q: float = 0.9) -> Dict[str, Any]:
    """由 **development 段**（严格 <= train_end）的统计 baseline 残差分布推出调整上限。"""
    tcol = primary_target_col(horizon)
    ds = add_long_horizon_targets(dataset, horizons=[horizon])
    bser = rowwise_baselines(ds, horizon)
    bmethod = best_rowwise_method(crop, horizon)
    # An anchor before train_end is insufficient: every future label must already be mature.
    sub = bser[(bser["crop"] == crop) &
               (bser["date"] + pd.Timedelta(days=horizon) <= pd.Timestamp(train_end))]
    sub = sub[sub[tcol].notna() & sub[bmethod].notna()]
    if not len(sub):
        return {"crop": crop, "horizon": horizon, "n": 0, "max_adjustment_pct": None}
    resid = np.abs(sub[tcol].values / sub[bmethod].values - 1.0) * 100.0
    return {"crop": crop, "horizon": horizon, "n": int(len(sub)),
            "max_adjustment_pct": float(np.percentile(resid, q * 100)),
            "median_abs_resid_pct": float(np.median(resid))}


__all__ = ["ExperimentConfig", "case_grid", "run_experiment", "point_metrics",
           "stability_test", "learn_max_adjustment", "best_rowwise_method",
           "CROPS", "LH_HORIZONS", "PILOT_HORIZONS"]
