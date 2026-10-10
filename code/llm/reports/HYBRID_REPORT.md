# Hybrid Report（Phase 13）

> `SUPERSEDED_BY_RC2`：保留的 RC1 Stub 链路历史记录，不是 Hybrid 能力证据。当前状态见 `HYBRID_V2_REPORT.md`。

## 0. 诚实性声明（必读）

**本轮无合法 LLM API Key**（环境中的 IDE token 不得挪用），因此 harness 使用
`deterministic-stub-v1`（**不是 LLM**）跑通全链路。这意味着：

- 下文所有数字均为 **`HARNESS_SMOKE_ONLY`**：验证「pipeline 正确 / 无泄漏 / 可缓存 / 可度量」，
  **不代表任何 LLM 预测能力**；
- **LLM 的数值增益 = 未评估（UNKNOWN）**；在拿到真实 key 并完成 OOT 回测/校准/消融之前，
  LLM **不得**进入正式数值链路（Phase 17 Registry 中一律 `SCENARIO_ONLY`）。

> provider=`{'provider': 'stub', 'model': 'deterministic-stub-v1', 'is_real_llm': False, 'seed_supported': True}`；生成时间 `2026-10-08 01:08:37`。

## 1. 残差约束三模式 + Hybrid A/B/C（OOT=fold2/fold3）

| crop | horizon | n_oot | weight_w_on_baseline | dev_wape_at_w | max_adjustment_pct_dev | baseline_WAPE | llm_direct_WAPE | hybrid_B_WAPE | hybrid_A_unbounded_WAPE | hybrid_A_bounded_WAPE | hybrid_A_conf_gated_WAPE | n_residual | hybrid_C_regime_choices | hybrid_C_WAPE |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 土豆 | 60 | 24 | 0.000 | 9.260 | 15.942 | 7.300 | 7.223 | 7.223 | 6.006 | 6.006 | 6.006 | 16 | {'low': 'llm', 'mid': 'baseline', 'high': 'baseline'} | 7.206 |
| 土豆 | 90 | 24 | 0.000 | 9.262 | 18.656 | 8.560 | 8.553 | 8.553 | 8.443 | 8.443 | 8.443 | 16 | {'low': 'llm', 'mid': 'baseline', 'high': 'baseline'} | 8.529 |
| 土豆 | 120 | 24 | 0.000 | 9.129 | 20.906 | 8.715 | 8.601 | 8.601 | 8.407 | 8.407 | 8.407 | 16 | {'low': 'llm', 'mid': 'baseline', 'high': 'baseline'} | 8.707 |
| 黄瓜 | 60 | 24 | 1.000 | 18.432 | 37.004 | 22.424 | 22.508 | 22.424 | 24.537 | 24.537 | 24.537 | 16 | {'low': 'baseline', 'mid': 'baseline', 'high': 'baseline'} | 22.424 |
| 黄瓜 | 90 | 24 | 1.000 | 21.397 | 44.778 | 25.845 | 26.069 | 25.845 | 28.318 | 28.318 | 28.318 | 16 | {'low': 'baseline', 'mid': 'baseline', 'high': 'baseline'} | 25.845 |
| 黄瓜 | 120 | 24 | 0.000 | 22.864 | 58.929 | 28.859 | 28.910 | 28.910 | 31.695 | 31.695 | 31.695 | 16 | {'low': 'baseline', 'mid': 'baseline', 'high': 'llm'} | 29.037 |
| 青椒 | 60 | 24 | 0.000 | 24.243 | 54.822 | 21.687 | 21.542 | 21.542 | 20.026 | 20.026 | 20.026 | 16 | {'low': 'baseline', 'mid': 'baseline', 'high': 'llm'} | 21.583 |
| 青椒 | 90 | 24 | 1.000 | 27.786 | 78.400 | 26.103 | 26.053 | 26.103 | 24.929 | 24.929 | 24.929 | 16 | {'low': 'baseline', 'mid': 'baseline', 'high': 'baseline'} | 26.103 |
| 青椒 | 120 | 24 | 0.000 | 28.931 | 59.825 | 37.413 | 37.489 | 37.489 | 42.114 | 42.114 | 42.114 | 16 | {'low': 'baseline', 'mid': 'llm', 'high': 'llm'} | 37.573 |


## 2. 方法说明

- `max_adjustment` **由 development 段（fold1=2024）的 baseline 残差分布 p90 程序学习**，
  非手写 ±30%（见上表 `max_adjustment_pct_dev`）；
- 残差三模式：`unbounded` / `bounded` / `confidence-gated`（confidence 自报 ≥0.5 才采纳）；
- **Hybrid A** = baseline × (1 + 调整)；**B** = `w·baseline + (1-w)·LLM`，`w` 由 dev 网格搜索最小化 WAPE；
  **C** = 按市场 regime（当前价 expanding 分位三分位）门控，在 dev 上逐 regime 选 baseline/LLM；
- **LLM 无权输出或建议权重**：所有权重与边界均由程序在 dev 上决定（§6.3）。

**重要**：上表任何看似「优于 baseline」的数字（如某些 `hybrid_A_*_WAPE < baseline_WAPE`）
**全部是 stub 确定性抖动带来的噪声，不含任何预测信息**。禁止据此认为 LLM / Hybrid 有增益。

## 3. 结论

- 机制完整：三模式与 A/B/C 均已程序化实现并可复算；
- 权重 `w` 由 dev 逐 (crop,horizon) 网格搜索得到、`max_adjustment` 由 dev 残差 p90 学得 ——
  **LLM 始终无权重决定权**；
- **LLM 的数值增量：未评估**（stub）；因此 **不进入** `PRODUCTION_HYBRID`，一律 `SCENARIO_ONLY`。
