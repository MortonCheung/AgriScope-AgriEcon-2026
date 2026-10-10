# LLM Ablation Report（Phase 16）

> `SUPERSEDED_BY_RC2`：保留的 RC1 Stub 链路历史记录，不是 LLM 能力证据。当前状态见 `LLM_ABLATION_V2_REPORT.md`。

## 0. 诚实性声明（必读）

**本轮无合法 LLM API Key**（环境中的 IDE token 不得挪用），因此 harness 使用
`deterministic-stub-v1`（**不是 LLM**）跑通全链路。这意味着：

- 下文所有数字均为 **`HARNESS_SMOKE_ONLY`**：验证「pipeline 正确 / 无泄漏 / 可缓存 / 可度量」，
  **不代表任何 LLM 预测能力**；
- **LLM 的数值增益 = 未评估（UNKNOWN）**；在拿到真实 key 并完成 OOT 回测/校准/消融之前，
  LLM **不得**进入正式数值链路（Phase 17 Registry 中一律 `SCENARIO_ONLY`）。

> provider=`{'provider': 'stub', 'model': 'deterministic-stub-v1', 'is_real_llm': False, 'seed_supported': True}`；生成时间 `2026-10-08 01:08:37`。

## 1. 消融阶梯（horizon=90，OOT）

| level | n | sections | mean_abs_delta_vs_prev_pct | output_vs_baseline_abs_pct |
|---|---|---|---|---|
| llm_only | 48 |  | nan | 0.762 |
| +seasonality | 48 | seasonality | 0.000 | 0.762 |
| +short_model | 48 | seasonality,short_model | 0.000 | 0.762 |
| +risk | 48 | seasonality,short_model,risk | 0.000 | 0.762 |
| +events | 48 | seasonality,short_model,risk,events | 0.000 | 0.762 |
| hybrid_full | 48 | ALL | 0.000 | 0.762 |


## 2. 「复述输入」检查（§84）

- `output_vs_baseline_abs_pct`：LLM 输出相对统计 baseline 的平均绝对偏差。
  **若该值接近 0**，说明 LLM 只是复述输入（≈Last Value），**不得**进入 Hybrid；
- `mean_abs_delta_vs_prev_pct`：每增加一层上下文的边际变化量（gain source）。

## 3. 结论（程序化判定）

- **消融阶梯的无边际变化（全部 Δ=0.0%）⇒ 当前 provider 的输出与上下文无关**，本表**不能**回答「LLM 到底利用什么」，属 `HARNESS_SMOKE_ONLY`。
- **`output_vs_baseline_abs_pct` < 1% ⇒ 命中「复述输入」风险**：输出几乎等于输入的统计基线，按 §84/§105-C，**不得**把该 provider 接入正式 Hybrid（本轮其本就不接生产）。
- **LLM 到底利用什么 = 未评估（UNKNOWN）**，需真实 key 后重跑本消融。
