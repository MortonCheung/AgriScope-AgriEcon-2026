# PHASE_2_RESEARCH_REPORT.md
## 《2026 年沈北新区极端暴雨对玉米生产影响及反事实推演研究》—— 第二阶段研究报告（模型数据补强与建模准备）

> 执行顺序：P2-01 → P2-15 全程按序，未跳过；**未训练最终模型、未构造平行世界、未碰前端**。
> 时间：2026-09-22。所有数值可经 `source_id` 回溯。

---

## 1. 本轮目标
围绕四大瓶颈（样本少 / 天气未转成生育期特征 / 缺灾害结果变量 / 干预不可计算）做**建模地基**：
① 延长历史玉米序列；② 构建面向农业的生育期天气特征；③ 补齐灾害结果证据；④ 把“有人排水”变成可计算变量；
并完成**候选模型筛选、可识别性审计、因果结构骨架**。

## 2. Phase 1 复核发现（P2-01）
- **单位/时间重审结论：未发现需修正的错误。**
- 关键澄清：**“97.1 mm/h”经原文回溯确认为“最大小时降雨量”= 最大 1 小时雨强**（非累计）；`8月24日` 是**日期**、`6时至16时` 是**10 小时窗口**。Phase 1 标注正确。
- 已区分“新闻发布时间 vs 事件时间”“统计年度 vs 出版年度”。（详见 `logs/PHASE1_UNIT_AND_TIME_REAUDIT.md`）

## 3. 新增数据（P2-02 ~ P2-10）
- **新增来源 9 条**（registry 22 → 31）：官方 2（更名通知、民政局区划）、同行评议论文 4、遥感 STAC 服务 2、区划整理 1。
- **新增文件**（主要）：`corn_history_extended.csv`、`corn_year_weather_features.csv`、`corn_model_dataset_annual(_CORE).csv`、`corn_phenology_reference.csv`、`corn_phenology_yearly_gdd.csv`、`disaster_outcomes_2026.csv`、`intervention_quantified.csv`、`literature_parameter_library.csv`、`rs_scene_manifest.csv`、`rs_s1_backscatter_exploratory.csv`、`weather_source_validation.csv`；文档 11 份；脚本 6 个（新增）。
- **构成**：官方 A/B 级 4；科研 C 级 4（论文）；再分析/遥感 D 级 4；第三方线索 1。

## 4. 玉米历史序列（P2-02）
- **最终年份范围：2018–2025**；**有效可比年份数 = 8**。
- **行政口径**：已确证 **2006-11-07 起“新城子区”更名为“沈北新区”，所辖行政区域与驻地不变** → 更名后 **DIRECTLY_COMPARABLE**；更名前（1960–2006）**APPROXIMATELY_COMPARABLE**（需核边界）。
- **2010–2017：官方未公开**（沈阳统计年鉴 2016/2017/2018 卷落地页无附件）。**未插值、未外推。**
- 内部一致性：`面积×单产≈总产` 相对差 <0.01%（2018–2024），2025 −0.15%。
- ⚠️ **未达 §32 条件 A（≥15 年）**：距理想仍缺 7 年 → 复杂年度模型风险极高（已在 §11 量化）。

## 5. 气象数据（P2-04）
- **年份范围**：日值 **1991–2026-09-14**；逐小时 **2015–2026-09-14**。
- **空间位置**：沈北新区代表**网格点**（42.003513, 123.53712）→ **不是站点**。
- **性质**：**再分析（ERA5，Level C）**；**未写成“实测”**。
- **质量验证（ERA5 vs NASA POWER，2083 天）**：月降水相关 **0.938**、日均温 MAE **1.45℃**；但**极端日（≥25mm）一致率仅 0.391**。
  → **可用于长期总量/均值/趋势；不可靠用于“某一天是否暴雨”的识别**。

## 6. 物候（P2-05）
- 建立 **GDD 物候模型**（基温 10℃、上限 30℃；阈值经本地作物日历标定）。
- **2026：抽雄 07-10、吐丝 07-14** → **7-13 暴雨落在“抽雄—吐丝期”**。
- **阶段概率（1991–2020 经验分布，7-13）**：抽雄 **0.50** / 大喇叭口 **0.33** / 吐丝 **0.17**（抽雄+吐丝合并 0.67）。
- **结论：2026-07-13 玉米处于抽雄—吐丝期，最可能为抽雄期；置信度“中”。**

## 7. 生育期天气特征（P2-06/07）
- 输出 `corn_year_weather_features.csv`（**36 年 × 各生育期**，159+ 列）。
- **每阶段**（播种/出苗/拔节/大喇叭口/抽雄/吐丝/灌浆/成熟）生成：降水（sum/mean/max1d/max3d/max5d、雨日、暴雨日、连续湿日）、温度（tmean/tmax/tmin、热日、极端热日、GDD）、复合（湿热日）；并合并为 **营养生长期 / 抽雄吐丝期 / 灌浆期** 三大核心阶段。
- **前期湿润**：`antecedent_precip_{3,7,14,30}d`（以抽雄期为基准）。
- **极端与复合指数**：`rx1day / rx5day / r95p / r99p / cwd / annual_precip`；阈值**同时给绝对（国标）与相对（沈北历史 P90/P95/P99）**。

## 8. 2026 灾损证据（P2-08 / P2-09）
| 类别 | 内容 | 状态 |
|---|---|---|
| **官方（区级）** | 受灾/成灾/绝收面积、直接经济损失 | **not_available**（未按区公开；仅省级“受影响约 290 万亩”“排空 53.27 万亩”） |
| **官方（点位）** | 兴隆台“万亩农田受淹”；马刚 423 人转移；虎石台撤离 50 余人 | ✅ 定性/量级 |
| **新闻** | 新城子街道八间房村 8000 余亩受淹、最深>1m | ✅ 量级 |
| **遥感** | S1 事件前后各 5 景；实测 VV **−1.75%**；**但 2025 该区无 S1 存档 → 无同期对照**，**不能归因**；S2 云量中位 68% | 🟡 探索性 |

## 9. 干预量化（P2-10）
- **什么时候行动**：预警 7-13 09:10 → 排涝 7-14（八间房村）/7-15（兴隆台新民村）；**预警提前量 14.8–38.8 h**。
- **行动能力**：八间房村 **12 台 8 寸泵**（当量范围 1800/3600/6000 m³/h，**工程参考非铭牌**）。
- **持续时间**：个案 **96 h**（7-14→7-18）；兴隆台约 48 h。
- **涉及面积**：个案 **8000 余亩**。
- **还不知道**：全区排涝台账、各受淹地块积水时长、未干预对照、泵站既有能力。

## 10. 因果图（P2-14）
`Weather → Waterlogging → CropStress → Yield → Production`，支链 `Intervention → WaterloggingDuration → CropStress`。
逐边证据：`Weather→Waterlogging`（定性 DATA_SUPPORTED）、`Waterlogging→CropStress`（LITERATURE_SUPPORTED）、`CropStress→Yield`（**仅文献先验**）、`Yield→Production`（DATA_SUPPORTED）、`Intervention→Duration`（个案 DATA_SUPPORTED）。核心障碍：**Waterlogging 无全区可观测量**（隐变量）。详见 `CAUSAL_GRAPH.md`。

## 11. 样本量诊断（P2-12）——**现在到底能不能建模型？**
> **不能（除“简单趋势基线”外）。**

- n=8、核心特征 12、**自由度 = −5**；
- `yield ~ time`：斜率 +328.5 kg/ha/年，R²=0.661（趋势混杂技术因素）；
- 特征间高度相关（降水类 |r|>0.84），**VIF 不可计算（p≥n）**；
- **LOYO 外推**：历史均值 R²=−0.31、**线性趋势 R²=+0.40**、OLS(全特征) R²=+0.10、**岭回归 R²=−44.4（灾难性）**。
→ **加入特征不提升外推反而破坏**，是 `p ≥ n` 的典型后果。

## 12. 候选模型（P2-13）
- **可立即用（探索性/描述）**：Linear Regression（1–2 变量）、相关/趋势、极端指数。
- **当前不可用**：GAM、Piecewise、RF、XGBoost、Ridge(多变量)、Synthetic Control、DID、BSTS。
- **推荐路线**：**结构式因果骨架 + 文献先验 + 遥感/机理约束 + Bayesian / Monte Carlo 不确定性传播**。
- 就绪度：**M1 LEVEL 1 · M2 LEVEL 2 · M3 LEVEL 1 · M4 LEVEL 1 · M5 LEVEL 1**（无一项达 LEVEL 3 预测）。

## 13. Phase 3 建议（第一项建什么）
**第一项建议：`M1′ — 小样本贝叶斯单产响应模型`**
- **为什么**：数据现成（`corn_model_dataset_annual_CORE`）、可解释、直接服务 B 世界（无灾害世界）；且能在小样本下给出**不确定区间**而非虚假精确值。
- **输入**：`time_index`（技术趋势）+ **1 个**抽雄吐丝期极端降水指标（如 `repro_precip_max_5d` 或 `repro_heavy_rain_days`，**二选一，避免共线**）；先验来自 `literature_parameter_library.csv`。
- **输出**：单产后验分布 + 降水弹性/阈值的可信区间。
- **验证**：**Leave-One-Year-Out** + 后验预测检查；报告跨年预测 MAE/RMSE，**不报训练 R²**。
- **并行准备**：采集 **DEM + 水系 + 泵站** 以解锁 `M2（降雨→渍涝）`；申请**区级灾损台账**以解锁 `M3`。

## 14. 剩余风险
| 风险 | 说明 |
|---|---|
| **样本量** | n=8，任何多特征模型不可识别（df<0） |
| **空间粒度** | 单区单网格点，无内部空间变异 |
| **数据来源** | 气象为**再分析**（非实测），极端日识别弱（一致率 0.39） |
| **行政口径** | 更名前新城子区仅 APPROXIMATELY_COMPARABLE；2018/2019 玉米面积同为 14084 |
| **遥感解释** | 无历史对照、无辐射定标 → 不能归因 |
| **因果识别** | 无对照、无灾损因变量 → 反事实不可识别 |
| **外推风险** | 单区短序列的天气-单产关系外推到未来/极端年份不可靠 |

---

## §36 必答 15 问

1. **玉米历史序列最终延长到哪一年？** 未延长，仍为 **2018–2025**（2010–2017 官方未公开，已确认并记录）。
2. **最终有多少个可比年份？** **8 个**（全部 DIRECTLY_COMPARABLE）。
3. **旧新城子区数据是否可以进入模型？** **可以，但须先核边界**：更名公告证明 2006 年时点辖域一致；更名前按 APPROXIMATELY_COMPARABLE 处理。**当前未取得任何新城子区玉米数据，尚未触发。**
4. **历史天气能覆盖多少年？** 日值 **1991–2026**；逐小时 **2015–2026**。
5. **再分析与实际观测的一致性如何？** 无实测可校（Level A 缺失）。ERA5 vs NASA：月降水相关 0.938、日均温 MAE 1.45℃，但**极端日一致率仅 0.391**。
6. **能否为每一年构造玉米生育期天气？** **能**：1991–2026 每年 × 8 个生育阶段 × 多类天气特征（GDD 物候，模型估计）。
7. **2026 暴雨时玉米处于哪个阶段？** **抽雄—吐丝期（最可能抽雄）**；概率 抽雄 0.50 / 大喇叭口 0.33 / 吐丝 0.17。
8. **是否获得新的受灾面积或农业损失数据？** **未获得区级数据**（官方未公开）；新增遥感探索证据（VV −1.75%，无对照）。
9. **是否能用遥感观察暴雨影响？** **数据可得，但当前不能定性结论**：缺历史对照与辐射定标；S2 云量 68%。
10. **是否能量化排涝行动？** **能（个案）**：起止时间、12 台 8 寸泵、预警提前量 14.8–38.8h、96h 排净 8000 余亩；**全区仍缺**。
11. **目前最可靠的结果变量是什么？** **玉米年单产（2018–2025，A/B 级）**。
12. **当前样本是否足以做产量预测？** **不足以做多特征预测**；仅可做“趋势基线”（LOYO R²=0.40）。
13. **当前样本是否足以做因果识别？** **不足**：无对照、无灾损、n 太小。
14. **当前是否具备反事实模拟条件？** **不具备**（依赖 M1–M4，均未达 LEVEL 3）。
15. **Phase 3 第一项应建立什么模型？** **小样本贝叶斯单产响应模型（M1′）**：趋势 + 单一抽雄吐丝期极端降水指标，文献先验 + LOYO 验证。

---

## 关键新增产物清单（Phase 2）
```
00_README/ADMIN_BOUNDARY_HISTORY.md, PHASE2_DATA_GAP_MATRIX.md, RESEARCH_TREE.md(更新)
03_clean/agriculture/corn_history_extended.csv
03_clean/disaster/disaster_outcomes_2026.csv
03_clean/intervention/intervention_quantified.csv
03_clean/phenology/{corn_phenology_reference.csv}
03_clean/remote_sensing/{rs_scene_manifest.csv, rs_s1_backscatter_exploratory.csv}
03_clean/weather/... (pnb_daily/pnb_hourly 沿用)
04_marts/{corn_year_weather_features.csv, corn_model_dataset_annual.csv, corn_model_dataset_annual_CORE.csv, literature_parameter_library.csv}
05_analysis/02_climate_baseline/WEATHER_SOURCE_VALIDATION.md
05_analysis/04_corn_baseline/CORN_DATA_HARMONIZATION.md
05_analysis/05_phenology/{PHENOLOGY_MODEL.md, corn_phenology_yearly_gdd.csv}
05_analysis/06_damage_mechanism/REMOTE_SENSING_DAMAGE_EVIDENCE.md
05_analysis/07_intervention/INTERVENTION_QUANTIFICATION.md
05_analysis/08_model_readiness/{SAMPLE_SIZE_DIAGNOSTICS.md, CAUSAL_GRAPH.md, MODEL_CANDIDATE_COMPARISON.md, MODEL_READINESS_PHASE2.md, DIAG_*.csv}
09_reports/PHASE_2_RESEARCH_REPORT.md
logs/{PHASE1_UNIT_AND_TIME_REAUDIT.md, PHASE2_DATA_QUALITY_AUDIT.md, phase2_data_quality_audit.csv}
scripts/{60_p2_features,61_p2_dataset,62_p2_intervention,63_p2_diagnostics,64_p2_outcomes_rs,65_p2_rs_s1}.py
```

## 一句话结论
> Phase 2 已把**数据地基做实**：统一建模数据集、生育期天气特征（36 年）、GDD 物候、干预量化、文献先验、因果骨架全部就位；
> 但**样本量（n=8）与本地灾损缺口**共同决定：**纯数据驱动模型不适用**，Phase 3 应走 **统计基线 + 农业机理 + 文献先验 + 遥感 + 贝叶斯/Monte Carlo** 的混合路线，**第一项建 M1′ 小样本贝叶斯单产响应模型**。
