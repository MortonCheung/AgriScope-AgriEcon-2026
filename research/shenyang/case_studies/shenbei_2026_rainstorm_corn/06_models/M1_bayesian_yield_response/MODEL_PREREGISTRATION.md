# MODEL_PREREGISTRATION.md — 模型预注册（P3-01）

| 字段 | 值 |
|---|---|
| primary_exposure | `repro_precip_max_5d` |
| selection_reason | 机制（连续强降雨→渍涝）+ 年际变异充足 + 与时间趋势无强共线 + 能表达 2026 极端程度；**未**按拟合优度选择 |
| alternative_exposure | `repro_heavy_rain_days`（仅敏感性） |
| selection_date | 2026-09-22 |
| outcome | 沈北新区玉米单产 corn_yield_kg_ha（2018–2025，n=8） |
| trend_term | time_index（1..8） |
| model_family | 贝叶斯线性（log 单产） |
| priors | S0 Skeptical / S1（方向弱信息，非数值文献先验）/ S2 Wider |
| validation | Exact Leave-One-Year-Out（主要）+ 后验预测检查 + prior 敏感性 |

> **冻结声明**：主指标与模型结构一经登记，**后续不得因结果不理想而更换变量**（S1/S2 仅用于敏感性，不作为“换到满意为止”的通道）。
