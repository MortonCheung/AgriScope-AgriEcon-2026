# LLM Forecast Report（Phase 11 + 12）

> `SUPERSEDED_BY_RC2`：保留的 RC1 Stub 链路历史记录，不是 LLM 能力证据。当前状态见 `LLM_REAL_EVALUATION_REPORT.md`。

## 0. 诚实性声明（必读）

**本轮无合法 LLM API Key**（环境中的 IDE token 不得挪用），因此 harness 使用
`deterministic-stub-v1`（**不是 LLM**）跑通全链路。这意味着：

- 下文所有数字均为 **`HARNESS_SMOKE_ONLY`**：验证「pipeline 正确 / 无泄漏 / 可缓存 / 可度量」，
  **不代表任何 LLM 预测能力**；
- **LLM 的数值增益 = 未评估（UNKNOWN）**；在拿到真实 key 并完成 OOT 回测/校准/消融之前，
  LLM **不得**进入正式数值链路（Phase 17 Registry 中一律 `SCENARIO_ONLY`）。

> 生成时间 `2026-10-08 01:08:37`；数据指纹 `f04b01b9b8399c15`；
> provider=`{'provider': 'stub', 'model': 'deterministic-stub-v1', 'is_real_llm': False, 'seed_supported': True}`。

## 1. Pilot 作物（由数据统计选出，非凭印象）

选择规则：低波动 = min `logret_sigma`；高波动 = max `logret_sigma`；季节强 = max `eta2_month`。

**结论：低波动 `土豆` / 高波动 `黄瓜` / 季节强 `青椒`**
（去重后 pilot = ['土豆', '黄瓜', '青椒']）。

| crop | n_obs | mean_price | cv | logret_sigma | eta2_month | acf_365 |
|---|---|---|---|---|---|---|
| 土豆 | 1410 | 2.243 | 0.173 | 0.024 | 0.216 | 0.280 |
| 尖椒 | 1410 | 5.352 | 0.449 | 0.047 | 0.527 | 0.339 |
| 甘蓝 | 1410 | 2.072 | 0.446 | 0.055 | 0.265 | 0.113 |
| 芸豆 | 1410 | 8.783 | 0.259 | 0.045 | 0.438 | 0.348 |
| 芹菜 | 1410 | 3.616 | 0.318 | 0.047 | 0.127 | -0.227 |
| 茄子 | 1410 | 4.013 | 0.404 | 0.053 | 0.486 | 0.373 |
| 西红柿 | 1410 | 5.048 | 0.322 | 0.037 | 0.441 | 0.244 |
| 青椒 | 1410 | 5.831 | 0.438 | 0.045 | 0.642 | 0.487 |
| 韭菜 | 1410 | 5.320 | 0.363 | 0.044 | 0.628 | 0.513 |
| 黄瓜 | 1410 | 4.716 | 0.411 | 0.063 | 0.509 | 0.422 |


## 2. 实验 A：`blind_numeric_forecast`（匿名 + 相对时间索引）

| experiment | horizon | n | llm_WAPE | llm_MAE | llm_sMAPE | baseline_WAPE | delta_WAPE |
|---|---|---|---|---|---|---|---|
| blind_numeric_forecast | 60 | 72 | 19.474 | 0.838 | 16.116 | 19.657 | 0.182 |
| blind_numeric_forecast | 90 | 72 | 23.260 | 0.992 | 19.591 | 23.169 | -0.091 |
| blind_numeric_forecast | 120 | 72 | 29.618 | 1.255 | 24.022 | 29.526 | -0.092 |


## 3. 实验 B：`context_augmented_forecast`（cutoff-safe 上下文）

| experiment | horizon | n | llm_WAPE | llm_MAE | llm_sMAPE | baseline_WAPE | delta_WAPE |
|---|---|---|---|---|---|---|---|
| context_augmented_forecast | 60 | 72 | 19.609 | 0.844 | 16.167 | 19.657 | 0.048 |
| context_augmented_forecast | 90 | 72 | 23.229 | 0.991 | 19.540 | 23.169 | -0.060 |
| context_augmented_forecast | 120 | 72 | 29.562 | 1.253 | 23.973 | 29.526 | -0.036 |


> 实验 A 与 B **分开报告**，**不得**合并成一个 accuracy（§18）。
> 关于 A：blind 只能**缓解**而非消除 pretrained knowledge leakage；
> 关于 B：结论只能表述为「在给定上下文下是否有增量」，不得解读为因果。

## 4. 重复性（同 packet 同模型 ×4）

| repeats | n_ok | point_std | point_cv | direction_unique | range_std | crop | horizon | anchor |
|---|---|---|---|---|---|---|---|---|
| 4 | 4 | 0.000 | 0.000 | ['up'] | 0.000 | 土豆 | 60 | 2024-01-01 |
| 4 | 4 | 0.000 | 0.000 | ['up'] | 0.000 | 黄瓜 | 60 | 2024-01-01 |
| 4 | 4 | 0.000 | 0.000 | ['down'] | 0.000 | 青椒 | 60 | 2024-01-01 |


## 5. 成本与缓存

```
| hits | misses | writes | rejected_writes |
|---|---|---|---|
| 948 | 0 | 0 | 0 |

calls=648  cache_hits=648
```

## 6. 结论

- pipeline 正确、无泄漏（`leakage_passed=True`）、缓存只写通过校验的结果：**PASS**；
- LLM 数值增益：**未评估**（无真实 key）；
- LLM 输出稳定性：见第 4 节（stub 为确定性，`point_std=0`；真实模型需重测）。
