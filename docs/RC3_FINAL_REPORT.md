# AgriScope RC3 最终报告

生成时间：2026-10-08（Asia/Shanghai）
唯一正式仓库：`/Users/morton_cheung/Desktop/比赛/大数据分析/AgriScope`（分支 `feat/llm-real-evaluation-and-deploy`）

## 0. 一句话结论

**真实 LLM 评估已完成**（`REAL_LLM_EVALUATED_RETROSPECTIVE_ONLY`，0 失败）：
- **带 PIT 上下文的 LLM 预测相对基线有稳定增益（平均 +4.62pp，74/96 组更优，60/90/120/150 全档为正）；**
- **匿名盲测 blind 无增益（−4.71pp）；残差调整无增益（−4.21pp）；**
- **Hybrid A/B/C 全部未过门禁 → `HYBRID_NO_GAIN_STATISTICAL_FALLBACK_ACTIVE`；**
- 所有 LLM/Hybrid 数值**停留在 `RESEARCH_ONLY`**，**不进入生产 Registry**（本轮历史为 reused retrospective）。

## 1. 运行事实（可审计）

| 项目 | 值 |
|---|---|
| 权威运行状态 | `REAL_LLM_EVALUATED_RETROSPECTIVE_ONLY` |
| 有效响应 / 失败 | **360 / 0** |
| 权威运行真实调用 / 缓存命中 | 16 / 353 |
| Provider / model | `openai_compatible` / `deepseek-flash`（`is_real_llm=true`，`seed_supported=false`） |
| 平均延迟 | 44–59 s（单次上限 ≤ 约 130 s，超时设 180 s） |
| 本轮累计真实调用 | **356 次**（pass1 294 + pass2 46 + final 16） |
| 本轮累计 token | **5,686,554**（prompt 1,461,776 / completion 4,224,778），费用单价未配置 → `estimated_cost_usd=unknown` |
| 覆盖 | 3 作物 × 4 horizon（60/90/120/150）× 2 target × 4 phase；development 3 anchor、其余 1 anchor |

证据（不提交）：`llm/artifacts/v2/{real_call_records.json, real_metrics.csv, fair_comparison.csv, hybrid_metrics.csv, hybrid_selection_lock.json, ablation_deltas.csv, repeatability.json, outcome_labels.json, real_evaluation_status.json, pilot_plan_frozen.json}`。

## 2. 公平对比（同一 origins / crop / horizon / target / label）

96 组；均值 WAPE（越低越好）：

| 方案 | 平均 WAPE | 相对 baseline 增益 |
|---|---|---|
| baseline（PIT last_value 等） | 16.55 | — |
| statistical（seasonal） | 21.56 | −5.01pp |
| **LLM blind**（匿名） | 21.27 | **−4.71pp** |
| **LLM context**（PIT 上下文） | 11.93 | **+4.62pp** |
| LLM residual | 12.62 | −4.21pp |
| Hybrid A（baseline+残差） | 9.02 | −0.62pp |
| Hybrid B（权重集成） | 15.27 | −2.72pp |
| Hybrid C（regime 门控，退化为 baseline） | 12.55 | 0.00pp |

- **最佳变体优于 baseline 的组合：74 / 96**；最佳变体分布：context 49、blind 25、hybrid_B 9、hybrid_C 8、hybrid_A 4、residual 1。

分维度 context 增益：

| 维度 | 值 | context 增益 |
|---|---|---|
| horizon | H60 | **+7.11pp**（19/24 组更优） |
| horizon | H90 | **+4.24pp**（15/24） |
| horizon | H120 | **+2.89pp**（14/24） |
| horizon | H150 | **+4.25pp**（17/24） |
| crop | 土豆 / 青椒 / 黄瓜 | +4.26 / +7.70 / +1.90 pp |
| target | cycle_market_average | +5.54pp |
| target | harvest_market_price | +3.71pp |

**要点：90/120/150 均有改善**（120 最弱，但为正）；改善不依赖单一作物或单一目标。

## 3. 消融（H90、retrospective phase、每档 n=6，仅作方向性判读）

| 档位 | matched n | 平均预测变化 | paired WAPE 增益 | 来源状态 |
|---|---|---|---|---|
| llm_only | 6 | — | 基准 | PRICE_HISTORY |
| +seasonality | 6 | 10.31% | **+17.34pp** | PRICE_HISTORY |
| +short_model_pit_proxy | 6 | 2.14% | +1.56pp | PIT_RULE_PROXY_NOT_FINAL_MODEL |
| +hri_market_risk | 6 | 3.19% | **−2.82pp** | NOT_FOUND |
| +climate | 6 | 3.21% | −1.52pp | NOT_FOUND |
| +events | 6 | 3.54% | −0.78pp | NOT_FOUND |
| hybrid_full | 6 | 3.54% | +2.11pp | PRICE_HISTORY |

- **seasonality 是主要增益来源**；短模型中位规则有边际正贡献。
- **HRI/Market Risk/climate/events 档位的来源均为 `NOT_FOUND`**，其负增益**不得解释为"来源无效"**——因为根本没有真实来源，只是提示词结构变化；更不得凭"加了一档"宣称来源有效。
- 每档仅 6 个匹配样本，**结论为方向性，不足以定论**。

## 4. 重复性（强制绕过缓存，每作物 3 次）

| 作物 | horizon | repeats | 有效 | 方向一致性 | point_std | range_var |
|---|---|---|---|---|---|---|
| 土豆 | H60 | 3 | 3 | **1.00** | 0.011 | 0.003 |
| 黄瓜 | H60 | 3 | 3 | **1.00** | 0.044 | 0.196 |
| 青椒 | H60 | 3 | 3 | **1.00** | 0.311 | 0.292 |

- **方向判断稳定**（3/3 作物一致性 1.0）；点估计与区间宽度存在一定方差，但可用。

## 5. 结论标签（仅 retrospective）

```json
{
  "llm": "LLM_RETROSPECTIVE_GAIN_OBSERVED",
  "hybrid": "HYBRID_NO_GAIN_STATISTICAL_FALLBACK_ACTIVE",
  "llm_blind_gain_pp": -4.71,
  "llm_context_gain_pp": 4.62,
  "llm_residual_gain_pp": -4.21,
  "hybrid_best_gain_pp": 0.0,
  "note": "RETROSPECTIVE_ONLY_NO_UNTOUCHED; research evidence only, never production-admissible"
}
```

## 6. 门禁与诚实边界（不可越界）

- **无独立样本**：2024–2026 历史已被既有研究查看，`untouched_metric=null`、`final_effective_n=0`。
- **Context 无法完全排除预训练历史知识**；blind 与 context 必须分开报告，本报告未把 context 增益归因为"模型更聪明"。
- **LLM/Hybrid 一律 `RESEARCH_ONLY`**，不进入生产 Registry；后继资格只能来自 2026-10-08 之后成熟标签的 prospective 评估（标 `PROSPECTIVE_VALIDATION_PENDING_BY_TIME`）。
- 未改动任何冻结交付物（Final 冻结指纹 `b19b187268ee92db` 不变；`LONG_HORIZON_V2_ENGINEERING_ACCEPTANCE_PASS`，`untouched_n=0`）。

## 7. 与 RC2 的差异

| 项 | RC2 | RC3 |
|---|---|---|
| 真实 LLM 调用 | 0（Key 缺失） | **356 次真实调用，360 有效响应** |
| LLM 数值结论 | UNKNOWN | **context 有增益 / blind 无增益 / hybrid 无增益（均 retrospective）** |
| 失败可观测性 | 笼统 `LLMUnavailable` | 明确区分 `transport_error` / `method_mismatch` / 截断 / 拒答 |
| prompt 规模 | ≈12.5k tokens | **≈3.5k tokens（压缩约 65%）** |
| 运行工具 | 无单元选择 | CLI 单元选择 + 按 phase anchor + 有界并发 |
| 报告 | RC2 | RC3（含 `fair_comparison.csv` 公平对比表） |

## 8. 未完成项

- **阿里云部署**：SSH 公钥认证被外部阻塞 → 未部署（见 `RC3_DEPLOYMENT_REPORT.md`，含 264 MB 一键部署包与服务器侧验收清单）。
- **资产重冻结**：`runtime/manifest.json` 仍记 RC2 哈希（`RC3_TEST_REPORT.md` 已说明），发布前需运行 `scripts/freeze_runtime_manifest.py`。
- **Git**：未提交、未合并、未打 tag（`v1.0.0-rc3` 未创建）。
- **prospective 验证**：等未来标签成熟，`PROSPECTIVE_VALIDATION_PENDING_BY_TIME`。