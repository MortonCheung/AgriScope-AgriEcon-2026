# M2_BASELINE_SPEC.md（P4-16/49/50）

## 方案选择
采用 **方案1（机制方向 + 简单等权）** 为主，另给 **方案2（依证据点差异透明校准）** 作变体。

## 物理易感性 Baseline（M2a / susceptibility）
对参与变量标准化后，按**机制方向**取等权平均，再取百分位→[0,1]：
```
susceptibility_raw = mean( sign_v * z(v) )    # sign 见 M2_VARIABLE_CAUSAL_ROLE 的机制表
susceptibility     = percentile_rank(susceptibility_raw)
```
- 方向：高程↓、坡度↓、局部起伏↓、洼深↑、汇流↑、HAND↓、TWI↑、到水系/排水距离↑  → 更易涝
- **权重未凭感觉设定**：等权 + 机制方向；校准变体权重 = |z_diff(证据点邻域−背景)| 归一化（可复现）

## 2026 事件暴露（Layer B）
`event_exposure` = z(event_precip) + z(antecedent_14d)；**本轮为单 ERA5 网格点 → event-wide forcing**，
空间差异不来自降雨，而来自地形/水文/排水（诚实说明，§23）。

## 观测证据（Layer C）
- `sar_anomaly`：`delta_vv_pct` ≤ 其 P10（显著后向散射下降）；**无历史对照、未定标 → 仅“异常证据”**
- `evidence_proximity_score` = exp(−dist_to_nearest_reported_flood / 5km)

## M2R 重建（三层融合）
```
M2R_risk = percentile_rank( 0.50*susceptibility + 0.15*event_exposure_rank
                          + 0.15*sar_anomaly    + 0.20*evidence_proximity )
```
风险分级：Low/Moderate/High/VeryHigh（按分位）。
置信度：地形可用(0.4) + SAR异常(0.3) + 靠近地面证据(0.3) − 排水网络不完整(0.2)。

> **权重为透明设定，非拟合**；这是 Route A 的“物理启发 + 证据叠加”，**不是监督模型**。
