# MODEL_READY_MATRIX_PHASE4R.md（R18 / §八十七）

> 判定口径：`结构设计 / 代码骨架 / 合成测试 / 真实数据 / 正式验证`。状态：`READY_FOR_CALIBRATION` · `PARTIAL` · `BLOCKED_ON_DATA`。

| 模块 | 结构设计 | 代码骨架 | 合成测试 | 真实数据 | 正式验证 | 状态 |
|---|---|---|---|---|---|---|
| **M2 空间渍涝易感性** | ✅ | ✅（`80–86_p4_*`） | ✅（敏感性/稳定性/置换） | 🟡（DEM/耕地/水系/SAR；**土壤缺、排水不完整**） | 🟡（G1=0、无负样本 → 仅证据区一致性） | **PARTIAL（M2-L2）** |
| **M3 渍涝→损伤** | ✅（`M3_MODEL_CANDIDATES.md`） | ✅（`92_p4r_m3_prebuild.py`） | ✅（单调性/区间/敏感性） | 🟡（文献 8 行：**M3-B 7 / M3-C 1 / M3-A 0**；含全球 meta 分析） | 🔴 | **PARTIAL（文献侧就绪，仍缺 duration + 逐研究方差）** |
| **M4 干预→历时** | ✅（`M4_STATE_EQUATION.md`） | ✅（`m4_water_balance.py` + 3 个测试） | ✅（5 不变量 + 单元测试全通过） | 🔴（泵铭牌/设计排水能力缺） | 🔴 | **BLOCKED_ON_DATA**（缺 `drainage capacity`、`storage/depth`） |
| **Crop State（高频遥感）** | ✅（`CROP_STATE_STUDY_PREREGISTRATION.md`） | ⚪ 待数据 | ⚪ | 🔴 | 🔴 | **BLOCKED_ON_DATA** |
| **Market（事件研究）** | ✅（`MARKET_EVENT_STUDY_PREREGISTRATION.md`） | ⚪ 待数据 | ⚪ | 🔴（玉米批发/零售层级缺） | 🔴 | **BLOCKED_ON_DATA** |
| **Counterfactual（四世界）** | ✅（`COUNTERFACTUAL_WORLD_SPECIFICATION.md`） | ✅（`engine.py`，模块化） | ✅（`test_mc_propagation.py` 全通过，SYNTHETIC） | 🔴 | 🔴 | **BLOCKED_ON_DATA** |

## 汇总
- **可进入“落地校准”的模块数：0**（M2 仍为 L2，只能描述/重建）。
- **结构+代码+合成测试已就绪、仅等数据**：M3、M4、Counterfactual、Crop State、Market → **数据到达即可按 Runbook 直接校准**。
- **最大瓶颈（单点）**：**沈北区级 2026 灾损/田块级受淹标签（G1）** —— 同时卡住 M2→L3、M3、M4、反事实四者。
- **第二大瓶颈**：**积水持续时间（waterlogging duration）的观测或可靠代理** —— 直接决定 M3 能否启动（§九十一）。

## 各模块解锁所需数据（对应 §九十六 第 24–26 问）
| 模块 | 解锁数据 |
|---|---|
| M2 → L3/L4 | 田块级受淹标签或经核验负样本；完整沟渠/泵站；多时相 SAR（多年同期 + σ⁰）；裸地 DEM |
| M3 | 真实 `waterlogging_duration`（D1/D2 级）+ 文献方差 + 春玉米本地试验 |
| M4 | 泵铭牌/型号与流量、设计排水能力、storage/depth 观测 |
| Crop State | NDVI/EVI/SAR/土壤湿度时序（含 2021–2025 同期） |
| Market | 玉米 **farmgate/wholesale/retail** 分级时序 + 成交量 |
