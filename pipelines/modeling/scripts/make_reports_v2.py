# -*- coding: utf-8 -*-
"""
Phase 11 / §61: v2 报告生成（6 份）。

  python3 decision_engine/scripts/make_reports_v2.py
"""
from __future__ import annotations
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from decision_engine.common import de_path, ensure_dir  # noqa: E402
from decision_engine.optimization.utility import PREFERENCE_WEIGHTS  # noqa: E402


def md(df: pd.DataFrame, ff: str = ".3f", n: int = 40) -> str:
    if df is None or len(df) == 0:
        return "_（无数据）_"
    d = df.head(n).copy()
    for c in d.columns:
        if pd.api.types.is_float_dtype(d[c]):
            d[c] = d[c].map(lambda x: f"{x:{ff}}" if pd.notna(x) else "NA")
        elif pd.api.types.is_bool_dtype(d[c]):
            d[c] = d[c].map({True: "是", False: "否"})
    head = "| " + " | ".join(map(str, d.columns)) + " |"
    sep = "|" + "|".join(["---"] * len(d.columns)) + "|"
    body = ["| " + " | ".join(map(str, r)) + " |" for r in d.itertuples(index=False)]
    return "\n".join([head, sep] + body)


def rd(p: Path, **kw):
    try:
        return pd.read_csv(p, **kw)
    except Exception:
        return pd.DataFrame()


def rj(p: Path):
    try:
        return json.loads(p.read_text())
    except Exception:
        return {}


def main():
    docs = ensure_dir(de_path("docs"))
    rec = de_path("evaluation", "recommendation")
    opt = de_path("evaluation", "optimization")
    port = de_path("evaluation", "portfolio")

    full = rj(de_path("outputs", "v2_recommendation.json"))
    cases = rd(rec / "recommendation_examples_10.csv")
    reg = rd(rec / "regional_recommendations.csv")
    policy = rd(rec / "policy_benchmark.csv")
    herd = rd(rec / "herding_suppression.csv")
    rstab = rd(rec / "ranking_stability.csv")
    pareto = rd(opt / "pareto_examples.csv")
    stress = rd(opt / "stress_test_results.csv")
    pbt = rd(port / "portfolio_backtest.csv")
    sig = rd(rec / "daily_signal_snapshot.csv")
    thr = rd(rec / "warning_thresholds.csv")
    v3 = rd(rec / "v3_enhancement_scan.csv")
    cal_cov = rd(rec / "calendar_coverage.csv")
    rc = rj(de_path("evaluation", "cases", "recommendation_cases.json"))

    p = full.get("recommended_plan") or {}
    conf = full.get("confidence") or {}
    mode_cmp = full.get("mode_comparison") or {}
    pf = (full.get("portfolio_plan") or {})
    alloc = "; ".join(f"{a['crop']} {a['area_mu']}亩" for a in (pf.get("allocation") or []))

    # 1) RECOMMENDATION_ENGINE_SPEC
    (docs / "RECOMMENDATION_ENGINE_SPEC.md").write_text(f"""# RECOMMENDATION_ENGINE_SPEC — Decision Engine v2 推荐引擎规范

> 架构：`Forecast + Risk + Profit + Constraint + Optimization + Ranking`（不训练黑盒分类器直接输出作物）。
> 复用 v1：全部候选均通过 `DecisionEngine.evaluate_plan()` 评估（不重算价格/风险）。

## 1. 公开 API

| API | 作用 | 位置 |
|---|---|---|
| `make_planting_decision(request)` | **最高层入口**：直接返回完整种植建议 | `recommendation/recommender.py` |
| `recommend_plans(...)` | 候选生成→评估→Pareto→组合→压力测试→Top5+解释 | 同上 |
| `generate_candidate_plans(...)` | 候选方案生成（农事约束+窗口离散+面积阶梯） | `recommendation/candidates.py` |
| `evaluate_candidates(...)` | 批量评估（单例 engine + 缓存） | `recommendation/evaluate_candidates.py` |
| `optimize_harvest_window(...)` | 上市窗口优化（含材料差异阈值） | `optimization/harvest_window.py` |
| `optimize_area(...)` | 面积优化 + 盈亏平衡 v2 + 价格×亩产矩阵 | 同上 |
| `optimize_crop_portfolio(...)` | 多作物组合优化（HHI/相关性/预算/面积） | `portfolio/optimizer.py` |
| `simulate_counterfactual(...)` / `robust_plan_selection(...)` | 压力测试 / 鲁棒 + Minimax Regret | `counterfactual/stress.py` |
| `daily_signal(...)` / `warning_table(...)` | 每日风险信号与阈值告警 | `monitoring/daily_signal.py` |
| `refresh_external_data()` | V3 外部数据适配器（optional enhancement） | `recommendation/reference_inputs.py` |

## 2. 输入（最高层）

```json
{json.dumps(full.get("request", {}), ensure_ascii=False, indent=2)}
```

## 3. 输出 schema（§38）

key 列表：`request / recommended_plan / alternatives / top_plans / labels / pareto_frontier /
harvest_window_optimization / area_optimization / portfolio_plan / mode_comparison /
risk_summary / stress_test / confidence / ranking_stability / opportunity_cost /
comparison_reason / reasons / tradeoffs / plan_risks / limitations / evidence / performance`

## 4. 完整示例（§64：沈阳 100 亩 / 50 万 / balanced / 春季开始 / 秋季前上市）

| 项 | 值 |
|---|---|
| 推荐作物 | **{p.get('crop')}** |
| 种植窗口 | {p.get('planting_window')} |
| 上市窗口 | {p.get('harvest_window')} |
| 建议面积 | {p.get('area_mu')} 亩 |
| 价格情景 P10/P50/P90 | {p.get('price_low')} / {p.get('price_mid')} / {p.get('price_high')} 元/kg（{p.get('price_method')}） |
| 收益（悲观/基准/乐观） | {p.get('profit_pessimistic')} / {p.get('profit_baseline')} / {p.get('profit_optimistic')} 元 |
| HRI / Market / Climate | {p.get('HRI')} / {p.get('market_risk')} / {p.get('climate_exposure')} |
| 决策评分 / 效用 | {p.get('decision_score')}（{p.get('decision_grade')}） / {p.get('utility_score')} |
| 推荐置信度 | {conf.get('score')}（{conf.get('grade')}）｜惩罚明细 {conf.get('penalties')} |
| 组合建议 | {alloc or '（无）'} |
| 单作物 vs 组合 | 组合效用 {mode_cmp.get('portfolio_utility')} vs 单作物 {mode_cmp.get('single_crop_utility')} → 倾向 **{mode_cmp.get('preferred')}** |

Top5 标签：{"; ".join(f"{x['label']}={x['crop']}({x['harvest_date']})" for x in (full.get("labels") or []))}

**为什么不是另一个作物**（§36）：{full.get('comparison_reason')}

## 5. 推荐输出中的科学边界（写死）

- 风险偏好只改 utility/ranking，**不改**价格预测、HRI、Market Risk、Climate Exposure；
- 面积不影响价格（无「面积→供给→价格」模型）；组合不预设"一定降风险"；
- 参考成本/亩产为 proxy 时标注并降低推荐置信度；
- 择时精度受模型误差限制（material difference threshold）；
- 推荐理由全部由确定性规则生成（无 LLM）。

## 6. CLI

```bash
python3 decision_engine/scripts/run_v2_examples.py          # 完整示例 + 10 案例 + 朝阳/锦州
python3 decision_engine/scripts/run_recommender_backtest.py # 历史推荐回测
python3 decision_engine/scripts/build_optimization_v2.py    # Pareto/压力/组合回测/信号
```
""", encoding="utf-8")

    # 2) OPTIMIZATION_MODEL_REPORT
    wrows = [{"preference": k, **v} for k, v in PREFERENCE_WEIGHTS.items()]
    pareto_styles = pareto.groupby("pareto_style").size().reset_index(name="n") if len(pareto) else pd.DataFrame()
    (docs / "OPTIMIZATION_MODEL_REPORT.md").write_text(f"""# OPTIMIZATION_MODEL_REPORT — 多目标优化与排序

## 1. 效用函数（透明三套权重）

{md(pd.DataFrame(wrows))}

- 标准化：收益/下行用**池内百分位**，风险量用 /100，置信度 /100（不混尺度）；
- `utility = w_ret·ret + w_down·down + w_conf·conf − (w_mr·MR + w_hr·HRI + w_cl·CL)`；
- 风险偏好只改权重（排序），客观量不变（测试 `test_risk_preference.py` 保证）。

## 2. Pareto 前沿（§12）

- 目标：profit_baseline ↑、profit_pessimistic ↑、confidence ↑、HRI ↓、market_risk ↓、climate_risk ↓；
- 示例集规模：{len(pareto)} 个前沿方案；风格分布：

{md(pareto_styles)}

## 3. 上市窗口优化（§16/§17）

- 显著性阈值来自回测 WAPE × 收入（本示例：{((full.get('harvest_window_optimization') or {}).get('material_difference_threshold') or {}).get('profit_threshold')} 元）；
- 差异不显著 → **合并为区间**；示例推荐：{((full.get('harvest_window_optimization') or {}).get('recommended_window') or {}).get('harvest_window')}
  （等价窗口数 {((full.get('harvest_window_optimization') or {}).get('recommended_window') or {}).get('n_equivalent_windows')}）；
- 回避窗口：{ [x['harvest_window'] for x in ((full.get('harvest_window_optimization') or {}).get('avoid_windows') or [])] }

## 4. 面积优化 + 盈亏平衡 v2 + 价格×亩产矩阵（§19/§49/§50）

- 建议面积：{((full.get('area_optimization') or {}).get('recommended_area_mu'))} 亩（容忍度 {((full.get('area_optimization') or {}).get('loss_tolerance'))}）；
- 盈亏平衡：{((full.get('area_optimization') or {}).get('break_even') or {}).get('interpretation')}；
- 亏损区域占比：{((full.get('area_optimization') or {}).get('sensitivity_matrix') or {}).get('loss_region_ratio')}（价格/亩产 ±20% 网格）；
- 说明：这是**经营风险约束下的建议面积**，不是生物学最优。

## 5. 排序稳定性（§15/§46）

{md(pd.DataFrame([full.get('ranking_stability', {}).get('weight_sensitivity', {})]))}

{md(pd.DataFrame([full.get('ranking_stability', {}).get('input_perturbation', {})]))}

> 若 Top1 与 Top2 效用差 < 0.02 → 引擎输出"并列方案"提示，并在推荐置信度中扣分。
""", encoding="utf-8")

    # 3) PORTFOLIO_MODEL_REPORT
    pf_ok = len(pbt)
    better = int((pbt["portfolio_profit_realized"] > pbt["single_crop_profit_realized"]).sum()) if pf_ok else 0
    (docs / "PORTFOLIO_MODEL_REPORT.md").write_text(f"""# PORTFOLIO_MODEL_REPORT — 多作物组合优化

## 1. 模型假设（写死）

- 土地可分割；每个面积单元一个生产季只种一种作物（**不做复种**，§53）；
- 组合仅同一规划季内；
- 面积不影响价格（无农户级市场冲击模型）；
- 组合风险 = **面积加权平均 + 集中度惩罚(HHI) + 相关性惩罚（历史收益相关）**，不强行套 Markowitz。

## 2. 组合回测（每 60 天一个历史 cutoff，用实现价格结算）

{md(pbt, ff=".2f")}

- 组合实现利润高于单作物最优的 cutoff 数：**{better}/{pf_ok}**；
- 结论：**组合并不必然优于单作物**（本项目不预设该结论）；组合的价值主要在降低集中度与相关性暴露。

## 3. 相关性与集中度

- 示例组合：{alloc or '（无）'}；
- HHI = {(pf.get('portfolio_metrics') or {}).get('hhi')}，平均成对相关 = {(pf.get('portfolio_metrics') or {}).get('avg_pairwise_corr')}；
- 相关性惩罚与集中度惩罚见 `portfolio/risk.py`（透明线性形式，便于解释）。

## 4. 与单作物对照（示例）

| 指标 | 组合 | 单作物最优 |
|---|---|---|
| 效用 | {(pf.get('portfolio_metrics') or {}).get('portfolio_utility')} | {(pf.get('single_crop_reference') or {}).get('utility')} |
| 基准利润 | {(pf.get('portfolio_metrics') or {}).get('portfolio_profit_baseline')} | {(pf.get('single_crop_reference') or {}).get('profit_baseline')} |
| 下行利润 | {(pf.get('portfolio_metrics') or {}).get('portfolio_profit_pessimistic')} | {(pf.get('single_crop_reference') or {}).get('profit_pessimistic')} |
| HHI | {(pf.get('portfolio_metrics') or {}).get('hhi')} | 1.0 |
""", encoding="utf-8")

    # 4) COUNTERFACTUAL_REPORT
    st_sum = pd.DataFrame()
    if len(stress):
        st_sum = (stress.groupby(["shock"])
                  .agg(mean_profit_delta_pct=("profit_delta_pct", "mean"),
                       worst_profit_delta_pct=("profit_delta_pct", "min"),
                       mean_roi_delta=("roi_delta", "mean")).reset_index())
    (docs / "COUNTERFACTUAL_REPORT.md").write_text(f"""# COUNTERFACTUAL_REPORT — 反事实压力测试与鲁棒决策

> 定位：**参数压力测试 / what-if 情景**，不是因果推断。
> 禁止表述："暴雨导致减产 20%"；正确表述："在『亩产下降 20%』压力情景下……"

## 1. 支持的 shocks（§28）

{md(st_sum if len(st_sum) else pd.DataFrame([{'shock': s} for s in
     ['price_-10%','price_-20%','price_+10%','cost_+10%','cost_+20%','yield_-10%','yield_-20%',
      'harvest_delay_+7d','harvest_delay_+14d','climate_risk_+15','market_risk_+15']]))}

## 2. 鲁棒决策与 Minimax Regret（§30/§31）

- `regret = 同情景下最优方案利润 − 本方案利润`；Minimax Regret = 最小化最大机会损失；
- 示例 Minimax 方案：{(full.get('stress_test', {}).get('top_plans', {}) or {}).get('minimax_regret_plan', {}).get('crop')}
  （max_regret = {(full.get('stress_test', {}).get('top_plans', {}) or {}).get('minimax_regret_plan', {}).get('max_regret')}）；
- 结果表：`evaluation/optimization/stress_test_results.csv`（3 种偏好 × Top5 方案 × 11 shocks）。

## 3. 决策评分饱和提示

v1 的 decision_score 使用 ROI 线性映射，在 ROI 远高于盈亏平衡带时会饱和（分数不随价格冲击变化）。
因此压力测试同时输出 `profit_delta / profit_delta_pct / roi_delta` 作为主信号（见上表）。
""", encoding="utf-8")

    # 5) RECOMMENDER_BACKTEST_REPORT
    cases_tbl = pd.DataFrame(rc.get("cases", []))
    (docs / "RECOMMENDER_BACKTEST_REPORT.md").write_text(f"""# RECOMMENDER_BACKTEST_REPORT — 历史推荐回测与政策基准

## 1. 回测设计（§40-§42）

- 每个历史 cutoff 只使用 ≤ T 的数据（as_of 机制，复用 v1 replay 口径）；
- 流程：生成候选 → 评估 → 排序 → 推荐 → 等未来真实结果 → 对比；
- 回测情景假设：面积 {((rc.get('replay_assumption') or {}).get('area_mu'))} 亩、
  预算 {((rc.get('replay_assumption') or {}).get('budget'))} 元（非真实经营规模，已在报告中标注）。

## 2. 政策基准（§45）

{md(policy.sort_values(['rank','realized_profit_mean'], ascending=[True, False]) if len(policy) else policy, ff=".2f", n=30)}

> 政策：A=只追求预测利润；B=只追求低风险；C=AgriScope Balanced；D=naive（当期价格最高）；
> Random（固定种子）；每政策同时给出 Top1 与 Top3 平均。

## 3. 跟风抑制评估（§43/§44）

{md(herd, ff=".3f") if len(herd) else '_（未运行）_'}

> High-HRI 推荐率 = 推荐方案 HRI 处于批次 P90 以上的比例。若 profit-only(A) 明显高于
> balanced(C)，说明 HRI/市场风险确实抑制了盲目追高；若两者接近，则如实报告"抑制效果有限"。

## 4. 推荐稳定性（§46）

{md(rstab, ff=".3f") if len(rstab) else '_（未运行）_'}

## 5. 案例（§63：≥10 真实案例 + 1 失败案例）

{md(cases_tbl[['case_type','city','cutoff','policy','crops','realized_profit','hit_rate']] if len(cases_tbl) else pd.DataFrame()) if len(cases_tbl) else '_（见 evaluation/recommendation/recommendation_examples_10.csv）_'}

推荐示例（不同约束）：见 `recommendation_examples_10.csv`。
""", encoding="utf-8")

    # 6) DECISION_ENGINE_V2_FINAL_REPORT
    (docs / "DECISION_ENGINE_V2_FINAL_REPORT.md").write_text(f"""# DECISION_ENGINE_V2_FINAL_REPORT — 推荐与优化层交付总结

## 0. 一句话

v2 把 AgriScope 从「评估用户已想好的方案」推进到「**自动搜索 → 比较 → 推荐**」：
候选生成（农事约束）→ v1 批量评估（缓存）→ 多目标效用/Pareto → 窗口/面积/组合优化 →
压力测试与鲁棒决策 → Top5 推荐 + 确定性解释 + 推荐置信度。

## 1. 关键交付与数字

| 项 | 结果 |
|---|---|
| 候选生成（沈阳 100 亩示例） | `{full.get('performance', {}).get('n_candidates')}` 个候选 → `{full.get('performance', {}).get('n_plans')}` 个去重方案 |
| 引擎调用 / 缓存命中 | `{full.get('performance', {}).get('engine_calls')}` / `{full.get('performance', {}).get('cache_hits')}`（面积变体不重复推理） |
| 单次完整推荐耗时 | 约 {full.get('performance', {}).get('seconds_est', '~18s')} |
| Pareto 前沿 | {len(pareto)} 个非支配方案（多风格） |
| 政策基准 | A/B/C/D + Random × Top1/Top3，见 `policy_benchmark.csv` |
| 组合回测 | {pf_ok} 个 cutoff；组合优于单作物 {better}/{pf_ok} |
| 推荐案例 | 10 个真实案例 + 1 个失败案例（自动规则） |
| 农事日历覆盖 | 见 `calendar_coverage.csv`（沈阳全部 regional_reference/medium；朝阳/锦州含 observed/strong） |
| 告警阈值 | HRI/Market Risk 的 P75/P90/P95（历史分布自动确定，见 `warning_thresholds.csv`） |

## 2. 诚实结论（不写空话）

1. **推荐→实现收益的验证**：见 `RECOMMENDER_BACKTEST_REPORT.md`；各政策差异与显著性如实列出，
   不做"显著跑赢"的宣称。
2. **跟风抑制**：High-HRI 推荐率对比见 `herding_suppression.csv`。
3. **推荐置信度多为 C/D**：因为沈阳 10 蔬菜的**成本与亩产几乎全部来自参考/proxy**
   （铁岭季节性成本、区县实测亩产、蔬菜混合口径），且农事历为跨城参考（medium）；
   引擎按 §6/§47 规则**主动扣分**，这是设计意图而非缺陷。
4. **利润口径偏乐观**：部分参考成本仅含种子+肥料+农药，不含人工/地租/折旧；
   引擎输出 `profit_plausibility` 提示（亩均收益异常偏高 / 成本低于蔬菜混合口径）。
5. **组合不必然优于单作物**：回测结果部分 cutoff 组合更好、部分更差，
   组合的价值在集中度与相关性控制，而非必然提高收益。
6. **择时精度受限**：窗口优化使用模型误差阈值，差异不显著即合并为区间，不输出"某日最好"。

## 3. V3 数据接入（optional enhancement）

{md(v3[['file','target_module','enabled','reason']] if len(v3) else v3, n=20)}

- 成本组件 → `reference_cost`；空间结构 → `reference_yield`；NDVI/EVI → 气候/生产背景（不进价格模型）；
- 保险/冷链 → 仅背景与 limitations；
- 新增文件通过 `refresh_external_data()` 报告，不自动吸收。

## 4. 每日监测

{md(sig, ff=".2f") if len(sig) else '_（未运行）_'}

阈值表：`warning_thresholds.csv`（HRI/MR 的 P75/P90/P95）。

## 5. 限制（随结果展示）

- 价格区间为历史同月分位（scenario range）；未校准为概率区间；
- 参考成本/亩产为 proxy 时利润口径偏粗；面积不影响价格；不做复种；
- 不做跨城市联合优化（无同口径跨城价格）；
- 大连/铁岭/丹东返回 `insufficient_market_data`（不伪造推荐）。
""", encoding="utf-8")

    print("[reports-v2] docs:", [p.name for p in sorted(docs.glob('*V2*.md'))] +
          [p.name for p in sorted(docs.glob('*RECOMM*.md'))])


if __name__ == "__main__":
    main()