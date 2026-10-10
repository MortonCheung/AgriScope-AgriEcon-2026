# TERMINOLOGY_CORRECTION_PHASE4R.md（§九/§十 术语纠正）

> 依据 Phase 4R 审计，对 M2 输出的**命名与解释**做强制纠正。**不修改**任何 Data Agent 目录；本文件为本轮新产物。

## 1. 风险等级的真实生成方式（法医结论）
`M2R_risk` 与其分级 `risk_class` 的生成链条为：
```
M2R_risk   = percentile_rank( 0.50*susceptibility + 0.15*event_exposure_rank
                            + 0.15*sar_anomaly    + 0.20*evidence_proximity )
risk_class = pd.cut( M2R_risk, bins=[0, 0.50, 0.80, 0.95, 1.01],
                     labels=[Low, Moderate, High, VeryHigh] )
```
**阈值来自 `percentile_rank`（相对排名分位）**，即：
- Low = 排名 0–50%
- Moderate = 50–80%
- High = 80–95%
- VeryHigh = >95%

## 2. 因此它不是概率
❌ 禁止：把 “VeryHigh” 说成“发生积水概率 95%”
❌ 禁止：使用 `probability`、`risk probability`、`淹没概率` 等词
✅ 应使用：**`susceptibility score`（易涝性得分）** 或 **`relative waterlogging susceptibility`（相对渍涝易感性）**
✅ 分级应表述为：**相对易感性等级**（top 5% / 20% / 50% 的分位分组）

## 3. 对 Phase 4 报告的术语映射（不重写历史，仅加注）
| Phase 4 用词 | 规范用词 |
|---|---|
| 风险 Risk / M2R_risk | **relative waterlogging susceptibility（相对渍涝易感性）** |
| risk_class = VeryHigh | **susceptibility class = top 5%（相对）** |
| 高风险区 | **高易感区（相对排名前 5%/20%）** |
| confidence | 置信度（保持不变，但与易感性**分开**表达） |

## 4. 其它必须随引用一并声明的口径
1. 边界为 **public administrative boundary representation**（DataV），非官方法定边界；
2. 降雨为**单 ERA5 网格点 event-wide forcing**，无空间差异；
3. `delta_vv_pct` 为**未定标、无历史对照**的 SAR 相对变化 → 仅“异常证据”；
4. 排水网络 **严重不完整**（OSM 排水沟 1 条）→ 变量名 `dist_mapped_*`；
5. 耕地掩膜来自 **WorldCover 2021（单年，整体精度≈76.7%）**；
6. 土壤 **not_available**；
7. 空间单元为 100m 耕地网格；**空间自相关强 → 单元数 ≠ 独立样本数**（§二十二）。
