# PHASE_4_RESEARCH_REPORT.md
## 《2026 年沈北新区极端暴雨对玉米生产影响及反事实推演研究》—— 第四阶段研究报告
### 2026 暴雨农田渍涝空间重建与 M2 空间风险模型

> 执行顺序：空间数据审计 → DEM/农田/水系 → 地形水文特征 → 2026 天气暴露 → SAR → 真实灾情证据 →
> 标签审计 → 物理 Baseline → 决定 Route → M2 建模 → 空间验证 → 2026 重建 → 敏感性 → 反事实资格判断。
> **未先训练模型；未先画最终风险图；未碰 M3；未碰前端。** 时间：2026-09-23。

---

## 1. 为什么 Phase 3 后转向 M2
Phase 3 已**证伪** M1（年度天气→单产）：n=8、加入极端降雨后 LOYO **预测恶化**（ΔMAE +10.6/ΔRMSE +27.2/ΔlogPD −0.082）、2026 属强外推（ZR=+4.25）、对中度效应识别率仅 0.34 → **M1 不具备反事实资格**；并明确**禁止**用换算法/加特征/改先验去“救活” M1。
因此路线转向**事件尺度机制链**：`极端降雨 → 地表汇水 → 农田积水 → 积水范围/深度/历时 → 玉米胁迫 → 单产损伤`。本轮专攻 **M2：极端降雨 → 农田渍涝空间分布**。

## 2. Phase 4 研究问题
- **Q1** 2026-07 暴雨后，沈北哪些农业区域最容易积水？
- **Q2** 为什么这些区域更易积水？
- **Q3** 能否用 DEM+水系+土地利用+降雨+SAR+真实受淹报道，重建**有证据支持**的渍涝风险图？
- **Q4** 哪些结论有地面证据、哪些有遥感证据、哪些仅模型推断？

## 3. 空间数据来源（均登记 `DATA_SOURCE_REGISTRY.csv`）
| 数据 | 来源 | 分辨率 | 等级 |
|---|---|---|---|
| 沈北行政边界 | DataV GeoAtlas（adcode 210113） | 矢量 | B |
| DEM | Copernicus DEM **GLO-30**（AWS） | 30 m | C（DSM，含建筑/树冠） |
| 耕地掩膜 | ESA WorldCover 10m 2021（class 40） | 10 m | C |
| 水系/道路/铁路 | OpenStreetMap（Overpass） | 矢量 | C（**排水不完整**） |
| 2026 降雨 | ERA5（Phase 2） | 单网格点 | D |
| SAR | Sentinel-1C GRD（Planetary Computer） | ~10 m | D |
| 土壤 | SoilGrids WCS（**失败**） | — | not_available |

## 4. 研究单元与空间尺度
- CRS：**EPSG:32651（UTM 51N）**；分析栅格 **30 m**；研究单元 **100 m**。
- 研究区 = 沈北边界 ∩ 耕地 → **42,473 个 100 m 单元（424.7 km²）**。
- **不假精细**（§39）：输出精度由**最弱数据源**决定（soil 缺失、rainfall 单点、DEM 30m、SAR~10m）→ 不做米级灾害图。

## 5. DEM 与地形特征（P4-05/06/07/13）
- 质量：有效像元 610,266；高程 **35.9–370.4 m**；无异常 nodata（`DEM_QUALITY_REPORT` 数值见日志）。
- 水文预处理：**Priority-Flood 填洼**（2.3 s）→ 另保留 **raw 洼深**（不无脑填平，§12）。
- 提取：elevation、slope（0.92° 均值，**地形极平**）、local_relief、**depression_depth（max 6.99 m）**、**flow_accumulation（D8，max 582）**、**TWI**、**HAND（相对汇流≥200 的推导排水网络）**。
- ⚠️ TWI/HAND 局限：本地为**高度人工化农业排水系统**，纯自然地形指标不足，已写入限制。

## 6. 水系与排水设施（P4-07/08）
- OSM 水系 **67 条**：water 38、stream 14、river 8、canal 4、dam 2、**ditch 1**。
- → **`drainage network incomplete`**：**排水沟渠严重不完整**；泵站无 OSM 记录（0）。
- 变量命名严格用 **`dist_mapped_*`**（不暗示完整覆盖）。
- 道路/铁路 1013 条，**含 G101（101 国道）**，与受淹高标准农田空间对象一致。

## 7. 土壤与前期湿润（P4-09/10）
- **土壤：not_available**（SoilGrids WCS 返回 400）——如实记录，未插补。
- 前期湿润：`antecedent_7d=77.3mm`、`antecedent_14d=146.0mm`（ERA5 单点，event-wide）。

## 8. 2026 降雨空间暴露（P4-11）
- 沈北**仅有 1 个代表性 ERA5 网格点** → **不做虚假高精度空间插值**（§23）。
- 降雨作 **event-wide forcing**（事件累计 218.0mm、最大24h 155.7mm）；**空间差异来自地形/水文/排水**。

## 9. Sentinel-1 事件证据（P4-12）
- 配对：`S1C_IW_GRDH_1SDV_20260706 → 20260718`（**同平台、同相对轨道 3、descending**）。
- 预处理：**未做 σ⁰ 绝对辐射定标、未做地形校正**；仅通过降至 100m 等效抑斑；`delta_vv_pct` = 相对变化。
- 全研究区均值 **ΔVV ≈ −3.41%**（后向散射下降，方向上与土壤高湿/积水一致）。
- ⚠️ **无历史同期对照**（PC 存档 2023–2025 同轨道该窗口无可用影像）→ **ΔVV 仅作“异常证据”，不得称为实测积水**。
- 与物理易感性的 **Spearman ρ = 0.05（p<0.001）→ 空间一致性很弱**（重要诚实结果）。

## 10. 地面灾情证据（P4-13）
`labels/ground_evidence_points.csv`：8 条证据点
- **G1（精确田块级）＝0**；G2（村/街道级）＝7；G3＝1；**可靠负样本＝0**。
- 明确“有渍涝” 6 条；`unknown`（仅人员转移）1 条；**事件后已排涝的“无积水”1 条（属 post-treatment，非负样本）**。
- **空间定位误差 ≈3–5 km**（OSM 缺目标村节点，坐标用街道中心/路名代理近似）。

## 11. 标签质量审计（P4-35）
见 `labels/LABEL_AUDIT.md`。核心结论：
1. 无精确田块正样本；正样本均为村/街道级；
2. **无可靠负样本**——“未报道 ≠ 无积水”（§33），且唯一“无积水”记录是事件后已排涝（post-treatment）；
3. 因此**不具备监督二分类条件**；唯一可用对照是**全区背景分布**。

## 12. 物理易涝性分析（P4-15）
见 `05_analysis/09_spatial_waterlogging/PHYSICAL_PLAUSIBILITY_ANALYSIS.md`。
- 对每个“明确受淹”证据点取 **3 km 邻域**耕地均值，与全区背景比较：
  **10 个地形/水文变量中 9 个方向与机制一致**（高程↓、坡度↓、起伏↓、洼深↑、HAND↓、TWI↑、到水系/河流/排水距离↑）。
- **例外**：`flow_accumulation` 方向相反（受淹邻域 3.47 < 背景 5.68）。
- ⚠️ 证据点误差(3–5km) 与邻域半径(3km) 同量级 → **只看方向，不作显著性结论**。

## 13. M2 模型方法（P4-16/17）
**Route A：证据重建**（因标签结构决定，§36）
- **不做监督模型**（无 G1、无负样本）；
- 构造**透明的物理易感性 Baseline**（§49/50 方案1：机制方向 + 等权 → 百分位），另给**方案2**（依证据点差异透明校准）变体；
- 三层融合：
```
M2R_risk = rank( 0.50·susceptibility + 0.15·event_exposure_rank
               + 0.15·sar_anomaly    + 0.20·evidence_proximity )
```
- **M2a（自然易感性）与 M2b（事件观测）严格分开**；**Predictive M2 只用 PRE+EVENT**，**M2R 才叠加 POST-EVENT**（§59/64）。

## 14. 空间验证（P4-44/45/48）
见 `validation/M2_VALIDATION.md`。**无负样本 → 不报 accuracy/specificity/ROC-AUC**（无意义）。
| 指标 | 值 |
|---|---|
| 已知正样本邻域召回（邻域易感性>中位数） | **0.50** |
| 正样本处易感性平均百分位 | **0.59**（背景=0.50） |
| Spearman(易感性, ΔVV) | **0.05** |

## 15. 2026 渍涝重建（P4-17）
- `M2R_risk` 分级：**Low 21,008 / Moderate 12,605 / High 6,303 / VeryHigh 2,101** 单元。
- 置信度：Low 17,745 / Medium 22,503 / High 2,225。
- **风险与置信度分开表达**（图12），避免“高风险=高确信”。
- 空间规律：高风险集中于**低高程 + 小坡度 + 大洼深 + 低 HAND + 距映射排水远**的连片低洼耕地。

## 16. 不确定性
1. 排水网络不完整（距排水变量最不可靠）；
2. SAR 未定标、无对照、与易感性一致性弱；
3. 降雨为单点 forcing（无空间差异）；
4. 土壤缺失；
5. 证据点空间误差 3–5 km；
6. DEM 为 DSM（含建筑/树冠）而非裸地。

## 17. 敏感性分析（P4-66）
见 `sensitivity/M2_SENSITIVITY.md`。
| 因素 | 正样本处易感性百分位 |
|---|---|
| 网格 50/100/250 m | 0.499 / 0.547 / 0.546（**较稳**） |
| DEM 30/90 m | 0.536 / 0.574（**较稳**） |
| 排水变量 有/无 | 0.547 / **0.415**（**去掉排水后跌到中位数以下**→ 排水距离确有影响） |
| SAR 阈值 P5/P10/P20 | 异常比例 5%/10%/20%，与易感性前 25% 的重叠仅 1.0%/2.2%/4.5%（**几乎不重叠**） |

## 18. 典型案例区
- **八间房村（新城子街道）**：8000 余亩、最深>1m、**12 台 8 寸泵**、7-18 排净（最强干预证据）。
- **新民村（兴隆台街道）**：7-15 清障疏渠抢排积水（官方锚点）。
- **101 国道沿线高标准农田**（财落+兴隆台街道，含大营子/大屯/兴光/单家村，1.55 万亩项目）——**与灾情综述受淹对象一致**。
- ⚠️ **未做田块级放大图**：因证据点空间误差 3–5 km，放大图会制造“伪精确”（§81 要求“前提是空间证据确实对应”）。
  可行的替代已在图8（证据点）与图11（重建风险）中呈现。

## 19. M2 反事实资格（P4-72）
见 `COUNTERFACTUAL_ELIGIBILITY_M2.md`：
| Gate | 结果 |
|---|---|
| A 地形/水系质量 | **PASS**（地形）/ 排水不完整 |
| B 方向符合机制 | **PASS**（9/10） |
| C 与真实受淹点一致 | **CAUTION**（召回 0.50） |
| D 与独立遥感一致 | **CAUTION**（ρ=0.05） |
| E 空间验证 | **CAUTION**（无 G1 标签） |
| F 无 post-event leakage | **PASS** |
**总判定：`ELIGIBLE_FOR_DESCRIPTION_ONLY`** → 只能**描述/重建 2026**，**不能**用于未来降雨情景与无灾害世界（§74）。

## 20. Phase 5 建议
1. **补标签**：向区农业农村局/应急局申请**田块级受淹台账**（G1）→ 才能解锁 M2-L3；
2. **补排水**：沟渠/泵站矢量（水务局）→ 修正 `dist_mapped_drainage`；
3. **补 SAR 对照**：多年同期 + σ⁰ 定标 + 地形校正；
4. **补土壤**：换 SoilGrids 其他接口或本地土壤图；
5. **补 DEM**：裸地 DEM（如 30m Copernicus DEM 的 DSM 局限性）或本地实测；
6. 仅在 L3 达成后，才启动 **M3：渍涝持续时间 → 玉米损伤**（§58：需 `waterlogging duration + phenology`）。

---

## §83 必答 20 问

1. **最终使用什么 DEM？** Copernicus DEM GLO-30（AWS 公开 COG）。
2. **DEM 分辨率？** 30 m（DSM；分析栅格 30 m）。
3. **沈北农田范围如何确定？** 沈北行政边界 ∩ ESA WorldCover 2021 class40 耕地（100 m 网格 42,473 单元 / 424.7 km²）。
4. **是否获得玉米空间范围？** **否** → 只称 **agricultural cropland**，不称 corn（§9）。
5. **水系完整度如何？** OSM 67 条水系；**不完整**。
6. **排水沟渠完整度？** **严重不完整**（ditch 仅 1 条）→ `drainage network incomplete`。
7. **是否获得泵站位置？** **否**（OSM 无记录）；仅文字证据（八间房村 12 台 8 寸泵）。
8. **哪些地形指标最能解释已知受淹地点？** 与机制一致者：**高程↓、洼深↑、HAND↓、距水系/河流/排水距离↑、TWI↑、坡度↓、起伏↓**（9/10 一致）；`flow_accumulation` 方向相反。
9. **Sentinel-1 是否检测到空间一致性异常？** **弱**：全研究区 ΔVV≈−3.41%，但与易感性 **ρ=0.05** → 空间一致性差。
10. **有多少明确地面正样本？** 6（G2=5 + G3=1）；**G1=0**。
11. **有多少可靠负样本？** **0**。
12. **是否具备监督模型条件？** **否**。
13. **最终选择 Route A/B/C？** **Route A（证据重建）**。
14. **M2 预测输入有哪些？** PRE-EVENT（地形 7 项 + 排水距离 3 项 + 道路 1 项 + 耕地比例）+ EVENT（事件降水、前期 7/14 日降水）；**不含** SAR/地面证据/干预。
15. **M2R 比 M2 多用了哪些事件后证据？** `sar_anomaly`（ΔVV 异常）、`evidence_proximity`（到受淹报道距离）、以及干预（仅用于叙述）。
16. **模型空间验证效果如何？** 无负样本 → 只报一致性：正样本邻域召回 **0.50**、正样本处易感性百分位 **0.59**、与 SAR ρ=0.05。
17. **哪些区域是 2026 高渍涝风险区？** VeryHigh 2,101 + High 6,303 个 100m 单元，集中于低高程/大洼深/低 HAND/远离映射排水的连片低洼耕地（图11）。
18. **哪些区域模型置信度最低？** 17,745 个 Low 置信单元（无 SAR 异常且远离地面证据，且全区受“排水不完整”降级）。
19. **M2 是否达到反事实资格？** **否**（`ELIGIBLE_FOR_DESCRIPTION_ONLY`）。
20. **是否已能进入 M3？** **否**。M3 需 `waterlogging duration + phenology`；本轮**仅有单次 before/after SAR（D3 级）**，**不能推持续时间**，故 M3 暂不可启动（§56/58）。

---

## 本轮产物
```
06_models/M2_waterlogging_spatial/
  M2_INPUT_AUDIT.md, SPATIAL_REFERENCE.md, M2_VARIABLE_CAUSAL_ROLE.md,
  M2_SPATIAL_DATA_DICTIONARY.md, MODEL_CARD_M2.md, COUNTERFACTUAL_ELIGIBILITY_M2.md
  data/grid_100m.gpkg
  labels/ground_evidence_points.csv, LABEL_AUDIT.md
  remote_sensing/S1_PROCESSING_PIPELINE.md
  models/M2_BASELINE_SPEC.md, M2R_reconstruction.gpkg
  validation/M2_validation_metrics.csv, M2_VALIDATION.md
  sensitivity/M2_sensitivity.csv, M2_SENSITIVITY.md
03_clean/spatial/{shenbei_boundary.gpkg, dem/*.tif(8), cropland/*.tif, hydro/*.tif(5)}
04_marts/M2_spatial_dataset.{csv,gpkg}
05_analysis/09_spatial_waterlogging/{PHYSICAL_PLAUSIBILITY_ANALYSIS.md, physical_plausibility.csv}
05_analysis/08_model_readiness/MODEL_READINESS_PHASE4.md
08_figures/M2/F1..F12 (12 图 + README)
scripts/{80..86}_p4_*.py
09_reports/PHASE_4_RESEARCH_REPORT.md
```

## 一句话结论
> Phase 4 建立了 **2026 沈北农田渍涝的空间证据体系与 M2 模型（M2-L2 多源事件重建）**：
> 明确**哪些区域高风险、为什么高风险（地形—水文机制，9/10 方向一致）、证据有多强（G1=0、无负样本、SAR 与易感性一致性弱）**；
> 并判定 **M2 只能用于描述 2026，不具备反事实资格**，**M3 暂不可启动**。
> —— 这回答的是：**在当前真实数据条件下，我们对“哪里淹、为什么淹”究竟能知道多少。**
