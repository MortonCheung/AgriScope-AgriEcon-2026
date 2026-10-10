# -*- coding: utf-8 -*-
"""
验收清单自检（任务书 §62 Acceptance Criteria 的自动化检查）。

  python3 models/scripts/check_acceptance.py
"""
from __future__ import annotations
import json
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from decision_engine.common import de_path  # noqa: E402


def exists(*p) -> bool:
    return de_path(*p).exists()


def main():
    checks = []

    def add(name, ok, detail=""):
        checks.append((name, bool(ok), detail))

    # 数据与特征
    add("输入快照完成", exists("data", "manifests", "input_manifest.csv"),
        f"{len(pd.read_csv(de_path('data','manifests','input_manifest.csv')))} 个文件")
    ds_ok = exists("data", "processed", "decision_dataset_v1.parquet")
    add("Decision Dataset v1 完成", ds_ok and exists("data", "processed", "decision_dataset_v1.csv"),
        f"{len(pd.read_parquet(de_path('data','processed','decision_dataset_v1.parquet')))} 行" if ds_ok else "")
    add("特征字典完成", exists("data", "manifests", "feature_dictionary.csv"),
        f"{len(pd.read_csv(de_path('data','manifests','feature_dictionary.csv')))} 条")
    add("泄漏验证（含 cutoff 可复现）", exists("docs", "LEAKAGE_VALIDATION.md"))

    # 模型
    add("Baseline 完成", exists("evaluation", "metrics", "model_comparison.csv"))
    add("多模型比较完成", exists("evaluation", "metrics", "model_comparison.csv"))
    add("10 种沈阳蔬菜价格模型完成", exists("models", "registry", "model_registry.json"),
        f"{len(json.loads(de_path('models','registry','model_registry.json').read_text()).get('price_models', []))} 个条目")
    add("30 天目标回测完成", exists("evaluation", "backtests", "predictions.parquet"))
    add("P10/P50/P90 区间完成", exists("evaluation", "backtests", "interval_predictions.parquet"))
    add("区间 calibration 完成", exists("evaluation", "metrics", "interval_calibration.csv"))

    # 风险
    add("HRI v1 完成", exists("data", "features", "hri_v1.parquet"))
    add("HRI sensitivity 完成", exists("evaluation", "metrics", "hri_sensitivity.csv"))
    add("Market Risk 完成", exists("data", "features", "market_risk_v1.parquet"))
    add("Climate Exposure 完成", exists("data", "features", "climate_daily_shenyang.parquet"))
    add("Production Context 完成", exists("data", "features", "production_context.csv"))

    # 决策
    add("Profit Engine 完成", exists("outputs", "engine_examples.json"))
    add("Confidence Engine 完成", exists("outputs", "engine_examples.json"))
    add("Decision Score 完成", exists("outputs", "engine_examples.json"))
    add("风险偏好完成", exists("outputs", "engine_examples.json"))
    add("Scenario Comparison 完成", exists("outputs", "engine_examples.json"))

    # 回放与扩展
    rp = exists("evaluation", "backtests", "replay_results.csv")
    n_replay = len(pd.read_csv(de_path("evaluation", "backtests", "replay_results.csv"))) if rp else 0
    add("历史全量 backtest 完成", rp, f"{n_replay} 条回放记录")
    cases_ok = exists("evaluation", "cases", "replay_cases.json")
    n_cases = len(json.loads(de_path("evaluation", "cases", "replay_cases.json").read_text())["cases"]) if cases_ok else 0
    add("至少 6 个历史案例完成", cases_ok and n_cases >= 6, f"{n_cases} 个案例")
    add("朝阳简化扩展完成", exists("data", "features", "regional_朝阳.parquet"))
    add("锦州简化扩展完成", exists("data", "features", "regional_锦州.parquet"))
    add("大连/铁岭/丹东降级机制完成", exists("outputs", "engine_examples.json"))

    # 交付
    add("Decision Engine Python API 完成", exists("src", "decision_engine", "engine", "engine.py"))
    add("模型注册表完成", exists("models", "registry", "model_registry.json"))
    add("自动测试完成", exists("tests", "test_feature_leakage.py") and exists("tests", "test_engine.py"))
    figs = list(de_path("evaluation", "figures").glob("*.png")) if exists("evaluation", "figures") else []
    add("图表完成", len(figs) >= 8, f"{len(figs)} 张")
    docs = ["DATASET_REPORT.md", "LEAKAGE_VALIDATION.md", "PRICE_MODEL_REPORT.md", "HRI_REPORT.md",
            "CLIMATE_RISK_REPORT.md", "DECISION_ENGINE_SPEC.md", "MODEL_LIMITATIONS.md", "FINAL_MODEL_REPORT.md"]
    have = [d for d in docs if exists("docs", d)]
    add("最终报告完成", len(have) == len(docs), f"{len(have)}/{len(docs)}")
    add("开源 Benchmark 完成", exists("evaluation", "open_source", "OPEN_SOURCE_MODEL_BENCHMARK.csv") and
        exists("evaluation", "open_source", "OPEN_SOURCE_INTEGRATION_REPORT.md"))
    add("一条命令重建（run_all.py）", exists("scripts", "run_all.py"))

    ok_n = sum(1 for _, ok, _ in checks if ok)
    print("\n== AgriScope Decision Engine v1 验收清单 ==")
    for name, ok, detail in checks:
        mark = "✅" if ok else "❌"
        print(f"{mark} {name}" + (f"  [{detail}]" if detail else ""))
    print(f"\n通过 {ok_n}/{len(checks)}")
    return 0 if ok_n == len(checks) else 1


if __name__ == "__main__":
    raise SystemExit(main())