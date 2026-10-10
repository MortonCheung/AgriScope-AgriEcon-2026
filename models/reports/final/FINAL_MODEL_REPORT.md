# Final Model Report · AgriScope（穹衡）

- model_version: `final_v1` · data_version: `final_v1`
- 生成时间: 2026-10-07 19:45:00 · 代码指纹: 5a5d68232b747549
- 数据入口: `data/model_ready/`（冻结为 `models/data/snapshots/final_v1`）

## 结论摘要
- **Data**: DATA_AUDIT_PASS（19 表 / 182025 行；无阻断性 P0；1 项已规避缺陷）
- **Leakage**: 截断不变性测试 0 泄漏特征（沈阳/朝阳 × 3 截断点，63 特征）
- **Price Model (h=30, 沈阳)**: 10 作物中 7 个 ML 优于 baseline，3 个 baseline 胜出
- **Interval**: 最优方法 `residual_expanding`，实际覆盖 0.745（名义 0.80）→ 定性为 **scenario_range**
- **HRI**: 12 周(≈90d) 高 HRI 组未来收益显著低于低 HRI 组（沈阳 10 作物中 9 个 p<0.05）
- **HRI vs Market Risk**: Spearman ≈ -0.049（几乎不重叠 → 非重复计风险）
- **Balanced 根因**: C (HRI 有效，但与预测收益/价格水平高相关 → 旧 score 未有效惩罚)
- **独立复算**: 887/887 通过（最大差异 7.11e-15）
- **最终状态**: TRAINED / CALIBRATED / BACKTESTED / VERIFIED / FROZEN

## 支持的城市与作物
| city | tier |
|---|---|
| 沈阳 | full_model |
| 朝阳 | extended_model |
| 锦州 | weak_model |
| 大连 | insufficient_market_data |
| 铁岭 | insufficient_market_data |
| 丹东 | insufficient_market_data |

- 沈阳 10 蔬菜（wholesale）：完整模型
- 朝阳（market_average 单层，8/10 蔬菜有市场均价）：扩展模型（较弱，仅参考）
- 锦州（多 level / OCR）：弱化，不作主模型
- 大连 / 铁岭 / 丹东：`insufficient_market_data`

## 交付物
见本目录全部报告（FINAL_DATA_AUDIT / PRICE_MODEL_REPORT / HRI_VALIDATION_REPORT /
RISK_MODEL_REPORT / RECOMMENDATION_REPORT / BACKTEST_REPORT / ABLATION_REPORT /
ROBUSTNESS_REPORT / OPTIMIZATION_REPORT / FAILED_EXPERIMENTS / FINAL_ANSWERS /
FINAL_MODEL_OUTPUT_SCHEMA.json / FINAL_MODEL_REGISTRY.csv / FINAL_METRICS.csv）。

## Balanced 已知问题（生产路径）已闭环
- 修复前 `C_agriscope_balanced` 高-HRI 选中率 13.04% > `A_profit_only` 8.70%（固定阈值 73.2 下）。
- 修复后（`optimization/utility.py` 风险分量改池内百分位 + 提高负项权重）：**0.00% < 8.70%**。
- 详见 RECOMMENDATION_REPORT.md 的 Before/After 表与 OPTIMIZATION_REPORT.md。
