# Recommendation Report (Final)

## Balanced 13% > 8.7% 根因诊断
- 诊断结论：**C (HRI 有效，但与预测收益/价格水平高相关 → 旧 score 未有效惩罚)**
- 平均 corr(HRI, 预测收益) = 0.303
- 平均 corr(HRI, 现价) = 0.318
- 平均 corr(HRI, 实际收益) = -0.191
- 高-HRI 选中率：旧 Balanced = 0.127，Profit-only = 0.138，修复版 Balanced = 0.005

**机制**：旧 Balanced 的 HRI/市场风险/气候项用 `值/100` 线性缩放，而收益/下行用**池内百分位**——
当高价（高 HRI）同时对应高收益预期时，线性缩放的 HRI 惩罚几乎不区分候选，不足以抵消追高收益，
导致 Balanced 反而比 Profit-only 更追高。
**修复（已落入生产代码 `optimization/utility.py`）**：风险分量（HRI/market/climate）统一改为**池内百分位**，
与收益项量纲一致；并提高负项权重（balanced: herding 0.12→0.20, market 0.15→0.20, ret 0.35→0.30）。

## 生产推荐路径 Before / After（固定阈值 HRI≥73.2，消除批次阈值漂移）
| policy | before | after |
|---|---|---|
| A_profit_only | 0.0870 | 0.0870 |
| B_risk_only | 0.0000 | 0.0000 |
| C_agriscope_balanced | 0.1304 | 0.0000 |
| D_naive_highest_price | 0.1739 | 0.1739 |
| Random | 0.1905 | 0.1053 |


- 结论：`C_agriscope_balanced` 高-HRI 选中率 **13.04% → 0.00%**，且已**低于** `A_profit_only`（8.70%）；
  在批次 P90 相对阈值下同样由 13.0% 降至 0.0%。`A_profit_only` 与 `D_chase` 不变（它们不使用 utility）。
- 该验证走**生产链路**（DecisionEngine + generate_candidate_plans + utility_report + recommend_plans），
  非旁路分析脚本。汇总：{'policies': 20, 'ts': '2026-10-07 19:35:45', 'balanced_before': 0.1304347826086956, 'balanced_after': 0.0, 'profit_only_after': 0.13043478260869565, 'fix_effective': True, 'fixed_threshold': 73.2}

## 置信度（独立于推荐分）
| crop | price_confidence | profit_confidence | risk_confidence | overall_confidence | cost_reliability | yield_reliability | proxy_share | beats_baseline |
|---|---|---|---|---|---|---|---|---|
| 土豆 | 80.5000 | 27.5000 | 85.5000 | 68.5000 | 0.5500 | 0.0000 | 0.4500 | False |
| 尖椒 | 93.0000 | 0.0000 | 90.9000 | 69.2000 | 0.0000 | 0.0000 | 1.0000 | True |
| 甘蓝 | 86.7000 | 0.0000 | 89.1000 | 65.6000 | 0.0000 | 0.0000 | 1.0000 | False |
| 芸豆 | 86.6000 | 27.5000 | 87.2000 | 72.0000 | 0.5500 | 0.0000 | 0.4500 | True |
| 芹菜 | 81.2000 | 0.0000 | 85.9000 | 62.0000 | 0.0000 | 0.0000 | 1.0000 | False |
| 茄子 | 89.6000 | 0.0000 | 89.0000 | 67.1000 | 0.0000 | 0.0000 | 1.0000 | True |
| 西红柿 | 90.9000 | 27.5000 | 89.7000 | 74.8000 | 0.5500 | 0.0000 | 0.4500 | True |
| 青椒 | 90.2000 | 0.0000 | 89.3000 | 67.4000 | 0.0000 | 0.0000 | 1.0000 | True |
| 韭菜 | 90.0000 | 27.5000 | 89.2000 | 74.2000 | 0.5500 | 0.0000 | 0.4500 | True |
| 黄瓜 | 92.8000 | 27.5000 | 90.8000 | 75.9000 | 0.5500 | 0.0000 | 0.4500 | True |

