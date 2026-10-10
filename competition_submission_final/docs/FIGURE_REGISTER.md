# FIGURE_REGISTER — 论文图表登记（权威版）

- 日期：2026-10-10
- 所有图均由 `analysis/figures_final.py` 从**修复后权威结果**生成：
  `results/figures_final/F1..F4_*.png`
- 生成命令：
  ```bash
  cd 农业建模/experiments && PYTHONHASHSEED=0 python3 analysis/figures_final.py
  ```
- 中文字体：Arial Unicode MS（macOS），已确认无乱码；负号正常显示。

---

## 图清单

| 图号 | 文件名 | 标题 | 数据来源 | 样本 / 范围 | 关键说明 |
|---|---|---|---|---|---|
| 图 4-1 | `F1_hri_by_year.png` | 追高风险指数与未来 12 周收益：分年分组差 | `results/B02_pit_fixed/exports/eval/hri_weekly_沈阳.parquet` | 沈阳 10 品种，2022—2026（2021 为 HRI 预热期，已剔除） | 柱高＝高 HRI 组（≥P80）减低 HRI 组（≤P50）的未来 12 周收益差；柱上标注普通双侧检验 p 值；**各年符号一致为负** |
| 图 7-1 | `F2_strategy_vs_random.png` | 各策略相对均匀随机基准的超额（**主图**） | `results/validation/fixed/compare_vs_random.csv` | 左：128 个 7 天切点；右：31 个 30 天不重叠切点 | 横轴为未来 30 天窗口均价／建仓价 − 1；误差棒为 95% Bootstrap 置信区间；**绿色＝BH-FDR 校正后显著**；(b) 面板全部灰色，如实反映"不重叠口径下无策略显著" |
| 图 7-2 | `F3_high_hri_rate.png` | 各策略"踩入追高环境"的程度 | `results/validation/fixed/strategy_levels.csv` | 同上 | 纵轴为选中高 HRI 作物的比例；**均匀随机选择的期望约为 10%**（由池内 90 分位阈值决定）；`Balanced_fix_v2` 为 0.0%，追涨策略 53%—55% |
| 图 5-1 | `F4_hri_significance.png` | HRI 验证：检验严格度提高后显著数量的衰减 | `results/audit_fixed/H_hri_summary_multiple_testing.csv` | 沈阳 10 品种 × 4/8/12 周 | 三组柱：普通双侧检验 / 块 Bootstrap+HAC 同时显著 / **BH-FDR 校正后仍显著**；12 周由 9 → 7 → 5 |

---

## 表清单（论文用）

| 表号 | 表名 | 数据来源 |
|---|---|---|
| 表 2-1 | 数据构成与样本量 | `results/audit_fixed/A_panel_identity.csv`、`PIT_LEAKAGE_TEST.md` |
| 表 2-2 | 数据质量审计摘要 | `results/B02_pit_fixed/exports/manifests/leakage_*.csv` |
| 表 3-1 | 季节强度与趋势检验 | `research/shenyang/A01/` ⚠️ 未独立复算 |
| 表 4-1 | 十种蔬菜 30 天窗口预测精度 | `results/audit_fixed/I_forecast_accuracy_h30.csv` |
| 表 5-1 | HRI 分组检验与多重检验校正 | `results/audit_fixed/H_hri_summary_multiple_testing.csv` |
| 表 6-1 | 策略定义与口径 | 方法定义（`final/backtest.py::STRATS`） |
| 表 7-1 | 策略水平与风险指标（step7） | `results/validation/fixed/strategy_levels.csv` |
| 表 7-2 | 策略水平与风险指标（step30） | 同上 |
| 表 7-3 | 策略相对随机基准的超额与显著性 | `results/validation/fixed/compare_vs_random.csv` |
| 表 7-4 | 重点配对差异 | `results/validation/fixed/compare_pairs.csv` |
| 表 7-5 | 随机基准多种子实现分布 | `results/audit_fixed/C_random_multiseed_step{7,30}.csv` |
| 表 8-1 | 分年度策略表现 | `results/audit_fixed/G_by_year_new_step30.csv` |
| 表 8-2 | 基线定义修正对照 | `results/audit_fixed/B_same_sample_formula_summary.csv` |

---

## 图表质量自检

| 检查项 | 结论 |
|---|---|
| 数据与最终结果一致 | ✅ 全部由 `results/validation/fixed` 与 `results/audit_fixed` 生成 |
| 单位明确 | ✅ 纵轴/横轴均标注"未来 30 天窗口均价/建仓价 − 1"或"元/公斤"派生量 |
| 样本量与时间范围明确 | ✅ 图题或图内标注切点数与品种数 |
| 中文无乱码 | ✅ 已人工目视核验 |
| 置信区间有说明 | ✅ 图题标注 95% Bootstrap 区间 |
| 未夸大不显著差异 | ✅ (b) 面板统一使用灰色标识非显著；不显著结果不画显著性标记 |
| 未沿用被推翻的旧图 | ✅ 旧 `results/figures/` 已弃用，论文一律引用 `figures_final/` |
| 图号与正文引用一致 | ✅ 见上表"图号"列 |
