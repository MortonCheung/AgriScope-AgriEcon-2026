# Final Model — 30 问回答

1. **最终使用了哪些数据？** `data/model_ready/` 19 张 parquet（冻结为 `final_v1`）；价格核心为 `shenyang_core/market_daily`（wholesale），扩展用 `chaoyang_extended/market_daily`（market_average）。
2. **哪些数据被禁止使用？** `DO_NOT_USE_FOR_MODEL.csv` 全部条目；`hri_inputs` 复合 price_level 行；archive 旧加工层；`models/data/snapshots/**` 旧快照。
3. **是否发现 leakage？** 否。截断不变性测试 0 泄漏（沈阳/朝阳 × 3 截断点 × 63 特征）。
4. **最终支持哪些城市？** 沈阳（完整）、朝阳（扩展/弱）、锦州（弱化不主用）；大连/铁岭/丹东 = insufficient_market_data。
5. **最终支持哪些作物？** 沈阳 10 蔬菜：土豆, 西红柿, 黄瓜, 韭菜, 青椒, 尖椒, 茄子, 芹菜, 芸豆, 甘蓝。
6. **每种作物最终用什么 Price Model（h=30）？** 土豆→baseline_last_value(baseline); 尖椒→elasticnet(pooled); 甘蓝→baseline_last_value(baseline); 芸豆→elasticnet(pooled); 芹菜→baseline_last_value(baseline); 茄子→elasticnet_tuned(pooled); 西红柿→elasticnet_tuned(pooled); 青椒→elasticnet_tuned(pooled); 韭菜→elasticnet_tuned(per_crop); 黄瓜→extra_trees(pooled)。
7. **为什么选择它？** 按 OOT mean_WAPE + 0.5·std_WAPE 综合（平均 + 稳定性惩罚）在同池（含 baseline）竞争胜出。
8. **相比 baseline 提升多少？** 见 PRICE_MODEL_REPORT 的 improvement_vs_baseline_pct 列（h=30 沈阳 7/10 优于 baseline）。
9. **哪些作物复杂模型没有赢？** 土豆, 甘蓝, 芹菜 → 使用 baseline。
10. **每种 horizon 表现怎样？** 见 multi_horizon_WAPE.csv；7/14/30 天可用，60/90 天误差上升，长期建议情景化。
11. **价格 scenario range 实际覆盖多少？** 全局不设单一数字；改为**逐 crop×horizon 校准**（`scenario_range_by_crop_horizon.csv`）。参考：全局最优方法 coverage 0.745，逐作物最低 0.153 → 全部以 `scenario_range` / `scenario_range_widened` / `scenario_range_unreliable` 明确标注，**不用总体覆盖率掩盖最差作物**。
12. **HRI 是否真的有预测/风险区分价值？** 原始检验：90 天层面沈阳 10 作物中 9 个高-HRI 组未来收益显著更低（raw p<0.05）；但**时间序列稳健化后（block bootstrap + HAC 双通过）仅 5/10 显著** → 定性为「有历史区分能力的市场追高环境指数，非独立因果预测指标」。
13. **Balanced 13% > 8.7% 的根因是什么？** C (HRI 有效，但与预测收益/价格水平高相关 → 旧 score 未有效惩罚)；风险分量用「值/100」线性缩放、收益/下行用池内百分位 → 量纲不一致使 HRI 惩罚不区分候选，追高收益盖过跟风惩罚。
14. **最终是否修复？** 是，且已落入**生产代码** `optimization/utility.py`（风险分量统一池内百分位 + balanced 负项提权）。
15. **Final Balanced 高-HRI rate 是多少（生产路径）？** 固定阈值 73.2 下 **0.00%**（修复前 13.04%，Profit-only 8.70%）。
16. **Recommendation 是否优于 Profit-only？** 高-HRI 选中率 0.0% < 8.7%（生产路径，固定阈值）；**untouched 2026** 期 Balanced_fix market_return -0.01 vs Profit_only -0.03（该期为下行期，Balanced 回撤最小）。全期（2024-2026）Balanced_fix 0.02 vs Profit_only 0.01。
17. **在什么指标上优于？** 高-HRI 选中率、downside、untouched 期相对收益（见 POLICY_AND_UNTOUCHED_REPORT）。
18. **在什么指标上不优于？** 全期平均收益不如 Risk_only；与 Random 接近（见 strategy_benchmark / POLICY 报告）——如实说明。
19. **Portfolio 是否有实际价值？** 否（当前数据下）。生产组合优化器最优解收敛单作物（HHI=1.0）→ 已输出正式状态 `NO_DIVERSIFICATION_BENEFIT`。
20. **Stress Test 下哪些方案最稳？** 见 stress_scenarios.csv（base/mild/severe）。
21. **Proxy 对利润模型影响多大？** 蔬菜成本/亩产多为 RESEARCH_REFERENCE 或缺失（见 profit_grading）；利润点估计置信度低，故主指标改用真实价格结果。
22. **Confidence 是否与真实误差一致？** confidence_by_crop.csv 的 price_confidence 由 sample/stability/calibration/beats_baseline 构成；与 WAPE 反向（WAPE 低→confidence 高）。
23. **哪些场景返回 low confidence？** 成本/亩产缺失或 proxy、样本不足、区间未校准、模型未战胜 baseline 的作物。
24. **哪些城市返回 insufficient_market_data？** 大连、铁岭、丹东。
25. **哪些旧 v1/v2 结论被推翻？** 区间 80% 覆盖不足（旧 66–74%）→ 明确降级；Balanced「更强抑制跟风」不成立 → 已修复；hri_inputs 混层不可用于非沈阳。
26. **哪些结论继续成立？** 天气不进价格模型；土豆/甘蓝/芹菜 baseline 胜出；其余 7 作物 ML 有效；HRI 有风险区分力。
27. **Final Model 的局限是什么？** 跨城不可比、蔬菜成本/亩产缺口、区间仅 scenario range、HRI 与价格水平共线、60/90 天误差大。
28. **是否已经可以接 API？** 可以，见 FINAL_MODEL_OUTPUT_SCHEMA.json。
29. **API 应读取哪个模型版本？** `model_version = final_v1`，`data_version = final_v1`。
30. **Final Model 是否可以冻结？** 见 FREEZE_CHECKLIST 与测试/验收结果。
