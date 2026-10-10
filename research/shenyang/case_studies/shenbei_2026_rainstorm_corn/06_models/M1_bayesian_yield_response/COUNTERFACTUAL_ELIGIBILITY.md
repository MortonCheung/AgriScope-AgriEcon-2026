# COUNTERFACTUAL_ELIGIBILITY.md（P3-14）

| Gate | 检查 | 结果 |
|---|---|---|
| A 收敛 | 最大 R-hat=1.0067；最小 bulk ESS=573 | **PASS** |
| B 后验预测 | 观测被 95% 预测区间覆盖比例=1.00 | **PASS** |
| C LOYO | ΔMAE=+10.6；ΔRMSE=+27.2；ΔlogPD=-0.082（M1−M0） | **FAIL** |
| D 先验敏感性 | β_R 中位数跨先验极差=0.0058；P(<0)区间=[0.78,0.82]；方向反转=False | **PASS** |
| E 2026 外推 | ZR_2026=4.25 SD | **STRONG_EXTRAPOLATION** |
| F 机制 | 主变量=`repro_precip_max_5d`（降雨暴露） | **CAUTION (变量=降雨暴露，不能代表 waterlogging)** |

## 总判定：**NOT_ELIGIBLE**

依据规格 §48/§76：**Gate C 失败**（加入降雨后跨年预测不改善、反而变差）且 **Gate E 为强外推** → 属“情况 C”，**M1′ 不具备正式反事实资格**。
