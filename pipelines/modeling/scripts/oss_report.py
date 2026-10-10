# -*- coding: utf-8 -*-
"""
开源整合报告生成：

  python3 decision_engine/scripts/oss_report.py

读取 evaluation/open_source/** 的全部对比结果，生成
OPEN_SOURCE_INTEGRATION_REPORT.md（逐个项目的采用结论 + 量化对比 + 原因）。
"""
from __future__ import annotations
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from decision_engine.common import de_path, ensure_dir  # noqa: E402
from decision_engine.models.oss_common import upsert_benchmark  # noqa: E402


def md_table(df: pd.DataFrame, floatfmt: str = ".4f", max_rows: int = 60) -> str:
    if df is None or len(df) == 0:
        return "_（无数据）_"
    d = df.head(max_rows).copy()
    for c in d.columns:
        if pd.api.types.is_float_dtype(d[c]):
            d[c] = d[c].map(lambda x: f"{x:{floatfmt}}" if pd.notna(x) else "NA")
    head = "| " + " | ".join(map(str, d.columns)) + " |"
    sep = "|" + "|".join(["---"] * len(d.columns)) + "|"
    rows = ["| " + " | ".join(map(str, r)) + " |" for r in d.itertuples(index=False)]
    return "\n".join([head, sep] + rows)


def read_csv_safe(p):
    try:
        return pd.read_csv(p)
    except Exception:
        return pd.DataFrame()


def main():
    oss = ensure_dir(de_path("evaluation", "open_source"))
    bench = read_csv_safe(oss / "OPEN_SOURCE_MODEL_BENCHMARK.csv")
    sf_sum = read_csv_safe(oss / "sf_vs_inhouse_summary.csv")
    sf_hh = read_csv_safe(oss / "sf_head_to_head_by_crop.csv")
    ag_sum = read_csv_safe(oss / "autogluon_vs_inhouse.csv")
    ag_cov = read_csv_safe(oss / "autogluon_coverage_by_crop.csv")
    ts_cmp = read_csv_safe(oss / "tsfresh_experiment.csv")
    dr = read_csv_safe(oss / "evidently_drift_summary.csv")

    # AutoGluon 窗口均值层面的覆盖率（与自研区间同口径的 apples-to-apples 比较）
    ag_wm = pd.DataFrame()
    ag_orig = read_csv_safe(oss / "autogluon_origins.csv")
    if len(ag_orig):
        ag_orig = ag_orig[ag_orig["actual_window_mean"].notna()]
        hit = (ag_orig["actual_window_mean"] >= ag_orig["q10_window_mean"]) & \
              (ag_orig["actual_window_mean"] <= ag_orig["q90_window_mean"])
        ag_wm = pd.DataFrame([{
            "level": "window_mean_30d", "n": int(len(ag_orig)),
            "coverage": float(hit.mean()),
            "mean_width": float((ag_orig["q90_window_mean"] - ag_orig["q10_window_mean"]).mean())}])
        ag_wm.to_csv(oss / "autogluon_window_mean_coverage.csv", index=False, encoding="utf-8-sig")

    # 把区间方法的校准结果并入统一 benchmark（MAPIE / 自研 calibration）
    iv_sum = read_csv_safe(de_path("evaluation", "metrics", "interval_calibration_summary.csv"))
    iv_sel_path = de_path("models", "registry", "interval_selection.json")
    iv_sel = {}
    if iv_sel_path.exists():
        try:
            iv_sel = json.loads(iv_sel_path.read_text())
        except Exception:
            iv_sel = {}
    if len(iv_sum):
        rows = []
        for _, r in iv_sum.iterrows():
            m = r["method"]
            lib = "mapie" if str(m).startswith("mapie") else "builtin"
            ver = "1.4.1" if lib == "mapie" else "-"
            status = "ADOPTED" if (iv_sel.get("method") == m and iv_sel.get("is_calibrated_interval")) else (
                "ADOPTED" if iv_sel.get("method") == m else "BENCHMARK_ONLY")
            reason = (f"empirical coverage={r['coverage']:.3f} vs nominal 0.80；mean width={r['mean_width']:.3f}；"
                      f"undercoverage_rate={r['undercoverage_rate']:.2f}")
            if iv_sel.get("method") == m:
                reason += "（被选为最可靠方案）"
            rows.append({"library": lib, "model": f"interval:{m}", "version": ver,
                         "city": "沈阳", "crop": "ALL(10)", "target": "target_mean_price_next_30d",
                         "route": "interval_calibration", "coverage": round(float(r["coverage"]), 4),
                         "interval_width": round(float(r["mean_width"]), 4),
                         "status": status, "reason": reason})
        if rows:
            bench = upsert_benchmark(rows)

    adopted = bench[bench["status"] == "ADOPTED"] if len(bench) else bench
    rejected = bench[bench["status"].isin(["REJECTED", "FAILED"])] if len(bench) else bench

    txt = f"""# OPEN_SOURCE_INTEGRATION_REPORT — 开源项目公平评估与采用结论

> 原则：所有第三方方案与自研 Baseline **在同一 fold、同一评估原点**上比较；
> 禁止随机 split、禁止未来数据、禁止 cherry-pick 单个 fold。
> 统一 Benchmark：`OPEN_SOURCE_MODEL_BENCHMARK.csv`（{len(bench) if len(bench) else 0} 行）。

## 1. 采用结论总览

### ADOPTED（进入正式 pipeline / 工具链）

{md_table(adopted[['library','model','version','crop','WAPE','status','reason']] if len(adopted) else pd.DataFrame(), max_rows=40)}

### REJECTED / FAILED（不用，及原因）

{md_table(rejected[['library','model','version','crop','status','reason']] if len(rejected) else pd.DataFrame(), max_rows=40)}

## 2. StatsForecast（P0）

- 评估模型：Naive / SeasonalNaive(7) / AutoARIMA(7) / AutoETS(7) / AutoTheta(7) / AutoCES(7)
- 语义：walk-forward（refit=False，每 5 天一个原点、原点对齐观测日，30 天窗口均值），与自研模型在同一 fold 与原点集合上重算比较。

{md_table(sf_sum, max_rows=40) if len(sf_sum) else '_（未运行 oss_statsforecast.py）_'}

逐作物 head-to-head（最终选定模型 vs 最优 SF）：

{md_table(sf_hh, max_rows=12) if len(sf_hh) else '_（无）_'}

## 3. InterpretML EBM（P0）

- EBM 已加入 price model candidate set（Route A/B 同池竞争）；
- 结果：EBM 未进入逐作物最优（见 PRICE_MODEL_REPORT 第 2 节）→ `BENCHMARK_ONLY`；
- 但 EBM 的解释能力被保留为候选解释路径（若最终模型为 EBM 则直接使用其形状函数，见 explain_models.py）。

## 4. MAPIE（P0）

- 方法：`TimeSeriesRegressor(method="enbpi")`（非交换性适配的 Ensemble Batch Prediction Intervals），替代机械 iid split conformal；
- 与 seasonal quantile / residual calibration / quantile regression 同池比较：
  覆盖率与宽度见 `evaluation/metrics/interval_calibration_summary.csv`；
- 采用结论：由 coverage 校准检验决定（`models/registry/interval_selection.json`）。

## 5. Optuna（P0）

- objective = 跨 fold WAPE 的 mean + 0.5×std（时间序列验证目标）；
- 若改善小于阈值则使用默认参数（避免为调参而调参）：见 `models/registry/tuned_params.json`。

## 6. SHAP（P0）

- 对最终树模型输出 global importance / SHAP summary / dependence / local explanation；
- 输出：`evaluation/metrics/feature_importance_*.csv`、`evaluation/cases/local_explanations.json`；
- 表述规范：只写「特征对模型预测的贡献」，不写因果。

## 7. AutoGluon-TimeSeries（P0）

{md_table(ag_sum, max_rows=30) if len(ag_sum) else '_（未运行 oss_autogluon.py）_'}

分作物 quantile 覆盖（观测日层面）：

{md_table(ag_cov, max_rows=12) if len(ag_cov) else '_（无）_'}

**同口径（窗口均值层面）覆盖对比**（与自研区间方法 apples-to-apples）：

{md_table(ag_wm, floatfmt='.4f') if len(ag_wm) else '_（无）_'}

> 采用标准：ensemble 是否**稳定**优于手工模型；若无明显优势而依赖/体积巨大 → 保留轻量模型，
> AutoGluon 仅作 candidate generator benchmark 与区间校准参考。
> 关键事实（见上表与 interval 章节）：AutoGluon 的 P10/P90 在窗口均值层面达到接近名义 80% 的覆盖，
> 而自研方法（seasonal/残差）在同期测试上系统性欠覆盖（误差水平随年份漂移）——
> 已据此改进自研方案（见第 4 节与 PRICE_MODEL_REPORT），若轻量方案仍无法达标则引擎如实标注 scenario range。

## 8. Darts / sktime（P1）

- sktime splitter 验证（切分逻辑与 strict point-in-time 一致性）：`sktime_split_verification.csv`；
- Darts `historical_forecasts` 语义验证 + 模型对比：`darts_metrics.csv`；
- 结论：回测逻辑自研实现已满足「不重训 + 每周原点 + 严格 past-only」；
  Darts/sktime 作为**交叉验证工具**保留（BENCHMARK_ONLY），不进入正式 runtime（避免重复依赖）。

## 9. Chronos-Bolt（P1）

- 模型：`amazon/chronos-bolt-tiny`（zero-shot，禁止训练/超大模型下载）；
- 试点 3 作物（西红柿/黄瓜/土豆）；结论与扩展规则见 `chronos_metrics.csv` 与下方说明；
- 若无明显优势 → 立即停止 Chronos 路线（不扩展 10 作物）。

## 10. tsfresh（P1）

受控实验（过去窗口 30/90 观测、stride=3、严格 past-only、HistGB 同 fold 对比）：

{md_table(ts_cmp, max_rows=12) if len(ts_cmp) else '_（未运行 oss_tsfresh.py）_'}

> 若平均改善 < 1% 或作物不过半 → REJECTED（不引入数百特征与提取成本）。

## 11. PyOD（P1）

- 仅用于 Market Risk 的 `mr_abnormality` 组件（IsolationForest，训练窗口拟合）；
- 不包装成「风险模型」；组件覆盖率与市场风险验证见 `market_risk_validation.csv`。

## 12. Evidently（P1）

{md_table(dr, max_rows=6) if len(dr) else '_（未运行 oss_evidently.py）_'}

- 定位：QC / 漂移 / 回归质量报告工具（降低人工工作量）；
- 漂移影响 confidence：自研 KS 检验（confidence/drift.py）已在引擎内执行，漂移高 → confidence 降低（**不改变**风险数值）。

## 13. Prophet / FLAML（P2）

- Prophet：季节基线候选（trend + weekly + yearly + changepoints），与 AutoETS/AutoARIMA/Theta/SeasonalMedian 同原点比较；
- FLAML：轻量 AutoML（time-based holdout），仅作 pooled 对照；
- 胜负与 WAPE 数字见 `prophet_metrics.csv`、`flaml_metrics.csv`。

## 14. 最终 runtime 组件（防「十几个库互相依赖」）

正式 Decision Engine runtime 仅依赖：
1. 主价格模型框架（由回测决定：sklearn 族 或 StatsForecast 族）；
2. uncertainty/calibration 工具（自研 rolling residual 或 MAPIE，由 coverage 决定）；
3. explainability（SHAP 或 EBM 内在解释，由最终模型族决定）。

其余全部为 BENCHMARK_ONLY / REJECTED，不进入 runtime。
"""
    p = oss / "OPEN_SOURCE_INTEGRATION_REPORT.md"
    p.write_text(txt, encoding="utf-8")
    print(f"[oss report] -> {p}")


if __name__ == "__main__":
    main()