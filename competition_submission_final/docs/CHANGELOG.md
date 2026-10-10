# CHANGELOG — 本轮修复与结果变更记录

- 日期：2026-10-10
- 范围：`experiments/`（隔离环境）。**未修改**原 AgriScope 工程、`source_snapshot/`、已冻结的其他实验目录。
- 新增基线目录：`code_prev/src`（本轮修复前的精确回退版本，用于前后对照）

---

## 1. 代码变更

| 文件 | 变更 | 关联问题 |
|---|---|---|
| `final/backtest.py` | `_seasonal_hist` 增加 `label_avail_date = date + h + 1天`；`_seasonal_pick` 改为按 `label_avail_date <= t` 过滤；新增常量 `LABEL_AVAIL_EXTRA_LAG_DAYS` | **P0-A** |
| `final/backtest.py` | `_expectation_rec` 的 `high_hri` 由布尔改为**池内占比**；新增 `stat_type`（expected/realized）；`_rec` 的 `high_hri` 统一为 0/1 浮点 | **P0-B** |
| `models/backtest.py` | `fold_mask` 新增 `purge_days` / `embargo_test_tail`；新增 `target_horizon_days()` | **P0-C** |
| `models/train_price.py` | `run_ml_backtest`、`baseline_predictions` 传入 `purge_days = target_horizon_days(target)` | **P0-C** |
| `final/models.py` | `fold_metadata` 传入 `purge_days=PRIMARY_H` | **P0-C** |
| `final/intervals.py` | `quantile_regression`、`residual_intervals` 传入 `purge_days=h` | **P0-C** |

**回归测试**：`tests/p0_final_regression.py`——**修复前 0/4 通过 → 修复后 4/4 通过**
（证据：`results/p0_final_BEFORE.csv` / `p0_final_AFTER.csv`）

---

## 2. 结果变更（可能影响论文结论）

| 指标 | 修复前 | **修复后（权威）** | 原因 |
|---|---|---|---|
| 回测有效样本（品种×决策日） | 6 670 | **6 090** | P0-C 测试端 embargo |
| step7 / step30 切点数 | 140 / 33 | **128 / 31** | 同上 |
| 价格模型优于基线 | 7/10，改善 2.0%—18.6% | **7/10，改善 2.7%—24.0%** | P0-C 重训 |
| **季节策略 step30 均值** | **+9.26%** | **+4.01%** | P0-A + P0-C |
| 季节策略 step7 均值 | +8.80% | **+7.82%** | P0-A + P0-C |
| **step30 策略 vs 随机（保守校正）** | 2 个策略显著 | **0 个策略显著** | 季节性下降 + 样本变化 |
| step7 策略 vs 随机（保守校正） | 4 个策略显著 | **4 个策略显著** | 保持 |
| 配对差异显著数 | 0/8 | **0/8** | 保持（核心诚实结论） |
| 随机策略高 HRI 命中率 | **100%（错误）** | **池内占比口径（约 10%）** | P0-B |
| HRI 12 周校正后显著 | 5/10 | **5/10** | 不依赖价格模型 |

---

## 3. 被作废/降级的旧结论

1. ❌ **作废**："在不重叠的 33 个切点上，季节策略与最小尾部风险策略显著优于随机"。
   → 修复后在 31 个切点上**无任何策略**通过多重比较校正。
2. ⬇️ **降级**：季节策略的整体表现（step30 均值由 +9.26% 降至 +4.01%）。
3. ❌ **作废**："随机策略的高 HRI 命中率为 100%"（度量错误，已更正为池内占比口径）。
4. ⬇️ **降级**：所有涉及价格预测的下游数值（因 P0-C 重训而整体变化，必须使用新值）。

## 4. 保持不变的结论

1. ✅ 价格预测 **7/10** 品种优于朴素基线。
2. ✅ HRI 与未来 12 周收益存在负向关联，**校正后 5/10 显著**，方向分年一致。
3. ✅ **8/8 重点配对不显著**——复杂预测策略未能显著优于季节策略。
4. ✅ 在 128 个 7 天切点上，四个正向策略显著优于随机基准。
5. ✅ 追高类策略方向性负超额（`Highest_price_level` 在 7 天口径下显著为负）。
6. ✅ "均值最高"与"尾部最稳"不是同一策略。

---

## 5. 新增文件

### `experiments/FINAL_PAPER_VALIDATION/`
- `METHOD_AUDIT.md`、`PIT_LEAKAGE_TEST.md`、`FINAL_RESULTS.md`、
  `FINAL_EVIDENCE_REGISTER.md`、`FIGURE_REGISTER.md`、`CHANGELOG.md`

### `experiments/`
- `code_prev/src`（修复前代码基线）
- `tests/p0_final_regression.py`
- `analysis/figures_final.py`
- `results/B02_pit_fixed/`、`results/validation/{fixed,pre_ab}/`、`results/audit_fixed/`、
  `results/figures_final/`、`results/pit/fold_sample_counts.csv`

### 保留未动
- `results/A00_repro_unpatched/`、`results/B01_fixed/`、`results/strategy_final/`、
  `results/analysis/`、`results/audit/`、`results/figures/`（历史证据，供追溯）

---

## 6. 未完成事项（转为论文声明）

1. **嵌套交叉验证未实施**：模型选择仍使用测试折，残余选择偏差存在。
2. **`tuned_params.json` 调参来源未完全确证**。
3. **无成本/亩产数据**，无法评估经营利润。
4. **HRI 与价格水平共线**，不构成因果。
5. 本轮**只重算沈阳 30 日链路**为主；7/14/60/90 日模型虽同步重训，但论文不作主结论。
