# RECOMMENDATION_ENGINE_SPEC — Decision Engine v2 推荐引擎规范

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
{
  "city": "沈阳",
  "available_area_mu": 100,
  "budget": 500000,
  "earliest_plant_date": "2027-03-01",
  "latest_harvest_date": "2027-10-31",
  "risk_preference": "balanced",
  "mode": "compare_both",
  "as_of": null,
  "allowed_crops": null,
  "excluded_crops": null,
  "max_acceptable_loss": null
}
```

## 3. 输出 schema（§38）

key 列表：`request / recommended_plan / alternatives / top_plans / labels / pareto_frontier /
harvest_window_optimization / area_optimization / portfolio_plan / mode_comparison /
risk_summary / stress_test / confidence / ranking_stability / opportunity_cost /
comparison_reason / reasons / tradeoffs / plan_risks / limitations / evidence / performance`

## 4. 完整示例（§64：沈阳 100 亩 / 50 万 / balanced / 春季开始 / 秋季前上市）

| 项 | 值 |
|---|---|
| 推荐作物 | **芸豆** |
| 种植窗口 | 2027-07-09（来源：inferred_window） |
| 上市窗口 | 2027-10-02 ~ 2027-10-11 |
| 建议面积 | 100.0 亩 |
| 价格情景 P10/P50/P90 | 6.174363636363637 / 8.527272727272724 / 11.022436363636364 元/kg（seasonal_quantile(same_month_history)） |
| 收益（悲观/基准/乐观） | 2149131.0 / 2989456.0 / 3880586.0 元 |
| HRI / Market / Climate | 44.7 / 52.0 / 11.85 |
| 决策评分 / 效用 | 81.7（A） / 0.4355458536585366 |
| 推荐置信度 | 37.4（D）｜惩罚明细 {'reference_proxy': 11.16, 'calendar(level)': 10.0} |
| 组合建议 | 芸豆 50.0亩; 韭菜 30.0亩; 西红柿 20.0亩 |
| 单作物 vs 组合 | 组合效用 0.484 vs 单作物 0.472 → 倾向 **portfolio** |

Top5 标签：Best Return=西红柿(2027-10-11); Best Balanced=芸豆(2027-10-11); Lowest Risk=茄子(2027-08-17); Most Robust=芸豆(2027-10-11); Alternative=芸豆(2027-08-12)

**为什么不是另一个作物**（§36）：预测收益：黄瓜 低 289,182 元；下行情景：黄瓜 差 34,350 元；跟风风险：黄瓜 49.6 vs 芸豆 44.7；市场风险：黄瓜 63.8 vs 芸豆 52.0；气候暴露：黄瓜 11.9 vs 芸豆 11.8；在 balanced 偏好下，综合效用 芸豆 0.4355 > 黄瓜 0.3642（差 0.0713）

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
