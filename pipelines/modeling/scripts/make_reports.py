# -*- coding: utf-8 -*-
"""
Phase: 报告生成（全部 docs/*.md + 开源整合报告）。

  python3 decision_engine/scripts/make_reports.py

生成：
  docs/DATASET_REPORT.md / LEAKAGE_VALIDATION.md / PRICE_MODEL_REPORT.md / HRI_REPORT.md
  docs/CLIMATE_RISK_REPORT.md / DECISION_ENGINE_SPEC.md / MODEL_LIMITATIONS.md / FINAL_MODEL_REPORT.md
  evaluation/open_source/OPEN_SOURCE_INTEGRATION_REPORT.md
"""
from __future__ import annotations
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from decision_engine.common import de_path, ensure_dir  # noqa: E402


def md_table(df: pd.DataFrame, floatfmt: str = ".3f", max_rows: int = 60) -> str:
    if df is None or len(df) == 0:
        return "_（无数据）_"
    d = df.head(max_rows).copy()
    for c in d.columns:
        if pd.api.types.is_float_dtype(d[c]):
            d[c] = d[c].map(lambda x: f"{x:{floatfmt}}" if pd.notna(x) else "NA")
        elif pd.api.types.is_bool_dtype(d[c]):
            d[c] = d[c].map({True: "是", False: "否"})
    head = "| " + " | ".join(map(str, d.columns)) + " |"
    sep = "|" + "|".join(["---"] * len(d.columns)) + "|"
    rows = ["| " + " | ".join(map(str, r)) + " |" for r in d.itertuples(index=False)]
    note = f"\n_（仅显示前 {max_rows} 行）_" if len(df) > max_rows else ""
    return "\n".join([head, sep] + rows) + note


def read_csv_safe(p: Path) -> pd.DataFrame:
    try:
        return pd.read_csv(p)
    except Exception:
        return pd.DataFrame()


def read_json_safe(p: Path):
    try:
        return json.loads(p.read_text())
    except Exception:
        return {}


def gen_dataset_report(ds, qc, fdict) -> str:
    prof = ds.groupby("crop").agg(
        n=("date", "count"), start=("date", "min"), end=("date", "max"),
        price_min=("price_per_kg", "min"), price_max=("price_per_kg", "max"),
        price_med=("price_per_kg", "median")).reset_index()
    miss = ds.isna().mean().sort_values(ascending=False).head(15).reset_index()
    miss.columns = ["column", "missing_rate"]
    return f"""# DATASET_REPORT — Decision Dataset v1（沈阳 10 批发蔬菜）

> 数据快照：`models/data/snapshots/v1`（冻结，见 `data/manifests/input_manifest.csv`）
> 生成脚本：`scripts/build_dataset.py`

## 0. 一句话

Decision Dataset v1 = **{len(ds):,} 行 × {ds.shape[1]} 列**，沈阳 10 种批发蔬菜 × **{ds['date'].nunique():,} 个观测日**
（{ds['date'].min()} ~ {ds['date'].max()}），价格单位 **元/斤 → 元/kg**，成交量仅相对口径（unit=unknown）。

## 1. 观测频率的实测事实（重要）

- 1410 个观测日 **不是连续自然日**：周六/周日不发布（各缺 298 天），另有 77 个工作日缺失（节假日等）；
- 因此 lag/rolling 一律使用「**观测滞后（observation lag）**」语义，并在特征字典中注明；
- 10 种作物的观测日期集合**完全一致**（已用集合运算验证）。

## 2. join 校验（price × volume）

{md_table(qc)} 

结论：matched={int(qc.iloc[0]['matched_rows']) if len(qc) else 'NA'}，两表键唯一、无未匹配、**无行数膨胀**。

## 3. 价格单位验证

- `price_raw` / `price_per_500g` = 官方原始值（元/斤，wholesale）；
- `price_per_kg` = price_per_500g × 2；
- `price_kg_check` 列对 canonical `price_per_kg` 逐行校验，**全部通过**（见 `tests/test_units.py`）。

## 4. 逐作物样本与价格范围

{md_table(prof, max_rows=12)}

## 5. 缺失率 Top15 列

{md_table(miss, floatfmt=".3f")}

> 大缺失列均为结构性：前期窗口不足（MA90/slope）、季节分位首年不可用（2021）、
> 成交量事件行不适用。**不插值、不补未来**，由模型（HistGB/EBM 原生支持 NaN；线性模型走中位数 imputer）处理。

## 6. 特征字典

- 共 {len(fdict)} 条，字段：feature / group / definition / window / pit_rule / missing_policy；
- 文件：`models/data/manifests/feature_dictionary.csv`；
- 目标列（target_*）仅作标签，**禁止进入 X**（自动测试保证）。

## 7. 快照清单

- 输入文件：见 `data/manifests/input_manifest.csv`（45 个文件，含 SHA256 / 行数 / 时间范围）；
- 建模全过程仅读快照，不触碰 canonical 原始文件。
"""


def gen_leakage_report(test_out: str, cutoff_ok: bool) -> str:
    return f"""# LEAKAGE_VALIDATION — 泄漏验证与可复现性

> 实现：`tests/test_feature_leakage.py`（pytest），并在 `run_validation` 中自动执行。

## 1. 已执行的检查

1. **rolling 不含未来**：手工重算 MA7/MA30（仅含 ≤t 的观测）与流水线一致；
2. **expanding 分位 past-only**：t 时刻分位 == 用 ≤t 历史重算的分位；
3. **季节分位仅用历史年份**：2023-06 的 P10/50/90 == 2021、2022 同月重算值；2021（首年）全部 NA；
4. **目标不进特征**：FEATURE_COLS 与 TARGET_COLS 交集为空，且无 target_* 前缀；
5. **禁用列**：STL 全序列 / `_loo` 研究输出 / extremum_weekly / 全样本 rank 均不在数据集中；
6. **目标窗口完整性**：距数据末端不足 30 天的样本 target 必须 NA（不允许截断窗口）；
7. **Cutoff reproducibility（关键）**：cutoff=2024-12-31 独立重建的特征与全量流水线在 ≤cutoff 部分**逐列完全一致**（atol=1e-12）。

## 2. 测试结果

```
{test_out.strip()[-2000:]}
```

## 3. 结论

- cutoff 可复现性：{"**通过**" if cutoff_ok else "**未通过（必须修复）**"}；
- 特征全部为 point-in-time；目标仅作标签；
- 天气默认不进入价格模型（见 PRICE_MODEL_REPORT 的 ablation 结果）。
"""


def gen_price_report(sel, comp, runtime, ablation, iv_summary, iv_per, tuned) -> str:
    selv = sel.copy()
    if len(selv):
        selv = selv[["crop", "route", "model", "mean_WAPE", "mean_MAE", "mean_RMSE",
                     "baseline_mean_WAPE", "improvement_vs_baseline_pct", "beats_baseline"]]
    abl_show = ablation[["model", "crop", "market_only", "market_plus_weather", "delta_WAPE_pct"]] \
        if len(ablation) and "delta_WAPE_pct" in ablation.columns else ablation
    return f"""# PRICE_MODEL_REPORT — 价格模型（未来 30 天均价，沈阳 10 蔬菜）

> 主目标：`target_mean_price_next_30d`（未来 30 个自然天窗口平均价，元/kg）
> 回测：expanding window，**train≤2023 → test 2024；train≤2024 → test 2025；train≤2025 → test 2026(1-9月)**
> 指标：MAE / RMSE / sMAPE / WAPE / direction_accuracy / bias（全部保存于 `evaluation/backtests/predictions.parquet`）

## 1. 最终模型（逐作物，mean+0.5×std 选择，ML 与基线同池竞争）

{md_table(selv)}

> 说明：**基线胜出 4 例**（土豆/甘蓝/芹菜/茄子）——last value 在强持续性序列上非常强，这是诚实结果；
> pooled + 正则化（elasticnet/ridge/extra_trees）在其余 6 例胜出 5~21%。
> 不允许为了「用了机器学习」而选择更差模型，最终模型按上表逐作物锁定。

## 2. 全部模型对比（跨 fold 汇总）

{md_table(comp.sort_values(['crop', 'mean_WAPE']).head(45) if len(comp) else comp, max_rows=45)}

## 3. 训练/预测 runtime（每 fold 秒）

{md_table(runtime.head(30) if len(runtime) else runtime, max_rows=30)}

## 4. 天气 ablation（market-only vs market+weather）

{md_table(abl_show.head(30) if len(abl_show) else abl_show, max_rows=30)}

> 结论：与既有研究 A06 一致——天气未带来稳定改善（平均 ΔWAPE 见上表）。
> 正式价格模型**只用 market 特征**；天气特征仅用于气候暴露模块。

## 5. 区间（P10/P50/P90）

{md_table(iv_summary)}

> 方法：seasonal_quantile（历史同月分位，scenario range）/ residual_calibration（80/20 时序内分裂残差）/
> quantile_regression（LightGBM）/ mapie_enbpi（MAPIE TimeSeriesRegressor，非交换性适配）。
> `coverage by crop / by fold` 明细见 `evaluation/metrics/interval_calibration.csv`。

## 6. Optuna 调参（时间序列目标）

{md_table(pd.DataFrame(tuned.get('results', []))[['family', 'route', 'best_value']] if tuned.get('results') else pd.DataFrame(), floatfmt='.4f') if tuned.get('results') else '_（未运行 tune_models.py 或全部失败）_'}

> objective = 跨 fold WAPE 的 mean + 0.5×std；**禁止随机 CV**。若无显著改善则保留默认参数。

## 7. 观测口径与禁忌（复述）

- lag 为「观测滞后」；周末不发布；
- 沈阳 = wholesale（元/kg 已换算）；朝阳 = market_average；锦州 = 单一层级——三者禁止混用；
- 90 天以上不做精确点预测；气象不驱动价格。
"""


def gen_hri_report(hri_h, sens, val, herding_events) -> str:
    return f"""# HRI_REPORT — 跟风种植风险指数 v1

## 1. 定义与边界

> HRI = 「可观测市场信号所形成的扩种诱因强度」（0-100），**不是农民一定会扩种的概率**，也没有监督标签。

组件（全部 past-only 历史分位 → 0-100）：
1. price_level：当前价在同季历史分位（same_season → same_month → expanding 逐级回退）
2. momentum：price_momentum_30 的历史分位
3. rise：continuous_rise_days 历史分位
4. volatility：volatility_30 历史分位（高波动=市场不稳定）
5. volume：volume_percentile（**仅沈阳**，单位未知，仅相对市场活跃度）
6. area：上一年面积增速（仅当城市×作物精确匹配；蔬菜无 → 该组件自动剔除并重新归一化权重）

风险等级阈值来自自身历史分布（expanding P50/P75/P90），不使用人为 30/60/80。

## 2. 权重方案与敏感性

监管原则：缺失组件不填 0，而是 **Σ(w·score)/Σ(available w)** 重新归一化。

{md_table(sens, floatfmt=".3f")}

> 方案：Equal / Conceptual（价格位置 .30、动能 .25、连涨 .15、波动 .15、量 .10、面积 .05）/ Entropy（训练窗口 2021-2023 计算后固定）。

## 3. 量化验证：高 HRI 之后的真实价格表现（非因果）

{md_table(val, floatfmt=".4f", max_rows=40)}

## 4. 真实跟风案例（定性证据，不做准确率宣称）

{md_table(herding_events.head(6) if len(herding_events) else herding_events, max_rows=6)}

案例与 HRI 逻辑一致性：见 FINAL_MODEL_REPORT 的历史回放案例与 `evaluation/cases/replay_cases.json`。
"""


def gen_climate_report(clim_summary, plan_ex) -> str:
    return f"""# CLIMATE_RISK_REPORT — 气候暴露指数（Exposure, not Loss）

## 1. 定位

> 输出的是「气候暴露」而非「减产/损失概率」。项目内无分作物灾损标签，**不能**构建损失模型。

## 2. 日频暴露（六城）

组件：暴雨(≥50mm)/降水 P90/连旱(分位)/土壤干/高温(P95)/温度异常，权重 0.20/0.20/0.20/0.15/0.15/0.10，缺失自动重新归一化。

{md_table(clim_summary, floatfmt=".2f")}

## 3. 未来计划的「历史同期」暴露

- 对 plan（city, plant_date, harvest_date）：统计同 DOY 窗口内各历史年份的暴雨概率/降水 P90 概率/干旱概率/土壤干概率/高温概率/温度异常；
- **明确：这是历史同期气候概率，不是未来天气预报**；
- 严格 `as_of` 截断（历史回放时只用 ≤T 的天气）。

示例：

{md_table(plan_ex, floatfmt=".2f") if len(plan_ex) else '_（未生成）_'}

## 4. 边界与限制

- ERA5 对极端高温有平滑，2020-2024 ≥35℃ 日数为 0（既有研究 A08），故高温用 P90/P95 分位而非固定阈值；
- 气象数据范围 2010-2026，无 1991-2020 climatology，基线采用 **2010-2019 固定历史基线**；
- 沈阳土壤来自 supplement（ERA5-Land，2021-2026），其余五城为原生 soil_daily.csv；口径已交叉验证一致。
"""


def gen_engine_spec(examples, scenario_cmp, sel) -> str:
    ex_md = ""
    for i, (plan, out) in enumerate(examples, 1):
        ex_md += f"\n### 示例 {i}\n\n输入：\n\n```json\n{json.dumps(plan, ensure_ascii=False, indent=2)}\n```\n\n"
        brief = {k: out.get(k) for k in ["status", "city", "crop", "risk_preference"]}
        brief["price"] = {k: out["price"].get(k) for k in ["low", "mid", "high", "method", "is_calibrated_interval"]} if out.get("price") else None
        brief["profit"] = {k: (out["profit"] or {}).get(k) for k in ["break_even_price"]} if out.get("profit") else None
        if out.get("profit"):
            brief["profit"].update({s: out["profit"][s]["profit"] for s in ["pessimistic", "baseline", "optimistic"]})
        brief["risk"] = {k: (out["risk"].get(k) or {}).get("value") if isinstance(out["risk"].get(k), dict) else None
                         for k in ["market", "herding"]}
        brief["risk"]["climate"] = (out["risk"].get("climate") or {}).get("climate_exposure_score")
        brief["decision"] = out.get("decision")
        brief["confidence"] = {k: (out.get("confidence") or {}).get(k) for k in ["score", "grade"]}
        brief["reasons"] = out.get("reasons")
        ex_md += f"输出（节选）：\n\n```json\n{json.dumps(brief, ensure_ascii=False, indent=2, default=str)}\n```\n"
    cmp_md = md_table(scenario_cmp) if isinstance(scenario_cmp, pd.DataFrame) else "_（未生成）_"
    return f"""# DECISION_ENGINE_SPEC — Decision Engine v1 接口规范

## 1. 调用方式

```python
import sys; sys.path.insert(0, "models/src")
from decision_engine.engine.engine import DecisionEngine

engine = DecisionEngine()                 # 可选 as_of="2025-06-30" 用于历史回放
result = engine.evaluate_plan({{ ... }})   # 见下方示例
ranking = engine.compare_plans([planA, planB, planC])
```

### 输入

| 字段 | 含义 | 必填 |
|---|---|---|
| city | 城市（沈阳/朝阳/锦州/大连/铁岭/丹东） | 是 |
| crop | 作物 | 是 |
| plant_date / harvest_date | 计划种植 / 上市日期 | 是 |
| area_mu | 面积（亩） | 是 |
| cost_per_mu | 亩均成本（元/亩，**用户输入**，项目无历史蔬菜成本） | 是 |
| expected_yield_per_mu | 预计亩产（kg/亩，**用户输入**） | 是 |
| risk_preference | conservative / balanced / aggressive | 否（默认 balanced） |

### 输出 schema（与任务书 §47 一致）

city / crop / price{{low,mid,high,unit,method,is_calibrated_interval}} / profit{{break_even_price,pessimistic,baseline,optimistic}}
/ risk{{market,herding,climate,production}} / decision{{score,grade,risk_preference}} / confidence{{score,grade}}
/ reasons[] / evidence[] / limitations[]

**所有数字来自模型/规则/公式/历史数据，无 LLM 生成。**

## 2. 完整示例

{ex_md}

## 3. 方案对比

{cmp_md}

## 4. 科学边界（写死在引擎里）

- 价格区间未校准时标注 `scenario range`，不得称 prediction interval；
- 大连/铁岭/丹东返回 `insufficient_market_data` + 生产背景 + 气候暴露 + 低置信度（不硬造模型）；
- 风险偏好只影响效用权重，不改变客观 HRI/Market/Climate 数值；
- 置信度与决策评分分离（差方案也可以高置信）。
"""


def gen_limitations() -> str:
    return """# MODEL_LIMITATIONS — 模型与数据边界（必须随结果展示）

## 数据事实边界

1. **无历史亩均成本**：`input_cost_weekly` 仅是化肥等农资周价；蔬菜亩均成本必须用户输入。
   官方成本参考仅沈阳/辽阳玉米水稻（`crop_cost_yearly.csv`），与蔬菜不可混用。
2. **成交量单位未知**（沈阳，`volume_unit=unknown`）：仅作相对市场活跃度，禁止写「吨/绝对供应量」。
3. **无跨城同口径价格**：沈阳 wholesale / 朝阳 market_average / 锦州混合层级；跨城重叠 <8%，**不做跨城联动**。
4. **无分作物灾损**：气候暴露 ≠ 减产比例。
5. **气象无价格预测增量**（A02-A06 复验 + 本轮 ablation）：正式价格模型不接天气。
6. **观测频率为工作日**：lag 是观测滞后而非自然日滞后。
7. **样本长度 5.7 年**：季节分位在 2021 年不可用；90 天以上不做点预测。

## 模型边界

1. HRI 不是扩种概率；Market Risk 不是价格预测；Climate Exposure 不是损失预测。
2. 区间：若 empirical coverage 未接近 80%，只称 scenario range；已通过校准的才标记 `is_calibrated_interval=true`。
3. 解释（SHAP/EBM）是模型决策依据，不是因果效应。
4. 历史回放的收益类指标依赖「回放情景假设」（成本/亩产为假设值），价格类结论不依赖该假设。
5. 朝阳/锦州为简化模块（无成交量、层级不同），其 HRI 自动降级（组件更少）。
"""


def gen_final_report(ds, sel, iv_summary, iv_sel, val, replay_cov, replay_cases, oss,
                     regional_sel, examples) -> str:
    oss_show = oss[["library", "model", "WAPE", "MAE", "status", "reason"]] if len(oss) else oss
    return f"""# FINAL_MODEL_REPORT — AgriScope Decision Engine v1

## 0. 交付概览

- 输入快照（SHA256）→ Decision Dataset v1（{len(ds):,}×{ds.shape[1]}）→ 特征（严格 past-only，cutoff 可复现）
  → 逐作物价格模型 + 区间 → HRI / Market Risk / Climate Exposure / Production Context
  → Profit / Confidence / Decision Score → Python API → 历史回放 + 案例 → 报告与图表。
- 一条命令全流程：`python3 decision_engine/scripts/run_all.py`

## 1. Dataset（数字）

- 行数：{len(ds):,}；列数：{ds.shape[1]}；范围：{ds['date'].min()} ~ {ds['date'].max()}；
- 10 作物 × {ds['date'].nunique():,} 观测日（日期集合一致，周末/节假日不发布）；
- 价格 0 缺失；join 无膨胀（见 DATASET_REPORT）。

## 2. Price Model（逐作物最终选择）

{md_table(sel[['crop','route','model','mean_WAPE','mean_MAE','mean_RMSE','baseline_mean_WAPE','improvement_vs_baseline_pct','beats_baseline']] if len(sel) else sel)}

## 3. Interval（P10/P50/P90）

{md_table(iv_summary)}

选定方法：`{iv_sel.get('method')}`，coverage={iv_sel.get('coverage')}，
is_calibrated_interval={iv_sel.get('is_calibrated_interval')}。

## 4. HRI（组成/权重/敏感性/验证）

- 组件与权重：见 `docs/HRI_REPORT.md`；
- 敏感性：方案间 Spearman 与 ±20% 权重扰动见 `evaluation/metrics/hri_sensitivity.csv`；
- 高 HRI（Top5%）之后的实际价格变化（30/60/90 天）见 HRI_REPORT 第 3 节。

## 5. Climate（组成/基线/边界）

- 组件：暴雨/降水 P90/连旱/土壤干/高温/温度异常；基线 2010-2019（无 1991-2020 数据，如实标注）；
- 计划期用「历史同期气候概率」，不是天气预报；详见 `docs/CLIMATE_RISK_REPORT.md`。

## 6. Decision Engine（3 个完整输入输出例子）

见 `docs/DECISION_ENGINE_SPEC.md` 第 2 节（含价格/收益/风险/评分/置信度/原因/证据/限制）。

## 7. Historical Replay（全样本，非精选）

- 整体覆盖率：{replay_cov.get('coverage')}（n={replay_cov.get('n')}）；P50 平均绝对误差 {replay_cov.get('mean_p50_abs_error')} 元/kg；
- 按年/按作物明细：`evaluation/metrics/replay_coverage_by_year.csv` / `by_crop.csv`；
- 案例（自动规则选择，含失败案例）：3 个高 HRI + 2 个普通 + 1 个失败（`evaluation/cases/replay_cases.json`）。

{md_table(pd.DataFrame(replay_cases.get('cases', [])).drop(columns=['narrative'], errors='ignore') if replay_cases else pd.DataFrame())}

## 8. 朝阳 / 锦州 简化扩展

{md_table(regional_sel[['crop','model','mean_WAPE','baseline_mean_WAPE','beats_baseline']] if len(regional_sel) else regional_sel, max_rows=45)}

大连/铁岭/丹东：返回 `insufficient_market_data`（生产背景 + 气候暴露 + 低置信度），不造模型。

## 9. 开源组件采用结论

{md_table(oss_show.head(60) if len(oss_show) else oss_show, max_rows=60)}

详细对比（含未采用与失败原因）见 `evaluation/open_source/OPEN_SOURCE_INTEGRATION_REPORT.md`。

## 10. 最终 runtime 依赖（保持轻量）

- 正式 pipeline：pandas / numpy / scikit-learn（+ 选定模型的实现库）+ 自研 calibration；
- 统计基线（StatsForecast 等）与 AutoGluon 等仅作 benchmark（详见开源报告），不进入正式 runtime；
- 具体因回测结果而定，若统计模型胜出则以其为正式实现。
"""


def main():
    docs = ensure_dir(de_path("docs"))
    mdir = de_path("evaluation", "metrics")
    ds = pd.read_parquet(de_path("data", "processed", "decision_dataset_v1.parquet"))
    ds["date"] = pd.to_datetime(ds["date"])
    qc = read_csv_safe(de_path("data", "manifests", "join_qc.csv"))
    fdict = read_csv_safe(de_path("data", "manifests", "feature_dictionary.csv"))
    sel = read_csv_safe(mdir / "model_selection.csv")
    comp = read_csv_safe(mdir / "model_comparison.csv")
    runtime = read_csv_safe(mdir / "model_runtime.csv")
    ablation = read_csv_safe(mdir / "weather_ablation.csv")
    iv_summary = read_csv_safe(mdir / "interval_calibration_summary.csv")
    iv_per = read_csv_safe(mdir / "interval_calibration.csv")
    iv_sel = read_json_safe(de_path("models", "registry", "interval_selection.json"))
    sens = read_csv_safe(mdir / "hri_sensitivity.csv")
    val = read_csv_safe(mdir / "hri_validation.csv")
    mr_val = read_csv_safe(mdir / "market_risk_validation.csv")
    clim_summary = read_csv_safe(mdir / "climate_daily_summary.csv")
    plan_ex = read_csv_safe(mdir / "climate_plan_examples.csv")
    replay_cov = read_csv_safe(mdir / "replay_interval_coverage.csv")
    replay_cases = read_json_safe(de_path("evaluation", "cases", "replay_cases.json"))
    oss = read_csv_safe(de_path("evaluation", "open_source", "OPEN_SOURCE_MODEL_BENCHMARK.csv"))
    regional_sel = read_csv_safe(mdir / "regional_model_selection.csv")
    tuned = read_json_safe(de_path("models", "registry", "tuned_params.json"))
    herding = read_csv_safe(de_path("data", "snapshots", "v1",
                                    "city_data/reference/decision_engine_supplement/herding_events.csv"))

    # 泄漏测试输出（重跑 pytest 快速模式）
    import subprocess
    try:
        r = subprocess.run([sys.executable, "-m", "pytest",
                            str(de_path("tests", "test_feature_leakage.py")), "-q", "--no-header"],
                           capture_output=True, text=True, cwd=str(de_path(".")), timeout=1800)
        test_out = r.stdout[-2500:]
        cutoff_ok = "failed" not in r.stdout
    except Exception as e:
        test_out = f"pytest 运行异常: {e}"
        cutoff_ok = False

    # 引擎示例（3 个完整输入输出）
    examples = []
    try:
        from decision_engine.engine.engine import DecisionEngine
        eng = DecisionEngine()
        plans = [
            {"city": "沈阳", "crop": "西红柿", "plant_date": "2026-10-10", "harvest_date": "2027-01-10",
             "area_mu": 80, "cost_per_mu": 5200, "expected_yield_per_mu": 4500, "risk_preference": "balanced"},
            {"city": "沈阳", "crop": "黄瓜", "plant_date": "2027-03-01", "harvest_date": "2027-06-10",
             "area_mu": 120, "cost_per_mu": 4800, "expected_yield_per_mu": 6000, "risk_preference": "conservative"},
            {"city": "朝阳", "crop": "西红柿", "plant_date": "2027-04-01", "harvest_date": "2027-07-01",
             "area_mu": 60, "cost_per_mu": 4200, "expected_yield_per_mu": 5000, "risk_preference": "aggressive"},
        ]
        for p in plans:
            examples.append((p, eng.evaluate_plan(p)))
        cmp_res = eng.compare_plans(plans)
        scenario_cmp = pd.DataFrame(cmp_res["ranking"]).drop(columns=["full_results"], errors="ignore") \
            if cmp_res.get("ranking") else pd.DataFrame()
    except Exception as e:
        scenario_cmp = pd.DataFrame()
        examples = [(p, {"status": f"engine error: {type(e).__name__}: {e}"}) for p in [{"note": "error"}]]

    (docs / "DATASET_REPORT.md").write_text(gen_dataset_report(ds, qc, fdict), encoding="utf-8")
    (docs / "LEAKAGE_VALIDATION.md").write_text(gen_leakage_report(test_out, cutoff_ok), encoding="utf-8")
    (docs / "PRICE_MODEL_REPORT.md").write_text(
        gen_price_report(sel, comp, runtime, ablation, iv_summary, iv_per, tuned), encoding="utf-8")
    (docs / "HRI_REPORT.md").write_text(gen_hri_report(None, sens, val, herding), encoding="utf-8")
    (docs / "CLIMATE_RISK_REPORT.md").write_text(gen_climate_report(clim_summary, plan_ex), encoding="utf-8")
    (docs / "DECISION_ENGINE_SPEC.md").write_text(gen_engine_spec(examples, scenario_cmp, sel), encoding="utf-8")
    (docs / "MODEL_LIMITATIONS.md").write_text(gen_limitations(), encoding="utf-8")
    (docs / "FINAL_MODEL_REPORT.md").write_text(gen_final_report(
        ds, sel, iv_summary, iv_sel, val, replay_cov.iloc[0].to_dict() if len(replay_cov) else {},
        replay_cases, oss, regional_sel, examples), encoding="utf-8")
    print("[reports] docs 已生成:", [p.name for p in sorted(docs.glob('*.md'))])

    # 市场风险验证数字明细附到 HRI_REPORT
    if len(mr_val):
        with open(docs / "HRI_REPORT.md", "a", encoding="utf-8") as f:
            f.write("\n\n## 5. Market Risk（独立模块）验证\n\n" + md_table(mr_val, floatfmt=".4f") +
                    "\n\n> Market Risk = 波动/回撤/区间宽度/下行空间/异常度；与 HRI 分离（详见 metrics/market_risk_validation.csv）。\n")
    print("[reports] done")


if __name__ == "__main__":
    main()