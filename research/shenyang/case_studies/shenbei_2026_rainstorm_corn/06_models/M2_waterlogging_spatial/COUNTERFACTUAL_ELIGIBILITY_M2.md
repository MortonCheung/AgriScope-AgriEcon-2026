# COUNTERFACTUAL_ELIGIBILITY_M2.md（P4-72/73/74）

| Gate | 检查 | 结果 |
|---|---|---|
| A 地形/水系数据质量 | DEM 覆盖>95% = True；**排水网络不完整** | **PASS**（地形部分） |
| B 方向符合机制 | 方向一致变量占比 90% | **PASS** |
| C 与真实受淹点一致 | 已知正样本邻域召回 = 0.50 | **CAUTION** |
| D 与独立遥感证据一致 | ρ(易感性, ΔVV)=0.050, p=0.0000 | **CAUTION** |
| E 空间验证 | 无 G1 标签，仅邻域一致性 | **CAUTION** |
| F 无 post-event leakage | 预测输入仅 PRE-EVENT+EVENT | **PASS（预测输入已剔除 POST-EVENT：SAR/地面证据/干预只用于重建与验证）** |

## 总判定：**ELIGIBLE_FOR_DESCRIPTION_ONLY**

依据 §74：M2 **只能用于描述/重建 2026 事件**，**不能**用于 `future rainfall scenario` / `no-disaster world` 的定量反事实。
