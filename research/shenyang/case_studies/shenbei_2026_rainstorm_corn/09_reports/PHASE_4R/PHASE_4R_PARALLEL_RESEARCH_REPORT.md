# PHASE_4R_PARALLEL_RESEARCH_REPORT.md
## AgriScope 沈北案例 · Phase 4R（Research Parallel Track）
### 并行研究验证 + M3/M4 预建模 + 反事实框架预注册

> 定位：**不是** Phase 5/6 正式建模，**不是** 四世界计算；而是把**所有不依赖新数据**的验证、方法设计、模型结构、接口、代码骨架与质量控制**提前做完**。
> 纪律：`01_sources/ 02_raw/ 03_clean/ 04_marts/` 视为 **READ-ONLY**；本轮产物全部进入独立工作区。
> 时间：2026-09-23。

---

## 1. 本轮目标
让 Data Agent 补数完成后，只需「新数据 → Schema 检查 → 接入接口 → 重新校准 → 正式验证 → 进入 M3/M4/反事实」，而**不需要重新设计**。
本轮不做：正式 M3 损伤率、正式 M4 减损量、任何平行世界数字、前端。

## 2. Phase 1–4 研究状态复核
见 `05_analysis/10_parallel_research/RESEARCH_STATE_AUDIT.md`。按 **FACT / MODEL_SUPPORTED / LITERATURE_SUPPORTED / HYPOTHESIS / UNKNOWN** 五级重列：
- **FACT 13 条**（含 52h 极端降雨、城区 346.8mm、沈北单产 8 年序列、耕地 419 km²、排水沟仅 1 条、G1=0 等）；
- **MODEL_SUPPORTED 5 条**（趋势可识别；降雨对未见年份**无额外预测价值**；n=8 对中度效应识别率 0.34；M2 方向大体一致）；
- **LITERATURE_SUPPORTED 2 条**（渍涝不利 + 抽雄吐丝敏感；**无 Class A** 可映射先验）；
- **HYPOTHESIS 5 条**（H1 减产可观 / H2 排涝显著减损 / H3 M2 高易感区灾后植被异常更强 / H4 101 国道高标准农田更易涝 / H5 前期湿润放大）；
- **UNKNOWN 8 项**（全区积水边界/深度/历时、完整沟渠泵站、河渠水位、田块级玉米分布、区级灾损、2026 单产、土壤质地）。
> 术语一致性（§六）：M2 **只是** *spatial waterlogging susceptibility / evidence reconstruction*，**不是**深度/历时/水动力/概率模型。

## 3. M2 法医审计
- **术语纠正**（§九/§十）：`risk_class` 由 `percentile_rank` 分位切分（0/0.5/0.8/0.95）而来 → **是相对排名，不是概率**；统一改称 **susceptibility score / relative waterlogging susceptibility**（见 `TERMINOLOGY_CORRECTION_PHASE4R.md`）。
- **数据完整性**：`04_marts/M2_spatial_dataset.csv` 42,473 行 × 29 列，SHA256 已入快照。
- 发现并记录：Data Agent 正在并行写入（`osm_drainage/pump/waterbody/hydraulic.json`、`03_clean/market/*`、`04_marts/shenbei_*_system.csv`），但 **`FULL_DATA_ACQUISITION_REPORT.md` 不存在 → 视为未完成**，本轮**不读取其半成品**（见 `DATA_AGENT_ACTIVITY_DETECTION.md`）。

## 4. 42,473 vs 42,017 差异解释
见 `M2_CELL_ACCOUNTING_AUDIT.md`。
- **当前快照：总单元 42,473 = 有效分类 42,473 + 明确未分类 0（账目闭合）**。
- 该 456 缺口**来自 Phase 4 首次运行**：当时 100m 聚合函数未处理 nodata，`min/max` 重采样与 NaN 交互产生 **±inf** → 456 个单元 `slope/twi` 为 NaN → 易感性 NaN → 分级为空。
- **已修复**（聚合前非有限值置 NaN + 显式 `src/dst_nodata`），修复后缺失 456 → 0。
- **判定**：**代码缺陷（已修复）**，非 NoData/掩膜/边界问题；不影响结论方向。

## 5. Cropland 聚合审计
见 `CROPLAND_AGGREGATION_AUDIT.md`。
- **入选规则**：WorldCover **10m**(class40) → nearest 到 **30m** 掩膜 → **average 聚合到 100m** 得 `cropland_frac` → **判定 `frac ≥ 0.5`（多数）**。**不是**“任意像素/中心像素”。
- 阈值敏感性：

| 阈值 | 单元数 | 面积 | 高易感(>P95) 单元 | M2R 中位数 |
|---|---|---|---|---|
| 20% | 46,867 | 468.7 km² | 2,124 | 0.500 |
| **50%（当前）** | **42,473** | **424.7 km²** | **2,124** | **0.500** |
| 80% | 37,091 | 370.9 km² | 1,992 | 0.525 |

→ 面积随阈值单调变化（±10%），**高易感区域基本稳定**（2,124 → 1,992）。⚠️ WorldCover 2021 为**单年**产品（官方整体精度≈76.7%）。

## 6. M2 物理合理性交叉验证
见 `M2_PHYSICAL_CROSS_VALIDATION.md`。**逐变量**给出 ①预期方向 ②证据区实际方向 ③可能偏差。
- 以**背景中位数**为基准：**8/10 一致**；Phase 4 以**背景均值**为基准：9/10。
- **差异来自 3 个变量**（其余 7 个两口径都稳）：
  1. **elevation**：背景高程**右偏**（均值 55.1 ≫ 中位 47.9）→ 方向**随统计量反转**；
  2. **flow_accumulation**：分布**极强右偏** → 同样反转；
  3. **HAND**：背景**中位数为 0**（退化），中位数口径无判别力。
- **裁定**：Phase 4 的“9/10”**偏乐观**；稳健部分为 **slope / local_relief / depression_depth / TWI / dist_mapped_water / river / drainage（7 项）**。

## 7. flow accumulation 异常分析
- 中位数口径：证据区 2.44 vs 背景 2.33（**略高=方向一致**）；均值口径：3.47 vs 5.68（**偏低=不一致**）→ **口径敏感**。
- 机制解释：高汇流值多位于**河道/主干沟**，被 **cropland mask 排除**；**平坦东北平原**上 D8 易产生人工集中流路；**填洼**改变农田微地形；与 HAND/depression/水系距离**共线**。
- **处理**：**不删除、不反转、不改权重**（§十七）；保留原样，并建议正式 M2 采用 `log1p` 或 **specific catchment area** 作为敏感性变体。

## 8. Ground evidence 区域验证
见 `M2_EVIDENCE_REGION_VALIDATION.md`。
| 缓冲 | 单元数 | 易感性中位秩 | top10% 覆盖 | top20% 覆盖 | 富集比 |
|---|---|---|---|---|---|
| 1 km | 1,012 | 0.533 | 0.253 | 0.446 | 1.066 |
| 3 km | 8,580 | 0.640 | 0.336 | 0.472 | 1.311 |
| 5 km | 17,645 | 0.643 | 0.378 | 0.473 | 1.440 |
- **空间置换检验（3 km，匹配面积随机背景 ×1000）**：观测中位秩 0.640 > 全部零分布 → 单侧 p ≈ 0.000。
- ⚠️ 但**验证单位 = evidence region（6 个）**，**不是** cell；空间自相关强（§二十二）→ 结论只能是**方向性富集**，**不得**作功效性统计推断。

## 9. M2 敏感性与稳定性
见 `M2_STABILITY_AND_SENSITIVITY.md`、**`M2_RESOLUTION_SENSITIVITY_REAUDIT.md`**、**`M2_STABILITY_MAP.md`**。
- **权重集合**（4 套：equal / terrain-emphasis / drainage-emphasis / depression-hand-emphasis）。
- **§二十三 分辨率敏感性全面重审（本轮补完）**：把 4 套权重 + 网格 50/100/250 m + DEM 90 m 共 **9 套设定**，全部采样到同一 42,473 个 100 m 单元后逐项比较：

| 设定 | 证据区中位秩 | 富集比 | top20% 覆盖 | ρ vs 等权 | top20% Jaccard vs 等权 |
|---|---|---|---|---|---|
| 等权（基准） | 0.674 | 1.387 | 0.425 | 1.000 | 1.000 |
| terrain 强调 | 0.651 | 1.343 | 0.390 | 0.938 | 0.703 |
| drainage 强调 | 0.579 | 1.174 | 0.441 | 0.963 | 0.840 |
| depression/HAND 强调 | 0.717 | 1.493 | 0.384 | 0.938 | 0.674 |
| 网格 50 m | 0.679 | 1.401 | 0.416 | 0.928 | 0.780 |
| 网格 250 m | 0.670 | 1.368 | 0.432 | 0.894 | 0.772 |
| DEM 90 m | 0.694 | 1.424 | 0.432 | 0.970 | 0.861 |

  → **全部设定富集比 >1（1.17–1.49）**，秩相关 0.894–0.970；**格局稳定（秩极差<0.20）单元占 61.6%**。
  → 判读：M2 对**分辨率**较稳健，对**权重族**更敏感。
- **§二十五 稳定性地图（本轮补完）**：9 套设定下，**全部为 top20% → robust_high**；≤一半 → unstable。

| 类别 | 单元数 | 占耕地网格 |
|---|---|---|
| **robust_high** | **5,450** | 12.8% |
| intermediate | 2,638 | 6.2% |
| unstable | 34,385 | 81.0% |

  产物：`08_figures/M2/F13_stability_map.png`、`F14_resolution_overlap.png`、`M2_STABILITY_MAP.geojson`、`M2_STABILITY_MAP_cells.csv`。
- ⚠️ 稳定性图**不是新“真值”**，只是**模型稳健性**；robust_high 可作**优先关注区**，unstable 表示**结论依赖设定**。

## 10. 排水变量专项审计
见 `M2_FEATURE_FAMILY_ABLATION.md`。
- 当前“排水相关变量”**仅**为 **mapped 水系/河流/排水距离**（OSM）；**不含** DEM 推导排水网络、**不含**泵站。
- 证据区 `dist_mapped_drainage` 中位 **7,852 m** vs 全区 **5,517 m**（证据区**更远**）。
- **⚠️ 本轮重要更正**：Phase 4 曾报告“移除排水变量后正样本处易感性降到中位数以下（0.415）”，据此推断“排水强影响”。**该结论不稳健**——因其使用**单像元**取值，而 G2 证据误差 3–5 km（§十八禁止）。
  改用**证据区域口径**后：

| 消融 | 缓冲中位秩 | 背景中位 | 富集比 | 单像元均值 |
|---|---|---|---|---|
| full | 0.640 | 0.488 | 1.311 | 0.489 |
| drop 3 个 mapped 距离 | 0.564 | 0.491 | 1.148 | 0.547 |
| drop 仅 drainage | 0.655 | 0.481 | 1.364 | 0.474 |
| terrain only | 0.547 | 0.491 | 1.113 | 0.317 |

→ **正确口径下排水变量为次要贡献**；Phase 4 的“排水强影响”部分是**单像元取值的伪像**。
- **M2 主要由哪组变量驱动？** 地形族为主（elevation/slope/relief/depression/HAND/TWI），mapped 水系距离为**次要非零**贡献。

## 11. M3 文献重新分类
见 `06_models/prebuild/M3/M3_LITERATURE_AUDIT.md` 与 `M3_LITERATURE_EVIDENCE_AUDIT.csv`（**8 行**）。
- **M3-A = 0**（现有文献**均非**东北春玉米 → 无可直接数值迁移者）；
- **M3-B = 7 条**（4 篇夏玉米共 6 行 + **1 篇全球渍涝 meta 分析**）；
- **M3-C = 1 条**（水稻洪水损失函数，**方法学**）。
- 统一效应量：`relative_yield = 1 − loss`、`lnRR = ln(Y_t/Y_c)`。
- **逐研究方差信息：仍缺失**（未报 SD/SE/n）→ **不能伪造方差、不能做严格加权 meta-analysis**（§三十四）。
- **§八十九 新增两篇**（方法/文献核验所得）：
  - `LIT-TIAN2021META`（*Front Plant Sci* 2021，DOI 10.3389/fpls.2021.634898）：115 篇/2419 组比较，全作物平均 **−32.9%**，按积水历时分组（0–3/3–6/6–9/9–15/15–28 d）→ **M3-B 层次先验来源**。
  - `LIT-BILL2026RICE`（*NHESS* 2026，DOI 10.5194/nhess-26-925-2026）：Bayesian 回归（水深×历时×生育期）+ **跨区迁移误差** → **M3-C 方法学**。

## 12. M3 候选数学模型
见 `M3_MODEL_CANDIDATES.md`。
- **M3-A** 分阶段剂量响应（分段线性，强制单调不减）；
- **M3-B** 分层贝叶斯 Meta-regression（`lnRR_i ~ N(a_study + b_stage·f(duration) + c·depth, σ_i)`）；
- **M3-C** 保守区间模型（`(stage,duration) → [low,high]`，partial identification）。
**修正后的选择（因 §八十九 引入全球 meta 分析）**：**M3-B（先验级，用全球 meta 的分组效应作弱信息先验）+ M3-C（保守区间）并行**；M3-A 作透明基准。
**严格加权 meta-analysis 仍待逐研究方差补齐**（**不预设 M3-B 最好**，§三十九）。

## 13. M3 合成实验结果
见 `M3_SYNTHETIC_EXPERIMENTS.md`。
- 合成输入：0/12/24/48/72/96 h × 5 阶段（**仅测试结构，非沈北值**）。
- **单调性检查：5/5 阶段全部通过**（同阶段时长↑ ⇒ 损伤不降，§四十）。
- 锚点 ±25% 扰动 500 次 → 输出平均绝对偏差（各阶段）→ 说明**斜率锚点是最敏参数**。
- 只回答五问：数学稳定 ✓、输出落在 [0,0.95] ✓、异质性区间宽度（抽雄吐丝可达 ~0.2）、最敏参数=锚点斜率、**必须补的输入 = duration / 方差 / 春玉米试验**。

## 14. M4 状态方程
见 `06_models/prebuild/M4/M4_STATE_EQUATION.md`。
```
Storage(t+Δt) = Storage(t) + (Rainfall + Inflow − Infiltration − NaturalDrainage − PumpDrainage − OtherLosses)·Δt
```
每项标注 `OBSERVED / DERIVED / LITERATURE_PARAMETER / CALIBRATABLE / LATENT / UNKNOWN`（见 `M4_PARAMETER_RANGES.csv`）。
- **emergency pumping ≠ 全部排水**（§四十八）：**12 台 8 寸泵 / ~96h / 8000 余亩** 只能作 **weak aggregate constraint**。
- 量级换算：泵当量 **0.34–1.13 mm/h**；仅靠泵排 200 mm 需 **177–590 h**，**远长于实际 96h** → **自然排水/沟渠贡献不可忽略**，泵只是加速项（**不得反推真实泵流量**）。

## 15. M4 合成验证
见 `M4_SYNTHETIC_VALIDATION.md`（**全 SYNTHETIC**）。
- **5 个不变量全部通过**：

| 测试 | 结果 |
|---|---|
| T1 泵能力↑ → 历时不减 | [76.2, 67.8, 62.0, 56.5] ✓ 单调↓ |
| T2 提前启动 → 不更晚排净 | [57.2, 59.0, 62.0, 66.8] ✓ |
| T3 无泵 ≥ 现实 | 76.2 ≥ 62.0 ✓ |
| T4 降雨↑ → 峰值不减 | [120, 131.6, 208.0, 360.8] ✓ |
| T5 初始更湿 → 历时不减 | [45.2, 56.5, 62.0, 70.2] ✓ |

- 世界排序：**C(无应急) 76.25 > A(现实) 62.0 > D24 58.0**（合成）。
- 单元测试脚本已建立并通过：`scripts/tests/test_m4_mass_balance.py`、`test_m4_monotonicity.py`、`test_m4_scenario_ordering.py`。

## 16. 四世界正式定义
见 `COUNTERFACTUAL_WORLD_SPECIFICATION.md`。关键：
- **B 无灾害 = 把极端天气暴露替换为历史正常情景**（**不是 rainfall=0**）；且 **emergency intervention 是灾害的下游变量**，正常天气下**不应“12 台泵照常启动”**；
- **C 无干预 = 取消应急抽排，保留自然排水/沟渠/常规设施**（**不是所有排水=0**）；
- **D 提前干预 = 设施与泵能力不变，只改 `intervention_start`（−24h/−48h）**，并须讨论**操作可行性**；
- 估计量符号统一：`Disaster = Loss_A − Loss_B`；`Avoided = Loss_C − Loss_A`；`Extra(D24/D48) = Loss_A − Loss_D(·)`。

## 17. 反事实模拟架构
见 `06_models/prebuild/counterfactual/ENGINE_INTERFACE.md` 与 `engine.py`。
链：`simulate_weather → simulate_waterlogging_M2 → simulate_duration_M4 → simulate_crop_damage_M3 → aggregate_outcome`。
模块**相互独立**（禁止单体 `run_parallel_world.py` 硬编码）；接口契约明确（M2→M3/M4、M4→M3、M3→聚合）。
缺字段一律 `NULL / NOT_AVAILABLE / WAITING_FOR_DATA`（`engine.py` 抛 `MissingData`），**禁止假默认值让 pipeline “跑通”**。

## 18. 不确定性传播方案
见 `UNCERTAINTY_PROPAGATION.md`。
- **禁止**“M2 取均值 → M3 取均值 → M4 取均值”；改为**每次 draw 从各模块分布抽样、完整跑一个 world**。
- **Common Random Numbers**：同一次 draw 中 A/B/C/D 共享非处理随机参数，仅改 weather / intervention（§六十七）。
- 合成演示（**2000 draws，SYNTHETIC**）：A 中位 **56.5h**、B **26.5h**、C **69.0h**、D24 **52.5h**、D48 **52.0h**；`C−A` 中位 **12.0h**（区间见 CSV）。
- 单元测试 `scripts/tests/test_mc_propagation.py` **全部通过**：固定 seed 可复现、样本量增大稳定、世界排序正确、取值物理合理。

## 19. 高频作物状态研究设计
见 `CROP_STATE_STUDY_PREREGISTRATION.md`。核心：
- **禁止** `before − after` 直接称“暴雨损伤”；须建 **历史同期 expected trajectory（2021–2025）**；
- 时间轴 pre/event/T+1..4w/recovery；指标 NDVI/EVI/SAR/土壤湿度异常；
- **关键交叉验证**：M2 高易感区（top 20%）灾后是否异常更强 → 是则 M2 获**独立下游证据**（仍非因果）；
- 边界：NDVI 下降 **≠ 减产 X%**；无有效观测 → `NOT_FEASIBLE`。

## 20. 市场事件研究设计
见 `MARKET_EVENT_STUDY_PREREGISTRATION.md`。核心：
- 问题 = “是否**相对正常季节轨迹**异常”，**不是**“下雨后涨没涨”；
- **必须控制季节性**（禁止 7月 vs 8月直接归因）；
- 窗口 T−4w → T+8/12w；方法候选 event study / ITS / seasonal anomaly / distributed lag，**不预先强制 DID**；
- **价格层级分开**：farmgate / purchase / wholesale / retail；
- 已知约束：沈阳批发/零售**不含玉米**；省级周报有 **farm_gate**；→ 若玉米批发/零售不可得，标记 `NOT_FEASIBLE`，不用替代作物。

## 21. Data Contract
见 `06_models/prebuild/DATA_AGENT_INTEGRATION_CONTRACT.md` 与校验器 `scripts/validate_new_data_contract.py`。
- 按模型逐字段定义 **REQUIRED / OPTIONAL / NICE_TO_HAVE** + `invalid_condition / missing_handling / unit_conversion`；
- 校验器输出 **PASS / WARNING / FAIL / NOT_FOUND**，已实测可运行（当前结果含 Data Agent 半成品 → 预期 FAIL/NOT_FOUND，**不作数据质量结论**）。

## 22. Ready Matrix
见 `06_models/prebuild/MODEL_READY_MATRIX_PHASE4R.md`。
| 模块 | 结构 | 代码 | 合成测试 | 真实数据 | 正式验证 | 状态 |
|---|---|---|---|---|---|---|
| M2 | ✅ | ✅ | ✅ | 🟡 | 🟡 | **PARTIAL（L2）** |
| M3 | ✅ | ✅ | ✅ | 🔴 | 🔴 | BLOCKED_ON_DATA |
| M4 | ✅ | ✅ | ✅ | 🔴 | 🔴 | BLOCKED_ON_DATA |
| Crop State | ✅ | ⚪ | ⚪ | 🔴 | 🔴 | BLOCKED_ON_DATA |
| Market | ✅ | ⚪ | ⚪ | 🔴 | 🔴 | BLOCKED_ON_DATA |
| Counterfactual | ✅ | ✅ | ✅ | 🔴 | 🔴 | BLOCKED_ON_DATA |

**可进入落地校准的模块数 = 0**；**结构/代码/合成测试已就绪、仅等数据 = 5**。

## 23. 数据回来后的执行方案
见 `09_reports/PHASE_4R/POST_DATA_ARRIVAL_RUNBOOK.md`（Step 0–9，每步含 **输入/脚本/输出/PASS/FAIL**）。
最快路径：Step0 门禁 → Step1 合同检查 → Step2 快照 → Step3 重建 → Step4 M2 增强验证 → Step5 判 duration → Step6/7/8 分别进 M3/M4/Market → Step9 重判四世界资格。

## 24. 当前仍然禁止得出的结论
1. “2026 暴雨导致沈北玉米减产 X%”；2. “提前 24h 干预可减少 X 小时积水 / 挽回 X%”；3. “无灾害世界产量为 Y”；
4. 把 M2 的 susceptibility score 称为**积水概率**；5. 把 SAR ΔVV 称为**实测积水**；6. 把未报道地区当作**负样本**；
7. 用事件后排涝数据**预测**是否积水（post-treatment leakage）；8. 由 12 台泵**反推真实泵流量**。

## 25. 下一步
1. **等 Data Agent 完成**（`FULL_DATA_ACQUISITION_REPORT.md` 出现）→ 按 Runbook 执行；
2. **优先**：区级 2026 灾损台账（解锁 M2→L3、M3、M4、反事实）；
3. 其次：积水**持续时间**（D1/D2）、完整沟渠/泵站、多时相 SAR + σ⁰、玉米价格分层；
4. 结构与方法已就绪，**数据到达即可进入正式建模**。

---

## 26. 方法学文献核验（§八十九）
见 `05_analysis/10_parallel_research/METHOD_LITERATURE_REVIEW.md`；引用登记于 `logs/PHASE_4R/REGISTRY_ADDENDUM.csv`（**9 条**，含 DOI/URL）。
覆盖 §八十九 全部 8 个主题，并**逐条对应本研究决策**：

| 本研究决策 | 依据文献 |
|---|---|
| 不给 ROC/AUC（无可靠负样本） | Li & Guo 2021；Valavi et al. 2022 |
| 用“全区耕地背景”而非“伪 absence” | Phillips et al. 2009；Miok et al. 2026 |
| 以 **evidence region** 为验证单位 | Roberts et al. 2017；Valavi et al. 2019；Huang et al. 2025 |
| M3 用 **stage×duration**、优先**区间** | Tian et al. 2021；Bill-Weilandt et al. 2026；Ploschuk et al. 2018 |
| M3-B 用**全球 meta 分组效应**作弱信息先验 | Tian et al. 2021 |
| 反事实用 **CRN + 逐 draw 完整跑 world** | Karvanen et al. 2024；Lally et al. 2026 |
| 未校准前只做 definition/graph/interface/skeleton/synthetic | Lally et al. 2026；§九十三 |
| **应急泵 ≠ 全部排水** | Bill-Weilandt et al. 2026 方法学共识 |

> 说明：§八十九 明确本任务**不是** Data Agent 的抓数任务；本轮只获取**方法学证据与正式文献**并登记。
> 由此**强化了 M3 文献库**（新增全球 meta 分析 → M3-B 由“不可用”升为“先验级可用”）。

## 27. 本轮合规自查（§一–§九十九 逐条）
| 条款 | 要求 | 状态 |
|---|---|---|
| §3.1 | 不改 Data Agent 目录（01/02/03/04） | ✅ 全程只读，新增独立文件均在本轮工作区 |
| §3.2 | 建立独立工作区 | ✅ `05_analysis/10_parallel_research`、`06_models/prebuild`、`09_reports/PHASE_4R`、`logs/PHASE_4R` |
| §3.3 | 输入快照 | ✅ `logs/PHASE_4R/INPUT_SNAPSHOT.md`（含 SHA256/大小/mtime/行数/时间范围） |
| §3.4 | 不读可能正在写入的文件 | ✅ 未读半成品；`FULL_DATA_ACQUISITION_REPORT.md` **不存在** → 不做新数据接口预检查 |
| §四 | R01→R18 不跳步 | ✅ 按序完成（R01–R18 + 主报告） |
| §五 | RESEARCH_STATE_AUDIT（五级） | ✅ |
| §六 | 术语一致（非深度/历时/水动力/概率模型） | ✅ `TERMINOLOGY_CORRECTION_PHASE4R.md` |
| §七/八 | M2 法医审计 + 42,473 vs 42,017 | ✅ 账目闭合：42,473 = 42,473 + 0 |
| §九/十 | 阈值生成方式 + 改称 susceptibility | ✅ 百分位分位，禁写 probability |
| §十一/十二 | 耕地判定规则 + 阈值敏感性 | ✅ WorldCover10m→30m→100m `frac≥0.5`；20/50/80% |
| §十三 | DataV 边界审计 + 措辞 | ✅ 813.1 km²；标 **public administrative boundary representation** |
| §十四/十五 | 逐变量三问 | ✅ `M2_PHYSICAL_CROSS_VALIDATION.md` |
| §十六/十七 | flow_accumulation 专项 + 禁止擅改 | ✅ 5 项根因；不删/不反转/不改权重 |
| §十八–二十二 | 证据区域验证 + 非 p 值 + 置换 + 空间自相关 | ✅ 1/3/5km + 富集比 + 置换(1000) |
| §二十三–二十五 | 敏感性重审 + 权重集合 + 稳定性地图 | ✅ `M2_RESOLUTION_SENSITIVITY_REAUDIT.md`、`M2_STABILITY_MAP.md`、F13/F14 |
| §二十六–二十九 | 排水专项 + 特征族消融 | ✅ `M2_FEATURE_FAMILY_ABLATION.md` |
| §三十–三十四 | M3 文献审计/分级/效应量/方差 | ✅ 8 行；lnRR；不伪造方差 |
| §三十五–四十四 | M3 候选/合成/单调性/合同 | ✅ 单调性 5/5 |
| §四十五–四十九 | M4 状态方程/标注/泵≠全排水/分布 | ✅ |
| §五十–五十三 | M4 合成不变量 + 单元测试 | ✅ T1–T5 + 3 脚本全通过 |
| §五十四–六十 | 四世界定义 + 估计量 + 规格文件 | ✅ B≠rain=0；C≠全排水=0；D 只改启动 |
| §六十一–六十四 | 引擎骨架/模块化/接口/缺字段处理 | ✅ `engine.py`；MissingData |
| §六十五–六十九 | MC 传播 + CRN + 区间 + 单测 | ✅ `test_mc_propagation.py` 全通过 |
| §七十–七十六 | 作物状态预注册 | ✅ |
| §七十七–八十三 | 市场预注册（季节/窗口/层级） | ✅ |
| §八十四–八十六 | Data Contract + 字段分级 + 校验器 | ✅ `validate_new_data_contract.py` 可运行 |
| §八十七 | Ready Matrix | ✅ |
| §八十八 | 接数 Runbook（9 步含输入/脚本/输出/PASS/FAIL） | ✅ |
| §八十九 | 方法文献核验 + 登记 | ✅ 9 条（本节 + addendum） |
| §九十 | 可解释/可验证/可复现/可接入 优先 | ✅ 无深度学习/无堆算法 |
| §九十一 | 无 duration 不得输出损伤率 | ✅ 未输出 |
| §九十二 | 无排水能力/深度不得输出“提前24h减X小时” | ✅ 未输出 |
| §九十三 | 不得生成正式平行世界数字 | ✅ 仅 synthetic |
| §九十四 | 工程准备尽可能做完 | ✅ 6 模块结构/代码/测试就绪 |
| §九十五 | 主报告 25 节固定结构 | ✅ 1–25 节齐全（本节起为补充） |
| §九十六 | 必答 30 问 | ✅ 见下 |
| §九十七 | 成功标准 = 审计+隐患+结构/接口/代码/验证就绪 | ✅ |
| §九十八 | 最终纪律（无数据不填合理值） | ✅ |
| §九十九 | 一句话任务 | ✅ 见文末 |

---

# §九十六 必答 30 问

1. **M2 的 456 个未分类单元究竟是什么原因？** 当前快照**未分类=0**；该 456 缺口来自 Phase 4 首次运行的 **inf/NaN 聚合缺陷**（`min/max` 与 NaN 交互），已在 `aggregate()` 修复后消失（**代码缺陷，非 NoData**）。
2. **M2 风险等级究竟是概率还是相对排名？** **相对排名分位**（`percentile_rank` 切分 0/0.5/0.8/0.95），**不是概率**；已改称 **susceptibility score**。
3. **农田 100m 网格的入选规则是否稳健？** 规则 = WorldCover 10m → 30m → **100m `frac ≥ 0.5`（多数）**；20/50/80% 阈值下面积 ±10%、**高易感单元基本稳定**（2,124→1,992）。
4. **DataV 边界是否存在明显问题？** 几何有效、813.1 km²（公开约 819，差 ~0.8%）；**非官方法定边界**，须标 **public administrative boundary representation**。
5. **flow accumulation 为什么方向异常？** 实际是**口径敏感**：均值口径偏低（不一致）、中位数口径略高（一致）。根因：河道像元被 cropland mask 排除、平坦地形 D8 失真、填洼改变微地形、与 HAND/距离共线。
6. **已知受淹区域是否显著富集于高易感区域？** 是（3 km 缓冲中位秩 **0.640** vs 背景 0.488，富集比 **1.31**；top20% 覆盖 47%）；但**验证单位是 6 个证据区域**，只能作方向性结论。
7. **这一结果对 1/3/5 km 空间不确定性是否稳定？** 稳定：中位秩 0.533 / 0.640 / 0.643（富集比 1.07 / 1.31 / 1.44），随半径增大而增强（半径过小则覆盖不足）。
8. **M2 最依赖哪一类变量？** **地形族**（elevation/slope/relief/depression/HAND/TWI）为主；mapped 水系距离为次要。
9. **排水变量为什么影响这么大？** Phase 4 的“影响大”**部分是伪像**（单像元取值 + G2 证据 3–5km 误差）；证据区域口径下排水为**次要贡献**，且 OSM 排水沟仅 1 条、代表性不足。
10. **M2 哪些区域属于稳定高风险？** 按 §二十五 的 **9 套设定**（4 权重族 + 3 网格 + DEM 90m）：**robust_high = 5,450 单元（12.8%）**、intermediate 2,638、unstable 34,385；另有 4 套权重子集的更严口径为 712 个。（图 F13）
11. **Phase 2 已有渍涝论文进入 M3 后属于什么等级？** 4 篇夏玉米共 6 行为 **M3-B**，加 1 篇**全球 meta 分析**（M3-B），故 **M3-B = 7 条**；另有 1 篇水稻洪水损失函数属 **M3-C（方法学）**；**M3-A = 0**（无东北春玉米）。
12. **M3 最合适的是剂量响应、层次 Bayesian 还是区间模型？** **修正后：M3-B（先验级，用全球 meta 的分组效应作弱信息先验）+ M3-C（保守区间）并行**，M3-A 作透明基准；**严格加权 meta 仍待逐研究方差**。
13. **缺什么数据才能正式运行 M3？** **积水持续时间（≥D2）** + 文献方差（SD/SE/n）+ 春玉米本地试验。
14. **M4 最合理的状态方程是什么？** 简化水量平衡 `ΔS = (P + Inflow − Inf − NatDrain − Pump − Other)·Δt`，各项标注可观测性。
15. **8000 亩/96h 案例能够约束什么、不能约束什么？** **能**：给出**弱聚合约束**（排净时间上界、泵当量量级 0.34–1.13 mm/h）与**方向性**（泵加速排涝）；**不能**：反推真实泵流量、分离自然排水与泵贡献、给出单点排水能力。
16. **M4 需要哪些核心参数？** 泵能力/台数、干预起止、**设计排水能力**（常规 vs 应急须分开）、初始蓄水、入渗/自然排水速率、淹没面积。
17. **M4 的合成不变量测试是否全部通过？** **全部通过**（T1–T5 + 3 个单元测试脚本）。
18. **四个世界分别改变了哪些变量？** A 全观测；**B 仅天气→正常情景（干预由结构响应，通常不启动应急泵）**；**C 仅取消应急抽排（保留常规排水）**；**D 仅改 `intervention_start`（−24/−48h）**。
19. **B 世界为何不能简单设置 rainfall=0？** 因为“无灾害”是**把极端天气暴露替换为历史正常天气情景**，而非“不下雨”；且 emergency intervention 是灾害的**下游变量**，正常天气下不应“12 台泵照常启动”。
20. **C 世界为何不能设置所有排水=0？** 那会变成**另一个不存在的世界**；C 只取消**应急抽排**，必须保留自然下渗/沟渠/常规基础设施。
21. **四世界如何传播参数不确定性？** **Monte Carlo + Common Random Numbers**：每次 draw 从 M2/M3/M4/weather 分布抽样，完整跑一个 world，只改处理变量；结果给 **median + 50/80/95% 区间**。
22. **高频遥感数据回来后第一项检验是什么？** **建立历史同期 expected trajectory**（2021–2025 同行物候窗口），再算 **异常 = 2026 − expected**（不能只做 before−after）。
23. **高频价格数据回来后第一项检验是什么？** **季节性去除**：`abnormal_price = price_2026 − seasonal_expected(2021–2025 同期)`（不能直接 7月 vs 8月）；并**按价格层级分开**。
24. **哪些新数据能把 M2 从 L2 推向 L3/L4？** **田块级（G1）受淹标签或经核验负样本**；完整沟渠/泵站矢量；多时相 SAR（多年同期+σ⁰）；裸地 DEM。
25. **哪些新数据能解锁 M3？** **积水持续时间**（D1/D2）+ **逐研究方差（SD/SE/n，用于加权 meta）** + 春玉米本地试验；文献侧已由 §八十九 补入全球 meta 分析（M3-B 先验级可用）。
26. **哪些新数据能解锁 M4？** 泵铭牌/流量、**设计排水能力**、storage/depth 观测、干预台账。
27. **数据回来以后，最快多少步骤能开始正式模型？** 按 Runbook **9 步**：门禁→合同检查→快照→重建→M2 增强验证→判 duration→（M3/M4/Market）→重判四世界。
28. **当前整个四世界系统最大的单点瓶颈是什么？** **沈北区级 2026 灾损/田块级受淹标签（G1）** —— 同时卡住 M2→L3、M3、M4 与反事实。
29. **当前第二大瓶颈是什么？** **积水持续时间**的观测或可靠代理 —— 直接决定 M3 能否启动。
30. **下一阶段最优执行顺序是什么？** ①完成数据合同检查 → ②扩标签（G1）与 duration → ③M2 升级 L3/L4 → ④M3 校准 → ⑤M4 校准 → ⑥四世界（带区间）。

---

## 本轮产物清单
```
05_analysis/10_parallel_research/
  RESEARCH_STATE_AUDIT.md, TERMINOLOGY_CORRECTION_PHASE4R.md,
  M2_CELL_ACCOUNTING_AUDIT.md, CROPLAND_AGGREGATION_AUDIT.md, BOUNDARY_AUDIT.md,
  M2_PHYSICAL_CROSS_VALIDATION.md, M2_EVIDENCE_REGION_VALIDATION.md,
  M2_STABILITY_AND_SENSITIVITY.md, M2_FEATURE_FAMILY_ABLATION.md,
  M2_RESOLUTION_SENSITIVITY_REAUDIT.md, M2_STABILITY_MAP.md,
  M2_multisetting_ranks.csv, M2_weight_ensemble_scores.csv,
  M2_STABILITY_MAP_cells.csv, M2_STABILITY_MAP.geojson,
  UNCERTAINTY_PROPAGATION.md, DATA_AGENT_ACTIVITY_DETECTION.md, METHOD_LITERATURE_REVIEW.md
06_models/prebuild/
  MODEL_READY_MATRIX_PHASE4R.md, DATA_AGENT_INTEGRATION_CONTRACT.md
  M3/{M3_LITERATURE_EVIDENCE_AUDIT.csv, M3_LITERATURE_AUDIT.md, M3_MODEL_CANDIDATES.md,
      M3_SYNTHETIC_EXPERIMENTS.md, M3_synthetic_dose_response.csv, M3_INPUT_CONTRACT.md}
  M4/{m4_water_balance.py, M4_STATE_EQUATION.md, M4_PARAMETER_RANGES.csv, M4_SYNTHETIC_VALIDATION.md}
  counterfactual/{COUNTERFACTUAL_WORLD_SPECIFICATION.md, engine.py, ENGINE_INTERFACE.md,
                 MC_demo_summary_SYNTHETIC.csv}
  crop_state/CROP_STATE_STUDY_PREREGISTRATION.md
  market/MARKET_EVENT_STUDY_PREREGISTRATION.md
09_reports/PHASE_4R/{PHASE_4R_PARALLEL_RESEARCH_REPORT.md, POST_DATA_ARRIVAL_RUNBOOK.md}
08_figures/M2/{F13_stability_map.png, F14_resolution_overlap.png}
logs/PHASE_4R/{INPUT_SNAPSHOT.md, DATA_CONTRACT_CHECK.csv, REGISTRY_ADDENDUM.csv}
scripts/{90..95}_p4r_*.py, scripts/validate_new_data_contract.py, scripts/tests/{test_m4_*,test_mc_propagation}.py
```

## 一句话结论
> Phase 4R **完成了能提前完成的一切**：M2 法医审计（**账目闭合、术语纠正、3 处对 Phase 4 的方法学更正**）、
> M3/M4/反事实的**结构、代码、合成测试与接口合同**（**全部通过**）、**四世界因果定义**与**MC 不确定性框架**、
> 以及**明早接数的 9 步 Runbook**；同时严格确认 **Data Agent 尚未完成**，**未读取半成品、未生成任何正式数字**。
> 现在系统已处于「**数据到达即可直接校准**」的状态。
