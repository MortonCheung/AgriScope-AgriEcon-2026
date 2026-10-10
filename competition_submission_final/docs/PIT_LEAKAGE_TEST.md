# PIT_LEAKAGE_TEST — 价格模型前瞻标签泄漏审计与 purge 修复（P0-C）

- 日期：2026-10-10
- 代码：`experiments/code/src/decision_engine/models/`（修复后） vs `experiments/code_prev/src/`（修复前）
- 数据：`final_v1` 冻结快照（沈阳 10 蔬菜）
- 回归测试：`experiments/tests/p0_final_regression.py`（P0-C 用例）
- 结论：**问题成立**；已实施 purge/embargo 并重新训练 30 日价格模型；下游策略结果已按新预测重算。

---

## 1. 问题陈述

目标是 **未来窗口均价**：`target_mean_price_next_{h}d` 取 (t, t+h] 日历天内的价格均值
（`features/build_features.py::add_targets`）。因此该标签的**可获知日期是 t + h**，而不是 t。

修复前的折掩码为（`models/backtest.py::fold_mask`）：

```python
train = d <= pd.Timestamp(fold["train_end"])
test  = (d >= test_start) & (d <= test_end)
```

由此产生两类越界：

1. **训练标签越界（主问题）**：`train_end = 2023-12-31` 时，训练样本 `t = 2023-12-29` 的
   标签窗口为 (2023-12-29, 2024-01-28]，**该标签在训练截止时点尚不可获得，且直接使用了
   测试期（2024-01）的价格**。
2. **测试标签越界**：测试样本 `t = 2024-12-31`（fold1 `test_end`）的标签窗口延伸到 2025-01-30，
   **越入下一个折的测试期**，使折间评估相互污染。

---

## 2. 审计方法

对每个折与每个 horizon h ∈ {7, 14, 30}：

- 训练样本要求标签窗口完全落在训练截止之前：`t + h <= train_end`；
- 测试样本要求标签窗口完全落在测试窗口之内：`t + h <= test_end`；
- 统计修复前后的样本量差异；
- 回归用例直接断言：**(a)** 三折训练/测试样本的前瞻窗口均在边界内；
  **(b)** 所有满足 `train_end - h < t <= train_end` 的样本都被排除。

---

## 3. 审计结果

### 3.1 样本量影响（表：`results/pit/fold_sample_counts.csv`）

| horizon | fold | 训练样本（修复前 → 修复后） | 训练剔除 | 测试样本（修复前 → 修复后） | 测试剔除 |
|---|---|---:|---:|---:|---:|
| 7 | fold1_test2024 | 7 350 → 7 300 | 50 | 2 480 → 2 440 | 40 |
| 7 | fold2_test2025 | 9 830 → 9 790 | 40 | 2 500 → 2 450 | 50 |
| 7 | fold3_test2026 | 12 330 → 12 280 | 50 | 1 750 → 1 700 | 50 |
| 14 | fold1_test2024 | 7 370 → 7 270 | 100 | 2 480 → 2 390 | 90 |
| 14 | fold2_test2025 | 9 850 → 9 760 | 90 | 2 500 → 2 400 | 100 |
| 14 | fold3_test2026 | 12 350 → 12 250 | 100 | 1 750 → 1 650 | 100 |
| **30** | fold1_test2024 | 7 370 → 7 170 | **200** | 2 480 → 2 270 | **210** |
| **30** | fold2_test2025 | 9 850 → 9 640 | **210** | 2 500 → 2 280 | **220** |
| **30** | fold3_test2026 | 12 350 → 12 130 | **220** | 1 690 → 1 540 | **150** |

剔除量约为每折 2%—3%，**样本量影响不大，但性质严重**：被剔除的正是跨越训练/测试边界、
携带测试期价格信息的那批样本。

### 3.2 回归测试结论

| 用例 | 修复前（`code_prev`） | 修复后（`code`） |
|---|---|---|
| P0-C 训练/测试标签 purge | ❌ FAIL：`fold1_test2024 train_max=2023-12-29 +30d 超过 train_end`；`test_max=2024-12-31 +30d 超过 test_end`；三折均越界 | ✅ PASS：三折训练/测试样本前瞻窗口均在边界内，且 `train_end - 30d` 之后的样本全部被剔除 |

---

## 4. 修复实现

`models/backtest.py`：

```python
def target_horizon_days(target: str) -> int:
    return int(str(target).split("next_")[1].split("d")[0])

def fold_mask(df, fold, purge_days=0, embargo_test_tail=True):
    tr_end = pd.Timestamp(fold["train_end"]) - pd.Timedelta(days=int(purge_days))
    train = d <= tr_end
    te_hi = pd.Timestamp(fold["test_end"])
    if embargo_test_tail and purge_days > 0:
        te_hi = te_hi - pd.Timedelta(days=int(purge_days))
    test = (d >= pd.Timestamp(fold["test_start"])) & (d <= te_hi)
```

调用点统一传入 `purge_days = target_horizon_days(target)`：

| 文件 | 位置 | 说明 |
|---|---|---|
| `models/train_price.py` | `run_ml_backtest` | ML 训练/预测 |
| `models/train_price.py` | `baseline_predictions` | 朴素基线 |
| `final/models.py` | `fold_metadata` | 折元数据（`purge=PRIMARY_H`） |
| `final/intervals.py` | `quantile_regression`、`residual_intervals` | 区间校准 |

**注意**：`purge_days=0` 时行为与历史一致，因此该修改是**可选开启**的，便于复现旧结果。

---

## 5. 重训与下游重算

因训练集与评估集改变，**预测与全部下游策略结果均已重算**（未沿用失效数据）：

1. 重训 30 日（及 7/14/60/90 日）价格模型 → 新 `price_predictions.parquet` 与模型选择表；
2. 重算区间校准（`purge_days=h`）；
3. 重算 HRI / Market Risk（不依赖价格模型，仅作一致性复核）；
4. 重算 step7 / step30 全部策略与配对检验。

结果见 `FINAL_RESULTS.md` 与 `experiments/results/validation/`。

---

## 6. 仍存在的结构性局限（未修复，必须写入论文）

1. **模型选择使用同一 OOT 折**：`final/models.py::select_per_horizon` 用测试折的
   `mean_WAPE + 0.5·std_WAPE` 选择最终模型，随后又在同一折上评估策略 → 存在**选择偏差**。
   严格做法是嵌套交叉验证（外层留出年份、内层选择模型）。本轮**未实施**嵌套 CV，
   该偏差会使"预测精度"与"策略表现"被**轻微高估**，论文中必须声明。
2. **超参数调优**（`tuned_params.json`）来源为早前 Optuna 结果，其搜索过程是否使用了相同折
   无法完全确证；本报告将其视为**潜在残余偏差来源**并声明。
3. **标签缺失**：`add_targets` 仅对前瞻窗口完整落于数据范围内的样本生成标签；
   数据末端（2026-09 之后）样本无标签，这是正确的右删失处理，但会减少 fold3 的测试样本。
