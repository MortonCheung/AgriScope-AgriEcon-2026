# LEAKAGE_VALIDATION — 泄漏验证与可复现性

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
......                                                                   [100%]
6 passed in 5.43s
```

## 3. 结论

- cutoff 可复现性：**通过**；
- 特征全部为 point-in-time；目标仅作标签；
- 天气默认不进入价格模型（见 PRICE_MODEL_REPORT 的 ablation 结果）。
