"""RC2 real-provider pilot. Missing secret writes blocked reports and makes zero calls.

Run: PROJECT_ROOT=$PWD PYTHONPATH=models/src:models:. python3 -m llm.run_real_pilot
No IDE token is inspected or reused. Responses/cache are ignored runtime artifacts.
"""
from __future__ import annotations

import argparse
from dataclasses import asdict
import json
from pathlib import Path
from typing import Any
import numpy as np
import pandas as pd

from long_horizon import v2 as LH
from long_horizon.common import load_frozen_dataset
from llm.common import ROOT, LLM_REPORTS, LLM_ARTIFACTS, canonical_json, ensure_llm_dirs, stable_hash, prompt_meta
from llm.context import build_case_context, audit_packet
from llm.evaluation.harness import ExperimentConfig, stability_test
from llm.evaluation.v2 import (PilotConfig, BudgetedProvider, pilot_crops, run_v2_experiment,
                              v2_metrics, hybrid_evaluation, ablation_deltas, ABLATIONS,
                              fair_comparison_table)
from llm.providers import OpenAICompatProvider

BLOCKED = "REAL_LLM_EVALUATION_BLOCKED_BY_MISSING_SECRET"
REPORT_NAMES = ("LLM_REAL_EVALUATION_REPORT.md", "LLM_ABLATION_V2_REPORT.md", "HYBRID_V2_REPORT.md")
ARTIFACT_DIR = LLM_ARTIFACTS / "v2"


def _report(name, content):
    ensure_llm_dirs()
    for path in (ROOT / name, LLM_REPORTS / name):
        path.write_text(content + "\n", encoding="utf-8")


def _write_json(path: Path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(canonical_json(value) + "\n", encoding="utf-8")


def _target_lock() -> tuple[str | None, dict]:
    # Read the definition only. Never load/refit production model coefficients for a historical case.
    path = LH.ARTIFACTS / "target_selection_lock.json"
    if not path.exists():
        path = LH.ARTIFACTS / "model_selection_lock.json"
    if not path.exists():
        return None, {"status": "NOT_FOUND_RUN_LONG_HORIZON_V2_RETRAIN_FIRST"}
    lock = json.loads(path.read_text(encoding="utf-8"))
    if lock.get("config_hash") != LH.CONFIG_HASH:
        raise ValueError("target_selection_protocol_hash_mismatch")
    target = lock.get("harvest_definition", lock.get("target"))
    if target not in LH.CONFIG["harvest_admissible"]:
        raise ValueError("invalid_development_selected_harvest_definition")
    return target, {"source": str(path.relative_to(ROOT)), "sha256": stable_hash(lock, n=64),
                    "harvest_definition": target, "selection_data": "development+tuning only"}


def write_blocked_reports(provider: OpenAICompatProvider, target_lock: dict | None = None) -> dict:
    status = {"status": BLOCKED, "report_status": "BLOCKED_MISSING_EXTERNAL_SECRET",
              "secret_present": False, "provider": provider.describe(), "real_api_calls": 0,
              "tokens": 0, "estimated_cost_usd": 0, "llm_improvement": "UNKNOWN",
              "llm_production": False, "hybrid_production": False,
              "untouched_period": None, "final_effective_n": 0,
              "target_lock": target_lock or {"status": "NOT_FOUND"}}
    _write_json(ARTIFACT_DIR / "real_evaluation_status.json", status)
    common = f"""状态：`BLOCKED_MISSING_EXTERNAL_SECRET`
外部阻塞：`{BLOCKED}`

仅检查合法环境变量是否存在；未输出、持久化或挪用任何 Secret。合法 API Key 缺失，真实调用 **0**，
token **0**，费用 **0**。未运行 stub 数值实验；Coding Agent 的推理不算被评估的生产模型。
Provider 配置的模型 ID `{provider.model}` 尚未通过真实调用确认可访问；LLM 数值增益 **UNKNOWN**。

本轮所有历史 2024–2026 已被旧研究查看，2026 只能标 `retrospective_audit_reused`，
untouched metric 为 null、final independent n 为 0。未来评估起点不得早于 2026-10-08；必须等待真实标签成熟。
LLM / Hybrid 数值均为 `RESEARCH_ONLY`，禁止进入生产 Registry。

目标分别为 `cycle_market_average` 与 `harvest_market_price`，上市窗口只读取 development+tuning 冻结结果。
窗口锁状态：`{canonical_json(status['target_lock'])}`。

历史短期 context 仅用 cutoff-safe seasonal rule baseline，明确标为 proxy；从不调用全历史 refit 的 Final artifact。
HRI、Market Risk、气候、事件、城市日粒度物候均无可靠的逐 cutoff 来源，保持 `NOT_FOUND`。
Context benchmark 无法完全排除预训练历史记忆，与 blind 分开报告。
"""
    _report(REPORT_NAMES[0], "# LLM Real Evaluation Report（RC2）\n\n" + common + """

Blind 防护：匿名 CITY_A/CROP_A、relative day/month、current=1 的所有价格归一；可逆 scale/真实身份/边界只留 host。
Provider 只收到归一 packet、方法/context hash，成功响应须验证 finite、单位、量级、区间顺序及绑定。
cache key 包含 provider 非敏感配置、model、实际渲染 prompt hash、schema、context hash、temperature/seed；
仅缓存 schema valid 成功响应，命中重验；相同 packet 重复 3–5 次强制绕过缓存调用。
正式入口记录 latency、原始 token usage、response/model/prompt/context 和 cache hit。
未配置并验证费用单价时 `estimated_cost_usd=unknown`，不猜费用。

启动真实 Pilot：`PROJECT_ROOT=$PWD PYTHONPATH=models/src:models:. python3 -m llm.run_real_pilot --max-calls 240`。
Pilot 默认最多每 phase 一个 exposure block，属于小规模探路，不足以证明数值生产。
用量字段依据 [OpenAI Chat Completions 官方文档](https://developers.openai.com/api/reference/resources/chat/subresources/completions/methods/create)。
""")
    _report(REPORT_NAMES[1], "# LLM Ablation V2 Report（RC2）\n\n" + common + """

待真实调用执行：LLM only → seasonality → short PIT proxy → HRI/Market Risk → climate → events → Hybrid full。
每档使用实际不同渲染提示词与缓存键，并报告 paired WAPE、相对 baseline 输出偏差及逐档预测变化。
缺失上下文的档位如实标 NOT_FOUND，不能凭「加了一档」宣称来源有增益。
目前各档的真实表现、边际增益、复述 baseline 风险均 **UNKNOWN**。
""")
    _report(REPORT_NAMES[2], "# Hybrid V2 Report（RC2）\n\n" + common + """

Hybrid A：baseline + LLM residual。调整上下限由 train_end 前已成熟 label_end 的真实标签分位数学习。
Hybrid B：statistical / seasonal / LLM simplex 权重仅从 development 响应学习；development 不足时权重回退 baseline。
Hybrid C：development 逐 regime 选择 baseline 或 LLM，样本不足使用 baseline。
独立校准和真正未见 final 缺失时不能获得生产资格；真实增益、最坏场景、经济收益改善均 **UNKNOWN**。
模型失败提供显式 statistical fallback，该 fallback 不计为 LLM 成功响应或 LLM accuracy。
""")
    return status


def _real_reports(status, metrics, hybrid, locks, stability, plan, ablation, comparison):
    common = f"""状态：`{status['status']}`。真实接口调用 {status['real_api_calls']} 次；
Provider/model=`{status['provider']['provider']}/{status['provider']['model']}`；
token usage 已保存原始字段，不能确定的 estimated cost 记 unknown。
Token 汇总（排除 cache 与预算未调用）：`{canonical_json(status['token_usage'])}`；
实际调用平均 latency_ms=`{status['mean_api_latency_ms']}`，cache hits=`{status['cache_hits']}`。

所有结果为 reused retrospective pilot，untouched metric=null，final independent n=0，数值生产禁用。
Context 与 Blind 分开；Context 无法完全排除预训练历史知识。
数据/协议/target 锁、渲染 prompt hash、响应及反归一 metadata 见 `llm/artifacts/v2/`（不提交）。
快照 plan hash：`{stable_hash(plan, n=64)}`。Pilot call cap={status['max_calls']}；失败或预算不足保留显式记录。

**结论标签（retrospective，禁止据此授予生产资格）**：`{canonical_json(status.get('outcome_labels', {}))}`

HRI/Market Risk/climate/event/物候来源为 NOT_FOUND；short model 档仅为 PIT rule proxy。
"""
    rendered_metrics = metrics.to_csv(index=False) if len(metrics) else "NO_VALID_REAL_RESPONSES"
    rendered_comparison = comparison.to_csv(index=False) if comparison is not None and len(comparison) else "NO_MATCHED_VALID_RESPONSES"
    _report(REPORT_NAMES[0], "# LLM Real Evaluation Report（RC3）\n\n"+common+
            "\n\n**公平对比表**（同一 origins/crop/horizon/target/label 口径；`gain_pp` 为相对 baseline 的 WAPE 百分点改善，正=更好；数字均为 reused retrospective）：\n\n```csv\n"+
            rendered_comparison+"```\n\n逐 phase/crop/horizon/target 真实指标（WAPE/MAE/sMAPE/Bias/direction；无响应不评分）：\n\n```csv\n"+
            rendered_metrics+"```\n\n重复性（强制接口重复，无 cache）：\n\n```json\n"+canonical_json(stability)+"\n```")
    _report(REPORT_NAMES[1], "# LLM Ablation V2 Report（RC3）\n\n"+common+
            "\n\n真实消融与相对 baseline 输出偏差：\n\n```csv\n"+rendered_metrics+"```\n\n"
            "逐档 matched 预测变化与 WAPE 增益：\n\n```csv\n"+ablation.to_csv(index=False)+"```\n\n"
            "输出变化不是 accuracy gain。NOT_FOUND 的新增档位不能被解释为来源有效；缺 key/预算不足的档位不伪造指标。")
    _report(REPORT_NAMES[2], "# Hybrid V2 Report（RC3）\n\n"+common+
            "\n\nHybrid A/B/C：\n\n```csv\n"+(hybrid.to_csv(index=False) if len(hybrid) else "NOT_EVALUATED")+
            "\n```\n\nDevelopment 冻结权重/门控：\n\n```json\n"+canonical_json(locks)+
            "\n```\n\n残差边界只使用 train_end 前完整成熟的 label_end；不足时显式 baseline fallback。")


def outcome_labels(comparison) -> dict:
    """据公平对比表给出结论标签。**仅用于 retrospective 记录，不授予生产资格。**"""
    if comparison is None or len(comparison) == 0:
        return {"llm": "LLM_NOT_EVALUATED", "hybrid": "HYBRID_NOT_EVALUATED",
                "note": "RETROSPECTIVE_ONLY; not production-admissible"}

    def gain(column):
        sub = comparison.dropna(subset=[column, "baseline_WAPE"])
        return float((sub.baseline_WAPE - sub[column]).mean()) if len(sub) else None

    context_gain = gain("llm_context_WAPE")
    hybrid_gains = [value for value in (gain("hybrid_A_WAPE"), gain("hybrid_B_WAPE"),
                                        gain("hybrid_C_WAPE")) if value is not None]
    best_hybrid = max(hybrid_gains) if hybrid_gains else None
    return {
        "llm": "LLM_RETROSPECTIVE_GAIN_OBSERVED" if (context_gain is not None and context_gain > 0)
               else "LLM_NO_RETROSPECTIVE_GAIN",
        "hybrid": "HYBRID_RETROSPECTIVE_GAIN_OBSERVED" if (best_hybrid is not None and best_hybrid > 0)
                  else "HYBRID_NO_GAIN_STATISTICAL_FALLBACK_ACTIVE",
        "llm_blind_gain_pp": gain("llm_blind_WAPE"),
        "llm_context_gain_pp": context_gain,
        "llm_residual_gain_pp": gain("llm_residual_WAPE"),
        "hybrid_best_gain_pp": best_hybrid,
        "note": "RETROSPECTIVE_ONLY_NO_UNTOUCHED; research evidence only, never production-admissible",
    }


def run_all(*, max_calls=240, max_anchors=1, repeats=3, crops=None, horizons=None,
            targets=None, phases=None, skip_ablation=False, skip_stability=False,
            concurrency=1, anchors_by_phase=None) -> dict[str, Any]:
    if max_calls < 1 or max_anchors < 1 or not 3 <= repeats <= 5:
        raise ValueError("positive_budget_anchors_and_3_to_5_repeats_required")
    if max(1, concurrency) < 1:
        raise ValueError("concurrency_must_be_positive")
    anchors_by_phase = dict(anchors_by_phase or {})
    provider = OpenAICompatProvider()
    try:
        target, target_lock = _target_lock()
    except ValueError as error:
        if provider.is_available():
            raise
        target, target_lock = None, {"status": "INVALID_TARGET_LOCK", "reason": str(error)}
    if not provider.is_available():
        return write_blocked_reports(provider, target_lock)
    if target is None:
        raise ValueError("FROZEN_V2_TARGET_REQUIRED_BEFORE_REAL_PILOT")
    history = load_frozen_dataset()
    auto_crops, profiles = pilot_crops(history)
    crops = list(crops) if crops else auto_crops
    horizons = list(horizons) if horizons else list(LH.HORIZONS)
    targets = list(targets) if targets else list(LH.TARGET_TYPES)
    phases = list(phases) if phases else list(LH.PHASES)
    concurrency = max(1, concurrency)
    ablation_horizon = 90 if 90 in horizons else horizons[0]
    config = PilotConfig(crops=crops, horizons=horizons, target_types=targets, phases=phases,
                         max_anchors_per_phase=max_anchors, anchors_by_phase=anchors_by_phase,
                         concurrency=concurrency)
    residual_config = PilotConfig(crops=crops, horizons=horizons, target_types=targets,
                                  phases=[LH.PHASES[-1]], max_anchors_per_phase=max_anchors,
                                  anchors_by_phase=anchors_by_phase, concurrency=concurrency)
    ablation_config = PilotConfig(crops=crops, horizons=[ablation_horizon], target_types=targets,
                                  phases=[LH.PHASES[-1]], max_anchors_per_phase=max_anchors,
                                  anchors_by_phase=anchors_by_phase, concurrency=concurrency)
    plan = {"config": asdict(config), "long_horizon_protocol_hash": LH.CONFIG_HASH,
            "residual_config": asdict(residual_config), "ablation_config": asdict(ablation_config),
            "training_data_fingerprint": stable_hash(history[["date", "crop", "price_per_kg"]].to_dict("records"), n=64),
            "provider_config": provider.cache_config(),
            "prompt_versions": {name: prompt_meta(name) for name in ("forecast_v2.md", "residual_v2.md")},
            "target_lock": target_lock, "pilot_profiles": profiles, "max_calls": max_calls,
            "repeats": repeats, "untouched_period": None, "numeric_production": False,
            "selection": {"auto_crops": auto_crops, "crops": crops, "horizons": horizons,
                          "targets": targets, "phases": [p["name"] for p in phases],
                          "skip_ablation": skip_ablation, "skip_stability": skip_stability,
                          "concurrency": concurrency, "ablation_horizon": ablation_horizon,
                          "anchors_by_phase": anchors_by_phase, "max_anchors": max_anchors}}
    _write_json(ARTIFACT_DIR / "pilot_plan_frozen.json", plan)  # before any API call
    budgeted = BudgetedProvider(provider, max_calls)
    direct = [run_v2_experiment(budgeted, config, history, target, mode=mode) for mode in ("blind", "context")]
    residual = [run_v2_experiment(budgeted, residual_config, history, target, mode=mode, residual=True) for mode in ("blind", "context")]
    direct_df, residual_df = pd.concat(direct, ignore_index=True), pd.concat(residual, ignore_index=True)
    hybrid, locks = hybrid_evaluation(direct_df, residual_df)
    stability = []
    # Real repeatability uses the exact target packet tested in the direct benchmark.
    if not skip_stability:
        for crop in crops:
            chosen = direct_df[(direct_df.crop==crop) & (direct_df.schema=="forecast") & direct_df.valid].head(1)
            if chosen.empty:
                continue
            row = chosen.iloc[0]
            packet, host = build_case_context(crop, row.anchor, int(row.horizon), mode="blind", dataset=history)
            spec = LH.target_spec(row.target_definition, int(row.horizon))
            packet.update({"target_type": row.target_type, "target_window": {key: spec[key] for key in
                          ("name", "start_offset", "end_offset", "end_exclusive_offset", "calendar_days")},
                          "climate": {"available": False, "status": "NOT_FOUND", "reason": "NO_PIT_DATED_CLIMATE_SOURCE"}})
            from llm.evaluation.harness import _call_once
            calls = [_call_once(budgeted, packet, None, "forecast", ExperimentConfig(
                experiment="blind_numeric_forecast_v2"), host_metadata=host, bypass_cache=True) for _ in range(repeats)]
            points = [call["payload"]["point_forecast"]*host["scale"] for call in calls if call["valid"]]
            directions = [call["payload"]["direction"] for call in calls if call["valid"]]
            ranges = [(call["payload"]["range_high"]-call["payload"]["range_low"])*host["scale"] for call in calls if call["valid"]]
            stability.append({"crop": crop, "target_type": row.target_type, "horizon": int(row.horizon),
                              "repeats": repeats, "valid_n": len(points), "cache_hits": sum(bool(call["cache_hit"]) for call in calls),
                              "point_std": float(np.std(points)) if points else None,
                              "direction_consistency": max(directions.count(value) for value in set(directions))/len(directions) if directions else None,
                              "range_variance": float(np.var(ranges)) if ranges else None, "calls": calls})
    if skip_ablation:
        ablations = []
        ablation = pd.DataFrame(columns=["level", "valid_n", "paired_n", "source_status"])
    else:
        ablations = [run_v2_experiment(budgeted, ablation_config, history, target, mode="context",
                     sections=sections, ablation_level=name) for name, sections in ABLATIONS]
        ablation = ablation_deltas(pd.concat(ablations, ignore_index=True))
    all_records = pd.concat([direct_df, residual_df, *ablations], ignore_index=True)
    metrics = v2_metrics(all_records)
    comparison = fair_comparison_table(direct_df, residual_df, hybrid)
    _write_json(ARTIFACT_DIR / "real_call_records.json", all_records.to_dict("records"))
    _write_json(ARTIFACT_DIR / "hybrid_selection_lock.json", locks)
    _write_json(ARTIFACT_DIR / "repeatability.json", stability)
    metrics.to_csv(ARTIFACT_DIR / "real_metrics.csv", index=False)
    hybrid.to_csv(ARTIFACT_DIR / "hybrid_metrics.csv", index=False)
    ablation.to_csv(ARTIFACT_DIR / "ablation_deltas.csv", index=False)
    comparison.to_csv(ARTIFACT_DIR / "fair_comparison.csv", index=False)
    call_records = all_records.to_dict("records")+[call for item in stability for call in item["calls"]]
    api_records = [item for item in call_records if item["api_called"]]
    token_usage = {key: sum(item["token_usage"].get(key, 0) for item in api_records if isinstance(item["token_usage"], dict))
                   for key in ("prompt_tokens", "completion_tokens", "total_tokens")}
    token_usage["unknown_call_count"] = sum(not isinstance(item["token_usage"], dict) for item in api_records)
    valid_count = int(all_records.valid.sum())
    labels = outcome_labels(comparison)
    status_name = ("REAL_LLM_EVALUATED_FAILED_NO_VALID_RESPONSE" if valid_count == 0 else
                   "REAL_LLM_EVALUATED_PARTIAL_RETROSPECTIVE_ONLY" if valid_count < len(all_records) else
                   "REAL_LLM_EVALUATED_RETROSPECTIVE_ONLY")
    status = {"status": status_name, "secret_present": True,
              "provider": provider.describe(), "real_api_calls": budgeted.calls, "max_calls": max_calls,
              "valid_responses": valid_count, "estimated_cost_usd": "unknown",
              "token_usage": token_usage,
              "mean_api_latency_ms": float(np.mean([item["latency_ms"] for item in api_records])) if api_records else None,
              "cache_hits": sum(bool(item["cache_hit"]) for item in call_records),
              "llm_production": False, "hybrid_production": False, "untouched_period": None,
              "final_effective_n": 0, "evidence_status": "RETROSPECTIVE_ONLY_NO_UNTOUCHED",
              "outcome_labels": labels,
              "llm_improvement": labels["llm"], "hybrid_improvement": labels["hybrid"]}
    _write_json(ARTIFACT_DIR / "real_evaluation_status.json", status)
    _write_json(ARTIFACT_DIR / "outcome_labels.json", labels)
    _real_reports(status, metrics, hybrid, locks, stability, plan, ablation, comparison)
    return status


def _csv(value: str) -> list[str]:
    return [item.strip() for item in value.split(",") if item.strip()]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--max-calls", type=int, default=240)
    parser.add_argument("--max-anchors", type=int, default=1)
    parser.add_argument("--repeats", type=int, default=3)
    parser.add_argument("--crops", default="", help="逗号分隔；留空=自动选择 pilot 角色作物")
    parser.add_argument("--horizons", default="", help="逗号分隔，如 60,90,120")
    parser.add_argument("--targets", default="", help="逗号分隔 target_type")
    parser.add_argument("--phases", default="", help="逗号分隔 phase 名称")
    parser.add_argument("--skip-ablation", action="store_true", help="跳过消融档位")
    parser.add_argument("--skip-stability", action="store_true", help="跳过重复性强度测试")
    parser.add_argument("--concurrency", type=int, default=1, help="并发 API 调用数；默认 1=串行")
    parser.add_argument("--anchors-by-phase", default="",
                        help="按 phase 指定 anchor 数，如 development=3,calibration=1")
    args = parser.parse_args()

    phase_map = {phase["name"]: phase for phase in LH.PHASES}
    unknown_phases = [name for name in _csv(args.phases) if name not in phase_map]
    if unknown_phases:
        parser.error(f"unknown phases: {unknown_phases}; choose from {list(phase_map)}")
    anchors_by_phase = {}
    for item in _csv(args.anchors_by_phase):
        if "=" not in item:
            parser.error(f"--anchors-by-phase expects name=count, got {item!r}")
        name, value = item.split("=", 1)
        name = name.strip()
        if name not in phase_map:
            parser.error(f"unknown phase in --anchors-by-phase: {name}; choose from {list(phase_map)}")
        try:
            anchors_by_phase[name] = int(value)
        except ValueError:
            parser.error(f"non-integer anchor count for {name}: {value!r}")
    horizons = [int(value) for value in _csv(args.horizons)]
    unknown_horizons = [value for value in horizons if value not in LH.HORIZONS]
    if unknown_horizons:
        parser.error(f"unknown horizons: {unknown_horizons}; choose from {list(LH.HORIZONS)}")
    targets = _csv(args.targets)
    unknown_targets = [value for value in targets if value not in LH.TARGET_TYPES]
    if unknown_targets:
        parser.error(f"unknown targets: {unknown_targets}; choose from {list(LH.TARGET_TYPES)}")

    status = run_all(max_calls=args.max_calls, max_anchors=args.max_anchors, repeats=args.repeats,
                     crops=_csv(args.crops) or None, horizons=horizons or None, targets=targets or None,
                     phases=[phase_map[name] for name in _csv(args.phases)] or None,
                     skip_ablation=args.skip_ablation, skip_stability=args.skip_stability,
                     concurrency=args.concurrency, anchors_by_phase=anchors_by_phase or None)
    print(canonical_json(status))


if __name__ == "__main__":
    main()
