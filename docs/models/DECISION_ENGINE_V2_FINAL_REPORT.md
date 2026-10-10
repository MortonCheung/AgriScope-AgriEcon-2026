# DECISION_ENGINE_V2_FINAL_REPORT — 推荐与优化层交付总结

## 0. 一句话

v2 把 AgriScope 从「评估用户已想好的方案」推进到「**自动搜索 → 比较 → 推荐**」：
候选生成（农事约束）→ v1 批量评估（缓存）→ 多目标效用/Pareto → 窗口/面积/组合优化 →
压力测试与鲁棒决策 → Top5 推荐 + 确定性解释 + 推荐置信度。

## 1. 关键交付与数字

| 项 | 结果 |
|---|---|
| 候选生成（沈阳 100 亩示例） | `164` 个候选 → `41` 个去重方案 |
| 引擎调用 / 缓存命中 | `41` / `123`（面积变体不重复推理） |
| 单次完整推荐耗时 | 约 ~18s |
| Pareto 前沿 | 23 个非支配方案（多风格） |
| 政策基准 | A/B/C/D + Random × Top1/Top3，见 `policy_benchmark.csv` |
| 组合回测 | 11 个 cutoff；组合优于单作物 4/11 |
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

| file | target_module | enabled | reason |
|---|---|---|---|
| crop_cost_components.csv | Profit / reference_inputs | 是 | reference_cost（标注 proxy） |
| crop_spatial_structure.csv | reference_inputs / Production Context | 是 | reference_yield（区县级实测） |
| market_registry_v3.csv | 推荐证据层 | 是 | 市场通道背景（不进入价格模型） |
| market_supply_proxy.csv | HRI 解释/证据 | 否 | 仅当与价格信号同向时才作为解释证据 |
| remote_sensing_ndvi_city_monthly.csv | Climate / Production Context | 是 | 长势背景 + ablation，不进入价格模型 |
| remote_sensing_evi_city_monthly.csv | Climate / Production Context | 是 | 同上 |
| agri_insurance_claims_v3.csv | Limitations / 背景 | 否 | 不进入利润模型 |
| cold_chain_capacity_v3.csv | Limitations / 背景 | 否 | 不进入利润模型 |
| herding_events_v3.csv | HRI 定性验证 | 是 | 扩充跟风案例库 |
| demand_yearly_v3.csv | 背景/证据 | 否 | 年度需求背景 |
| pest_events.csv | Climate / Production Context（证据） | 否 | 事件证据，不建因果 |
| price_lnnync_veg_weekly_historical.csv | 省级价格背景 | 是 | 长历史省域周价（背景对照） |

- 成本组件 → `reference_cost`；空间结构 → `reference_yield`；NDVI/EVI → 气候/生产背景（不进价格模型）；
- 保险/冷链 → 仅背景与 limitations；
- 新增文件通过 `refresh_external_data()` 报告，不自动吸收。

## 4. 每日监测

| crop | date | price | price_percentile | momentum_30 | HRI | HRI_level | market_risk | market_risk_level | warning_level | HRI_thr_p90 | HRI_thr_p95 |
|---|---|---|---|---|---|---|---|---|---|---|---|
| 土豆 | 2026-09-14 | 2.16 | 0.60 | -0.00 | 61.12 | NORMAL | 66.19 | WATCH | WATCH | 76.28 | 81.79 |
| 西红柿 | 2026-09-14 | 3.76 | 0.43 | 0.05 | 57.29 | NORMAL | 54.09 | NORMAL | NORMAL | 71.89 | 77.05 |
| 黄瓜 | 2026-09-14 | 4.50 | 0.65 | -0.11 | 49.59 | NORMAL | 63.82 | WATCH | WATCH | 77.82 | 83.71 |
| 韭菜 | 2026-09-14 | 4.46 | 0.40 | -0.12 | 38.35 | NORMAL | 61.42 | WATCH | WATCH | 77.23 | 81.65 |
| 青椒 | 2026-09-14 | 4.40 | 0.62 | 0.20 | 64.50 | WATCH | 60.14 | WATCH | WATCH | 72.19 | 76.81 |
| 尖椒 | 2026-09-14 | 3.56 | 0.41 | 0.05 | 50.27 | NORMAL | 53.34 | NORMAL | NORMAL | 71.86 | 76.99 |
| 茄子 | 2026-09-14 | 2.36 | 0.38 | -0.01 | 48.96 | NORMAL | 49.41 | NORMAL | NORMAL | 74.76 | 79.31 |
| 芹菜 | 2026-09-14 | 2.60 | 0.21 | -0.13 | 29.47 | NORMAL | 54.78 | NORMAL | NORMAL | 72.57 | 77.13 |
| 芸豆 | 2026-09-14 | 7.90 | 0.58 | 0.01 | 44.70 | NORMAL | 51.99 | NORMAL | NORMAL | 73.20 | 80.51 |
| 甘蓝 | 2026-09-14 | 1.70 | 0.37 | 0.04 | 43.71 | NORMAL | 55.78 | WATCH | WATCH | 71.55 | 77.69 |

阈值表：`warning_thresholds.csv`（HRI/MR 的 P75/P90/P95）。

## 5. 限制（随结果展示）

- 价格区间为历史同月分位（scenario range）；未校准为概率区间；
- 参考成本/亩产为 proxy 时利润口径偏粗；面积不影响价格；不做复种；
- 不做跨城市联合优化（无同口径跨城价格）；
- 大连/铁岭/丹东返回 `insufficient_market_data`（不伪造推荐）。
