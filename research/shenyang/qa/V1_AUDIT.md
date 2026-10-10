# V1_AUDIT — 旧版沈阳研究审计

> 施工手册 §5 要求的第二阶段强制产出。
> 定位：**只回答"旧版做了什么、有什么问题"，不做"好不好"的评价**。
> 方式：通读 `shenyang/reports/`、`shenyang/workspace/reports|src|outputs|*.md|*.json`（只读，未改动任何 v1 文件）。
> 证据形式：文件路径 + 位置 + 原文/代码片段。

---

## 0 审计对象清单

| 类别 | 数量 | 位置 |
|---|---|---|
| 阶段报告 | 19 + 4（BLOCKERS/DECISION_LOG/LIMITATIONS/MILESTONE_1） | `workspace/reports/` |
| 分析脚本 | 29（`_common.py` + `00`–`28`） | `workspace/src/` |
| 结果表 | 100 | `workspace/outputs/tables/` |
| 图 | 53（F01–F53） | `workspace/outputs/figures/` |
| 人类报告 | 3 + README | `reports/`（`01/02/03/04`），与 `workspace/SHENYANG_*.md|json` **逐字节相同** |
| 结果血缘 | 143 行 | `workspace/outputs/results_registry.csv` |
| 前端消费 | — | `AgriScope/scripts/sync-shenyang-content.mjs` → `AgriScope/public/research/shenyang/*` |

---

## 5.1 旧版到底研究了什么（逐项）

> 说明：下表中"代码"列以脚本文件名表示；v1 报告正文多数未写出脚本名，脚本名由 STEP 编号与 `src/` 实际文件对应得到，属审计推断（已在表中标注来源）。

### 表 5.1-A 数据与基础层

| 编号 | 研究问题 | 数据 | 方法 | 主要结果（保留数字） | 代码 | 图 | 表 |
|---|---|---|---|---|---|---|---|
| 01 | 数据源是否真实、可重建？核心窗口边界与缺口？ | `liaoning-agri-risk` 只读仓 22 张输入表（fact_price_city 168,559 行、fact_market_supply 16,550 行、fact_weather_daily 14,581 行、fact_disaster_events 140 行、dim_calendar 2,191 行）；沈阳 1991–2020 日值基线 10,958 天；原始价格 JSON 5,262 个 | 文件清单 + SHA256 快照 + 数据字典 + 缺失归因 + 日期/重复检查；数据事实优先级 Mart>Metadata>Raw>模板>历史报告 | 核心窗口 **2021-01-01~2026-09-14**；面板 **14,100 行**；沈阳批发成交量 16,550 条/1,655 交易日/10 品种；价格记录 143,527 条；气象 2,083 天断裂 0 处；缺失归因 published 1,655(67.4%)/collection_gap 702(28.6%)/holiday 76(3.1%)/workday 23(0.9%)/weekend 0；成交量单位 `unknown` | `00_inventory.py`、`01_build_panel.py`、`02_data_qa.py`（报告未标脚本名，属推断） | 无 | `event_catalog.csv`、`event_overlap_flags.csv`、`market_missing_calendar.csv`；`data_snapshot.json` |
| 02 | 10 种批发蔬菜价格/成交量的分布、长期趋势与季节性 | 1,410 交易日 × 10 品种 = 14,100 行；价格 `元/500g`；成交量 `unknown` | 分布统计（中位/CV/IQR）；log 水平 OLS（HAC）；月度季节指数；STL 稳健分解；日/周/月变化率分布 | 价格中位 1.10（土豆）~4.13（芸豆）元/500g；年化波动率 38.2%（土豆）~100.5%（黄瓜）；长期趋势仅**土豆 -3.1%/年（p=0.001）**显著、甘蓝 -4.7%（p=0.078）、茄子 -3.9%（p=0.083）；月度季节指数 1–2 月/12 月偏高、6–7 月偏低（青椒 2 月 1.87/7 月 0.68）；STL 价格季节强度中位 **0.491**、2/10 品种 >0.6；成交量季节强度中位 **0.061**、最大 0.288；价格日变化中位数 0（0.05 元最小报价单位） | `03_descriptive.py`（推断） | F01–F09 | 无独立表文件（正文内嵌表） |
| 03 | 如何构造 expected 与 anomaly 并避免信息泄漏 | 面板 14,100 行；1991–2020 官方日值基线；`soil_moisture` 官方基线缺失 | **方法B（主）** 留一年法历史同期中位数（doy±5 共 11 天、跨年中位数、有效观测<8→NaN、闰日并入 doy=365）；**方法A（对照）** STL 周序列（period=52、robust=True，含目标年）；两法一致性检验 | 留一年法 `uses_target_year=False` 全部成立；两法一致性价格 r 中位 **0.728**、成交量 **0.769**；\|稳健 z\|>3 极端日 **1,285 条**；`soil_moisture_z` 因官方基线缺失（10,958 天全 null）降级为观测期 LOO，**证据等级 B**；价格 P95 异常% 最高甘蓝 114.1%；黄瓜 \|z\|>4 达 105 天 | `04_deseasonalize.py`（推断） | F10–F14 | `anomaly_extreme_days.csv`、`shenyang_panel_final.parquet` |

### 表 5.1-B 天气—市场关系层

| 编号 | 研究问题 | 数据 | 方法 | 主要结果（保留数字） | 代码 | 图 | 表 |
|---|---|---|---|---|---|---|---|
| 04 | 天气异常与后续量价异常是否存在稳定滞后结构（RQ 滞后/H1/H3） | 面板 14,100 行；7 hazard（precip_1d/3d/7d、temp_max、temp_min、vpd、soil_z）；precip_1d 最大 173.9mm | 路径(a) 单 lag 回归 k=0..30（周末/节假日控制）；路径(b) 窗聚合分布滞后（0-2/3-6/7-13/14-30 同时入场）；HAC `maxlags=14`；FDR 两级（全家族 + 系列内）；有效观测<300 跳过 | 共 **8,680 个检验**；单 lag **全家族 FDR<0.05 显著 lag 数 = 0**；土壤水分系列内 FDR 显著（价格 15 个 lag、成交量 45 个 lag）；3 日降水 20 个"品种×响应"峰值 FDR 后显著 **0/20**（未校正 p<0.05 仅 2 个）；窗聚合 4 窗口联合 FDR 显著 **0/10**；两法峰值 lag 一致率 价格 50%/成交量 30%；效果口径 = 每 +1 SD hazard → 响应稳健 z 变动 | `05_lag_analysis.py` | F15–F19 | `lag_profile_single.csv`（含 p_value/fdr_p/fdr_p_within） |
| 05 | 是否存在非线性天气效应与气象风险临界点（RQ3/H5） | 面板 14,100 行；4 hazard × 10 品种 × 2 响应 = 80 检验 | 预登记判定规则（非线性 Wald-F → 断点 sup-Wald 循环块 Bootstrap → CI 定位）；自然样条 `cr(x,df=7)` vs 线性 HAC(14)；GAM（pygam s=8）；分段回归 120 分位候选；sup-Wald 循环块 Bootstrap（块长 30、B=500）；BH-FDR | 80 检验中未校正 p<0.05 共 9 个（随机期望约 4），**BH-FDR 后 0 个（最小 FDR p=0.144）**；断点预登记门槛通过组合 **0**；探索性候选黄瓜·price·precip_3d：c\*=6.0mm、CI [0.1, 25.0]、sup-Wald p=0.172；可搜索范围 [0.1, 24.4]mm（>50mm 仅 2.9%）；AR(1) 价格 **0.969**→n_eff≈22、成交量 0.894→n_eff≈79；**RQ3/H5 = NOT SUPPORTED** | `06_threshold.py` | F20–F22 | `threshold_gam_scan.csv` |
| 06 | 全历史极端天气事件的平均市场响应是否显著 | 13 个事件簇（2021–2026）；主分析清洁簇 雨 8/高温 1；窗口 T-14~T+21 | 复合事件簇（间隔≤3 天合并）；事件相对化 z_rel；簇级 Bootstrap（B=1000）；安慰剂 500 个；事后统计量 mean(z_rel,T+1..T+14) | 雨→价格 事后均值 **+0.017 [-0.405,+0.451]，安慰剂 p=0.942**；雨→成交量 **+0.075 [-0.079,+0.340]，p=0.709**；均 **NOT SUPPORTED**；价格谷底 T+2 -0.202、成交量谷底 T+6 -0.180；安慰剂均值 -0.0384、SD 0.3777；高温簇仅 1 个不作判定 | `07_event_study.py` | F23–F25 | `event_study_curves.csv` |
| 07 | 2026-07 暴雨的天气异常程度、市场响应及是否符合历史规律（Q5） | T0=2026-07-13；派生事件窗 07-11~07-15；分析窗 T-14~T+42；官方通报 6 条（仅定性佐证） | ERA5 派生量化口径；事件相对化稳健 z；与 STEP 12 历史雨事件同口径对照 | 单日最大降水 **173.9mm（第 1/2083）**、3 日累计 **221.1mm（第 1/2083）**、过程 246.8mm；相对 1991–2020 同期 z≈21.2；2026 年 7 月总量 **424.0mm**（2021=111/2022=267/2023=210/2024=355/2025=171）；价格案例事后 **+0.315** 落历史 CI [-0.405,+0.451]（p=0.232）；成交量 **-0.445** 低于历史 CI 下界（p=0.154）；逐品种 8/20 落 CI 内；黄瓜价格 z +3.44/量 -1.52；市级灾损无公开统计 | `08_case_2026.py` | F26–F28 | `case2026_weather.csv`、`case2026_vs_history_percrop.csv` |
| 08 | 传导链两环节能否成立；是否存在中介 | 面板 14,100 行；5 hazard × 2 滞后窗 | 第一阶段 volume_z~Σweather+月FE+年趋势+周末/节假日（逐品种 HAC(14) + pooled cluster-by-date）；第二阶段嵌套 A→C→B；中介 = β(W→V)×β(V→P\|W)，日期移动块 Bootstrap（B=500）；禁用完整日期 FE | 第一阶段逐品种 100 个天气系数 **FDR 显著 0/100**；A→C 天气系数塌缩（R² A≈0.1→C≈0.95）；**C→B 天气系数平均绝对变化 0.0007（中位 0.0005）**；逐品种 volume 系数 FDR **0/10，全部 \|β\|<0.012**；中介 10 个间接效应 **全部 CI 含 0**，量级 ≤1e-3；价格滞后系数 0.94~0.975；链式传导在该尺度上**无统计支持** | `10_transmission.py` | F30–F31 | `transmission_stage1.csv` |

### 表 5.1-C 异质性、机制与预测层

| 编号 | 研究问题 | 数据 | 方法 | 主要结果（保留数字） | 代码 | 图 | 表 |
|---|---|---|---|---|---|---|---|
| 09 | 品种风险画像、冲击指纹聚类与市场韧性（H4） | 8 个清洁雨簇；指纹 T-7..T+14；韧性谷底 T+0..T+21、恢复观察至 T+42 | 画像；Ward 层次聚类（20 条曲线 22 维，K 由 silhouette 事后选择）；恢复定义 z_rel(t)≥0.9×trough_z；不构造综合指数 | **全部品种天气敏感度未过 FDR、无品种存在可支持阈值**；聚类 **K=2（silhouette=0.44）**，**黄瓜·价格独立成簇（谷底 z=-1.18，T+9）**；其余 19 条浅谷（量谷底 -0.18/价 -0.22；簇均值价谷深 -0.70）；韧性删失 量 11/80、价 17/80；恢复天数中位 1~4 天；H4 仅描述性支持 | `11_crop_heterogeneity.py` | F32–F33 | `crop_risk_profile.csv`、`fingerprint_curves.csv` |
| 10 | 本地上市窗口 × 极端天气是否存在额外放大效应 | `crop_calendar.csv` 22 行；`crop_agronomy.growth_stage`；主口径露地/次口径全部本地行 | 以本地采收上市窗口（harvest_start~harvest_end）作 Local Crop Stage 代理；交互回归 `y=b0+b1z+b2(z×in_window)+b3in_window+b4holiday`，HAC(14)；按口径家族 BH-FDR（主 60、次 90） | 主口径可用品种 **6/10**、次口径 **9/10**；西红柿/青椒/茄子本地行全为设施→主口径无窗口；主口径逐品种交互 FDR 显著 **0**、次口径 **0**、pooled 20 个 FDR 显著 **0**（露地价格×precip_3d b2=+0.0300，FDR p=0.9077）；**NOT SUPPORTED** | `12_phenology.py` | F34–F35 | `phenology_windows.csv` 等 5 张 |
| 11 | 年度尺度生产—气象关系能否作机制补充 | 市级 2017–2025；蔬菜仅 4 观测年（2017–2019、2025）；生长季气象仅 2021–2026 | 描述性趋势/anomaly、简单相关、单变量简单回归；**不训练任何模型**；不插补 | 蔬菜×气象重叠年仅 [2025]→**相关分析不可行**；粮食×气象 n=5 仅探索性；趋势：玉米产量 +30.0%（2,576,628.7→3,349,000 吨）、水稻产量 -19.9%、大豆面积 +35.9%、薯类产量 -44.0%、小麦产量 -66.7%；粮食单产 vs 生长季降水 r=**-0.960**、产量 r=-0.925；回归自由度仅 3（`inference_allowed=False`）；**蔬菜年度层 NOT SUPPORTED** | `13_yearly_production.py` | F36–F38 | `yearly_production_long.csv` 等 6 张 |
| 12 | 复杂模型是否优于简单基线；天气是否有样本外预测力 | train 2021-01-01~2024-12-31（9,850 行）/valid 2025（2,500）/test 2026-01-05~09-14（1,750） | 2 目标口径（hist/strict）× 3 特征口径（`F_wx`/`F_lag`/`F_now`）× 6 模型（mean/persistence/seasonal_naive/elasticnet/gam/lightgbm）；无 shuffle；Prep 仅 fit 训练集；Rolling Origin 扩张窗（2024/2025/2026）；MAPE 全 NA | test 价格最优 **baseline_persistence R²=0.9424**、RMSE 0.1966；elasticnet 0.9416/gam 0.9365/lightgbm 0.9322 均**未超越**持续性基线；`F_wx` 天气口径 R² 为负（-0.4351）；滞后1自相关 hist price test **0.9715**/volume 0.8424；`gain_from_weather`：price **-0.2430**、volume +0.6067；`gain_from_persistence`：price 1.3767、volume 1.1506 | `14_prediction.py` | F39–F42 | `model_metrics_by_crop.csv` 等 |
| 13 | 哪些天气变量最重要、风险快速变化区间、品种响应曲线是否不同 | `models/mainsplit_hist_*` LightGBM（训练 ≤2024-12-31）；test 2026（1,750 行） | SHAP 平均绝对值排名；ALE（20 箱，主）与 PDP（25 点，对照）；逐品种单训 LightGBM 的 ALE；`causal_claim_allowed=false` | 价格 top1 = `price_anomaly_z_hist_lag1` SHAP **0.4389（占比 0.5039）**，天气最高 `precip_7d_lag1d` 0.0183（第 4）；成交量 top1 = `volume_anomaly_z_hist_lag1` **0.4123（0.4374）**；仅天气口径价格最高 `soil_moisture_0_7_lag14d` 0.0873；**天气特征合计 SHAP<5%** | `15_model_explain.py` | F43–F45 | `model_ale_curves.csv`、`model_pdp_curves.csv`、`model_ale_by_crop.csv` |
| 14 | 无灾害/改变严重度/增加供应缓冲下模型估计的量价缺口（Level D） | 事件窗 2026-07-12~07-17；模拟 2026-07-10~07-31 | 递归链模拟（天气→量→价）；方法A（1991–2020 同期正常值）/方法B（2021–2025 同季无灾害日中位数 n=165）；配对残差 Bootstrap（B=100）；严重度 {0.5,1.0,1.2,1.5}；缓冲 {10,20,30}% | **World0 门控 FAIL**（price r2 **-0.4683**、volume **0.0839**，门限 0.1）；World1A POOLED 缺口 价格 **-0.3563 z（-14.08%）**、成交量 -0.0795 z（-0.73%）；严重度 1.2→1.5 无加速；供应缓冲 avoided≈0（avoided_fraction=-0.0004）；一切缺口仅作"模型外推演示" | `16_counterfactual.py` | F46–F49 | `counterfactual_gap.csv`、`counterfactual_gap_summary.csv` |
| 15 | 核心结论在 5 个设计维度下是否 Stable/Sensitive/Unsupported | 2026-07-13 事件；500 次 placebo | 维度1 基线方法（hist vs stl）；维度2 事件窗（-7/+14 vs -14/+21）；维度3 模型族；维度4 天气指标（1d/3d/7d）；维度5 placebo；Bootstrap | 三模型族**价格缺口全为负（Stable）**：lightgbm -0.3563/elasticnet -0.4902/gam -0.2688；**成交量缺口异号（Sensitive）**：-0.0795/+0.0499/+0.4232；placebo 雨价格 0.0169 vs p50 -0.0241（percentile 0.564）、成交量 0.0746（0.686）均"不可分辨于 placebo" | `17_robustness.py` | F50–F51 | `robustness_baseline_methods.csv`、`robustness_event_windows.csv` |
| — | 补充扫描（R02 成交量趋势、R10 累积降雨窗口） | 面板；precip 1/3/5/7/14d | OLS+HAC；单 lag 分布滞后 + 独立家族 BH-FDR | （登记于 `results_registry.csv`；报告见 `src/18` docstring） | `18_research_supplement.py` | F52 | `trend_volume_by_crop.csv`、`precip_window_comparison.csv` |
| — | 补充扫描（逐年画像、扩展气象、土壤分层、极端日对比） | 面板；humidity/wind/radiation/et0/dew_point/pressure/cloud/temp_mean；土壤 7-28/28-100 | HAC(14)，独立家族 BH-FDR；土壤 z 用观测期 LOO；极端日对比（Welch SE） | （登记于 `results_registry.csv`） | `19_pairwise_supplement.py` | F53 | `annual_market_by_year.csv`、`weather_extra_scan.csv`、`soil_layers_scan.csv`、`extreme_day_contrast.csv` |
| 16 | 区县级（年×区县×作物）生产与气象数据质量 | 《沈阳统计年鉴》分区县表 2018–2024 × 8 农业区县；区县 ERA5 2015–2025 | 覆盖矩阵、单位一致性、面积×单产≈产量、区县合计 vs 市级合计、公报抽样、异常清单 | 面板 **1,190 行**（full **1,167**）；气象日度 32,144 行、每区县 4,018 天、关键列缺失 0%；逻辑校验 通过 945/冲突 33/无法校验 201；**2023 年绿豆异常**（区县合计 4,246 吨 vs 市级 15 吨）；草莓区县合计 vs 市级 -14.9%~-28.6%；稻谷约 -5.4%~-6.6% | `25_district_panel.py`、`26_district_qa.py` | 无 | `district_qa_consistency.csv` 等 |
| 17 | 如何补齐区县农业生产与区县天气数据 | 年鉴 3-4/3-5/3-6 分区县表；区县公报/年鉴；Open-Meteo Archive | PyMuPDF words(bbox) → y 聚类成行 → 行内按 x 合并碎词 → 表头列中心归位 | 生产主源 2018–2024（+康平 2015–2017）；天气 2015–2025；已知异常原样保留：2023 卷绿豆行上游异常、区县合计<市级、公报抽取越界 `suspect_scope(>100%)`、**于洪区蔬菜公报 8.68 万吨 vs 年鉴 17.23 万吨**、ERA5 2020–2024 ≥35℃ 高温日数为 0 | `20`–`28`、`run_district.py` | 无 | 无独立表（引用 QA 报告与 `source_registry.csv`） |

### 表 5.1-D 结论性与汇总文档

| 文档 | 内容要点 |
|---|---|
| `MILESTONE_1_REPORT.md` | 五问 Q1–Q5；量价领先滞后补充（`price_z(t) ~ volume_z(t-k)`，k=-14..+14，HAC(14)）。Q1 未发现稳定证据（FDR 0/8,680）；**Q2 存在稳定同日负共变**（10/10 品种同日系数为负，范围 -0.037~-0.275，方向一致二项 p≈0.002；FDR 显著 **西红柿 -0.275、青椒 -0.214**），但**领先方向不可识别**（290 检验 FDR 显著 19 个但不成峰）；Q3 无可识别 lag；Q4 NOT SUPPORTED；Q5 价格符合历史规律、成交量边缘负偏不可分辨。交付：结果登记 103 条、图 31 张、表 46 张、阻断 5 条 |
| `BLOCKERS.md` | soil_moisture 官方基线全 null（10,958 天）→ 降级观测期 LOO（A→B）；芸豆设施行无采收日期跳过；韭菜全年窗口不可识别；蔬菜年份断裂（2017/2018/2019/2025，缺 2020–2024）；水果/瓜果/蔬菜重叠年份不足 4 年 → 不计算相关系数 |
| `DECISION_LOG.md` | 全局决策（仅沈阳、10 品种、证据分级 A/B/C/D、volume 禁写吨、LOO 主方法、train≤2024/valid 2025/test 2026、F_wx/F_lag/F_now、World0 门控 R²≥0.10）；降级/停用：**停用 xgboost（环境未装，用 lightgbm 替代）**、停用 `to_markdown`（缺包，自实现 `_md`）；异常：Rolling Origin 实际 3 折<配置 4 折 |
| `LIMITATIONS.md` | 数据/功效/模型/方法学红线/外部效度 5 类；原则"**未发现 ≠ 不存在**" |
| `reports/01_沈阳研究总报告.md` | 把上述研究点重组为 G1–G10（基础两两）、C1–C7（复杂关系）、S1–S6（专题）、第四部分（整城问答 Q1–Q7）+ 附录 A/B/C |
| `reports/02_沈阳最终总结.md` | RQ1–RQ10 与 H1–H6 逐条回答；第 7 节交付物复选框；第 9 节最终结论 |
| `reports/03_沈阳研究索引.json` | 结构化索引：`layer1_basic_pairwise/layer2_complex/...`、每研究点 `id/title/frontend_text/figure/table` |
| `reports/04_沈阳区县农业生产与气象数据.md` | 区县数据补充成果（六问：找到什么/哪些区县最好/哪些作物可多年/仍缺什么/生成哪些文件/下一步可做什么） |

**旧版净结论（三处最一致）**：
1. 天气→量价在日度/事件口径均**不可分辨于噪声**（THR/LAG/EVENT 三处 FDR 全阴性）；
2. 预测高 R²（0.94）**来自持续性而非天气**（天气口径 R²<0）；
3. 唯一稳定结构为**量价同日负共变**（Level B）。

---

## 5.2 旧版存在什么方法问题

> 逐项列出，均附文件+行号证据。判定列表示该问题在旧版中的**实际严重度**。

| # | 方法问题 | 证据 | 严重度 |
|---|---|---|---|
| 1 | **多重比较 family 定义混口径** | `src/05_lag_analysis.py:193` 把 `metric=z` 与 `metric=pct`、7 个 hazard 混入同一 BH 家族，使"全家族"不可复现为单一研究假设 | 中 |
| 2 | **独立性假设不成立但未修正** | 10 品种共享**同一条天气序列**；`src/05_lag_analysis.py:482-483` 明说"跨品种的检验并非相互独立"，但计算仍按独立 BH，未用 BY/staggered | 中 |
| 3 | **部分结论未做多重校正却作显著性判定** | `src/03_descriptive.py:96-108` 价格年化趋势 10 品种无 FDR，正文按 `p<0.05` 判"显著"（`03:424-428`）；`src/18_research_supplement.py:78-89` 成交量趋势同样无 FDR 却登记 `evidence_level="A"`（`18:103`） | 中 |
| 4 | **事件研究逐 offset 的 CI 未校正** | `src/07_event_study.py:329`（报告 `07:336-337` 已声明"仅探索性"） | 低 |
| 5 | **残差 Bootstrap 假设 iid** | `src/16_counterfactual.py:395-406` 直接 `rng.choice(resid[t], ...)` 无块结构；报告 `16:628` 自认"块长=1 的简化"。在 AR(1)≈0.97 序列上低估不确定性 | 中 |
| 6 | **Welch 近似忽略自相关** | `src/19_pairwise_supplement.py:238` `se=sqrt(var_a/n_a+var_b/n_b)`，其 p 值随后进入 FDR（`19:251-252`）；序列相关下 SE 偏小 | 中 |
| 7 | **HAC 带宽固定 14 与高度持续性不匹配** | 价格异常 AR(1)≈0.97（`09:208`）；`src/05_lag_analysis.py:97` 窗聚合含最长 14–30 天窗（长度 17），HAC=14 < 窗长 | 中 |
| 8 | **慢变变量伪相关风险** | `src/10_transmission.py:107-110` 用 0-2/3-14 天窗口均值作暴露，控制仅 `month FE + year_t + 周末/节假日`（`10:126-132`）；`src/06_threshold.py:612` 明确不放月份/趋势项；`soil_moisture_z` 用观测期 LOO 基线（`01:282-300`），其残差季节性与价格残差季节性可能共变 | 中高 |
| 9 | **物候交互控制最薄** | `src/12_phenology.py:302-319` 设计矩阵仅 `hazard_z`、`hazard_z×in_win`、`in_win`、`is_public_holiday`（pooled 加 crop FE），**无 month/趋势**；而 `in_win` 是固定季节窗口哑变量，交互项与季节共线风险高 | 中高 |
| 10 | **主预测目标 `hist` 口径含测试年之后年份** | `src/14_prediction.py:14-16` 自述"留一年法基线取自其他年份，含测试年之后年份"；`14:72` `TARGETS={"price":"price_anomaly_z_hist",...}`。对训练年（如 2021）其基线含 2022–2026 → 训练标签被未来污染。缓解：额外造 `strict` 口径（`14:73-74`、`14:123-140`），但**主结论仍用 hist** | 中 |
| 11 | **方法A（STL）含目标年却进入稳健性维度** | `src/04_deseasonalize.py:12-13`、`04:418-422`；被 `src/05_lag_analysis.py:591` 与 `src/17_robustness.py:76-78` 引用 | 中 |
| 12 | **模型选择存在结果导向兜底** | `src/06_threshold.py:279-288` 若无 FDR 通过组合则取 `wald_p` 最小者做断点（已标 exploratory）；`src/11_crop_heterogeneity.py:108-117` 用 silhouette 在同数据上事后选 K（无 CV/稳定性检验）；`src/14_prediction.py:630-633` F41 按 test RMSE 最优挑模型作图；`src/17_robustness.py:236,245` 稳定/敏感阈值（≥16/≥12）为硬编码武断值 | 低中 |
| 13 | **代码与文字不一致（可核查的诚实性问题）** | ①`src/05_lag_analysis.py:500-502` 报告称"只报通过 FDR 的结论"，但登记逻辑 `05:616` 为 `if not (peak_fdr_p<0.05 or peak_p<0.05)`——**未校正 p<0.05 也被登记**；②`src/19_pairwise_supplement.py:304` 图注称"经 HAC 带宽扫描（14→90）后无稳定显著项"，但代码只用 config 的 `HAC_LAGS`（14）（`19:56`）——**声称的带宽扫描不存在** | 中 |
| 14 | **样本量/功效** | 名义 14,100（`09:325`）；**有效 n_eff≈22–79**（`06:128-140`、`09:174-175`）；极端段 >50mm 仅 41 天、>100mm 仅 6 天（`06:694-696`）；年度层蔬菜 4 年、粮食 5 年（`13:16-27`）；预测训练仅 4 年（`14:837`）。**代码已充分承认** | 高（已承认） |
| 15 | **event 数量** | 雨簇 **8**（`07:306-307`、`11:63`）、高温簇 **1**（`07:340-344`）。**已承认**"样本量不足以给出可信的平均曲线与 CI" | 高（已承认） |
| 16 | **相关与因果的边界** | 大量显式免责（`05:452-453`、`10:457-459`、`15:8-9`、`16:561-562`）；残留：`src/10_transmission.py:358` 用因果箭头 `β(W→V)×β(V→P\|W)` 并以"中介/传导"命名；`src/08_case_2026.py:433-435` 由零结果推出"市场韧性/外部供应缓冲的间接迹象"（null → 机制）；`src/11_crop_heterogeneity.py:8-9` 命名 `shock magnitude/price shock` 隐含因果 | 低中 |
| 17 | **批发市场被隐含当作生产端** | 红线执行到位（`12:9-13`、`00:154-157`、`01:14`、`03:406-407`、`13:8`、`09:259` 均明确"产地未知/禁写吨"）；但残留措辞：`src/03_descriptive.py:483` 图 3 目的"供应是否存在季节性"、`03:500-501` 把成交量异常读作"供应端…短期冲击"、`src/05_lag_analysis.py:557` 图 16 目的"供给端响应比价格更早还是更晚"、`src/10_transmission.py:581-583` "天气冲击不经由本地成交量传导至价格" | 低 |

---

## 5.3 旧版存在什么写作问题

| # | 问题类型 | 证据（文件 + 位置 + 原文） |
|---|---|---|
| 1 | **AI 套话 / 元话语 / 内部流程说明混入正文** | `reports/01_沈阳研究总报告.md#L3-L12` 正文开篇是交付物说明：`> **研究正文（单一内容源）** — 论文、竞赛报告、PPT、答辩、前端展示一律以本文为准。`；`> **本文组织原则**：先做…保证每一部分都能独立成篇…`。`reports/02_沈阳最终总结.md#L14` 把内部验收规则写进结论：`（§七十二 要求：数据不支持时写 NOT SUPPORTED BY CURRENT DATA…）`；`02#L67/L70` `（§五十六）`/`（§六十二红线）`；`02#L133` `**SHENYANG ANALYSIS COMPLETE**（以"阴性结论完整"为完成标准）。` |
| 2 | **空泛总结（无数字、无指向）** | `02#L148-L150` 全文最终结论整段无一个数字；`01#L463` 悬空指向：`这种"天气侧确凿、市场侧平静"的落差，正是 C3 事件研究与 C5 韧性要处理的核心问题。`；`01#L1123` `这两个"错位"是理解沈阳市场的关键`；`reports/04_...md#L131-L144` 只见能力清单、无结果：`数据现在支持以下研究（**仅说明能力，未执行**）` |
| 3 | **重复内容** | ①**三目录逐字节相同**（md5 实测）：`reports/01_沈阳研究总报告.md` ≡ `workspace/SHENYANG_RESEARCH.md` ≡ `_legacy_deliverables/research/SHENYANG_RESEARCH.md`（`5057fafa…`）；`02_沈阳最终总结.md` ≡ `SHENYANG_FINAL_REPORT.md`（`25c9607f…`）；`03_沈阳研究索引.json` ≡ `SHENYANG_RESEARCH_INDEX.json`（`87ab5292…`）；②`01#L1119-L1123` S1 整段 ≈ `01#L126-L127` G1 结论原句；③`01#L1152-L1155` S6 复述 C6/C7；④`01#L1161-L1195` 第四部分第三次复述；⑤`02#L35-L83` RQ1–RQ10/H1–H6 逐条复述 01 的 G/C；⑥`03#L97/L138/L176/L213` F53 同时是 G2/G3/G4/G5 的 primaryFigure；⑦`source_registry.csv#L9-L10` `于洪区-bulletin--1` 与 `于洪区-bulletin--1-4953511` 同标题同 URL |
| 4 | **方法术语堆叠** | `01#L20` 摘要句堆 8 个术语：`…留一年法去季节化（无未来信息泄漏）、Newey-West HAC 稳健标准误、BH-FDR 多重检验校正、簇级 Bootstrap 与安慰剂零分布、严格时间切分与扩张窗验证…`；`01#L736` `自然样条基（df=7，残差化后 5 个非线性自由度）对线性的 Wald-F，HAC(14)，全家族 BH-FDR；GAM（pygam, n_splines=8）…`；`01#L1056` 内部步骤号当术语：`模型为 STEP 23 持久化的 LightGBM（训练 ≤2024-12-31）` |
| 5 | **"看起来专业但不知道研究了什么"** | `01#L3-L12` 开篇 10 行全是口径/组织说明，无研究问题、无结论；`02#L112-L133` 交付物章节是 STEP 复选框清单：`- [x] weather-market lag（STEP 10；阴性）`；`03#L35-L40` 直接暴露结构字段：`"layer1_basic_pairwise": "G1–G10，一个关系 = 一个研究点…"` |
| 6 | **结果与讨论混写** | `01#L444-L445` 结果区写机制解释：`**但一个反直觉的细节**：极端日的 \|z\| 均值普遍低于普通日…这提示…更可能来自普通日一侧的基准漂移…`；`01#L236-L250` 结果区下判定：`#### 关于"风速 × 成交量"这一唯一稳健信号的专项诊断 … 判定：这是**慢变共同趋势的指纹**…`；`01#L883` 结果区放解释性结论：`**④ 关键的模型塌缩证据**：…由**价格自身持续性…与天气的季节性共动**驱动。` |
| 7 | **标题不是真正的研究标题** | `02#L1` `# SHENYANG FINAL REPORT — 极端天气冲击下城市农产品市场供应—价格传导…`（英文工程名）；`01#L41/L663/L1119` 章节标题为内部编号+类目：`## G1 时间 × 市场`、`## C1 滞后结构研究（Lag）`、`## S1 市场基础规律（G1）`；`03#L46` 索引 title 全是问句：`"title": "时间（月份 / 季节 / 年份）与沈阳批发市场是什么关系？"`；`04#L1` 标题带轮次说明：`# 04 沈阳区县农业生产与气象数据（本轮数据补充成果）` |
| 8 | **G1/G2/C1 等内部编号暴露给读者** | `01#L180/L195/L422` 行内引用编号：`（详见 C1）`、`（见 C4）`、`同时为 C3 的事件研究确立天气侧的事实基础`；`01#L1199-L1220` 附录把图映射到编号：`| F29 | ... | G6 |`；`02#L38/L6` 用 STEP/RQ/H/§ 编号；`03#L43` `"id": "G1"`；前端明确展示编号（`AgriScope/docs/COPY_AUDIT.md#L52`、`AgriScope/src/features/research/ResearchPointPage.tsx#L166`） |
| 9 | **引用不存在的文件 / 路径不成立** | `01#L4` 称"研究过程证据保留于 `reports/` 下 19 份阶段报告"，但 `shenyang/reports/` 下只有 01–04+README，17 份阶段报告实际在 `workspace/reports/`；`02#L117` 引用 `04_DESEASONALIZATION.md`，实际文件是 `workspace/reports/03_DESEASONALIZATION.md` |
| 10 | **人类报告目录内图片全部断链** | `01#L122` 用 `![...](outputs/figures/Fxx.png)`，但 `reports/` 下只有 `figures/`，无 `outputs/figures/` → 同一内容在 `workspace/` 可解析、在 `reports/` 不可解析 |
| 11 | **目录定位自相矛盾** | `reports/README.md#L3` 声明该目录只放"给人看的研究成果、普通阅读不需要进入 workspace"，但 `01` 正文反复指向 `outputs/results_registry.csv`、`src/18_research_supplement.py`（`01#L1224-L1239` 附录 B） |

---

## 5.4 旧版存在什么前端问题

> 实测消费方：`AgriScope/scripts/sync-shenyang-content.mjs` → `AgriScope/public/research/shenyang/*`。

| # | 前端问题 | 证据 |
|---|---|---|
| 1 | **Markdown 字符串截断** | `frontend_text` 是正文 `### 前端一句话` 的**截断副本**，每截一次丢一个结论分句：G1 `01#L138` 完整句结尾为 `；六年间价格整体没涨跌，到货量则有 7 个品种出现了明显但方向不一的长期变化。` → `03#L71` 止于 `到货量却全年几乎不动。`；C1 `01#L720` 结尾 `——所谓"累积雨量更重要"其实是标准差变大造成的错觉。` → `03#L454` 止于 `也没有哪个窗口更强。`；C2 `01#L783` 结尾 `；80 次非线性检验里那 9 个"显著"，随机情况下也会出现 4 个。` → `03#L490` 止于 `不足以定位任何临界点。`；C3 `01#L849` → `03#L535` 止于 `落在安慰剂分布的正中间。`；C7 `01#L1113` → `03#L386` 止于 `只能当演示。` |
| 2 | **整段被丢弃（另一种截断）** | 全文最关键口径声明（成交量单位 unknown、ERA5 非气象站实测、证据分级）位于 `01#L3-L12` 的引用块；同步切分逻辑从 `## 0. 研究摘要` 才开始收集 → 该 blockquote **既不入 abstract.json 也不入任何 article** |
| 3 | **文章边界串联（上一篇结尾黏进下一篇开头）** | `AgriScope/public/research/shenyang/articles/abstract.json#L24-L29` 尾部出现 `# 第一部分 基础两两关系` + `> 本部分每个研究点…`；`G10.json` 含 `第二部分`；`C7.json` 含 `# 第三部分 六大专题总结`、`## S1`~`## S6`、`# 第四部分 沈阳整城分析`、`## 附录 A/B/C`（该文件 25,409 字节，其余 article 仅 3–7KB） |
| 4 | **串篇根因代码** | `AgriScope/scripts/sync-shenyang-content.mjs#L113-L136`：`const researchMatch = /^##\s+([GC]\d+)\b(.*)$/.exec(line);` —— 只认 `## G1`/`## C1`；`# 第X部分`、`## S1 市场基础规律（G1）`、`## 附录 A`、`## 1. 沈阳面临…` 全部不匹配，内容被无边界追加到"上一个匹配到的研究点"（C7）或被 abstract 吞掉 |
| 5 | **source 指向本地文件** | `AgriScope/public/research/shenyang/index.json#L883-L887`：`"sourceOfTruth": { "research_doc": "SHENYANG_RESEARCH.md", "process_reports": "reports/01~15 + MILESTONE_1_REPORT.md", "lineage": "outputs/results_registry.csv" }`；该字段被直接当"来源声明"渲染（`AgriScope/src/features/research/workspace/ResearchEvidenceRail.tsx#L36-L39`：`<dt>来源声明</dt><dd>{sources.length > 0 ? sources.join('；') : …}</dd>`）；索引中的图/表路径亦为本地相对路径（`03#L55` `"figure": "outputs/figures/F08_seasonal_heatmap_price.png"`）；来源登记表用本地落盘路径做"来源"（`source_registry.csv#L2` `local_file = data/raw/district_production/yearbooks/SY_yearbook_2019_data2018.pdf`） |
| 6 | **source URL 不是真正的原始来源** | `reports/03_沈阳研究索引.json` 全文**无任何 `source`/`url` 字段**（已检索确认）——真实原始来源（沈阳市发改委菜篮子信息发布平台、Open-Meteo ERA5、沈阳统计年鉴）从未以 URL 形式出现；逐图来源被判定为缺失（`AgriScope/docs/SOURCE_GAPS.md#L27-L36`：`索引只给了图片路径 figures[]，没有逐图来源字段`）；唯一登记的 URL 本身是爬取残留（`source_registry.csv#L9-L11`：`https://www.syyh.gov.cn/zwgk/fdzdgknr/tjxx/tjgb/./202512/t20251212_4953511.html`，含 `/./`，且 `year`/`data_year` 为 `-1`）；年鉴 URL 口径不一致（`source_registry.csv#L2-L8` 落地页 vs 第 7 条直链 PDF 混用） |
| 7 | **文章摘要与正文重复** | `abstract.json#L8-L20` ≡ `01#L18-L30`（逐句相同）；`03#L397-L407` summary_blocks 是 §0 的压缩版；同屏四处重复同一结论：`ResearchPointPage.tsx#L168`（页眉 frontendText）、`ResearchSummary.tsx#L20-L31`（摘要面板）、`ResearchInsightDock.tsx#L21`（`当前结论 = point.conclusion`）、article 的「结论」段；`03#L414-L428` 整城问答 ≡ `01#L1161-L1195` 第四部分 |
| 8 | **图没有对应研究问题** | `AgriScope/src/domain/research/adapters.ts#L91-L102` `caption: point.frontendText`（且该文案本身已被截断）→ 同一研究点下每张图共用一句与图无关的说明；G4（土壤×价格）挂阈值图（`03#L177-L180` 含 `F20_threshold_gam_pd.png`，而 `01#L1213` 归 C2）；G2 挂滞后曲线（`03#L98-L102` 含 `F17_lag_curves_precip_3d.png`，`01#L1211` 归 C1）；G3 挂传导图（`03#L139-L143` 含 `F30_transmission_stage1_heatmap.png`，`01#L1215` 归 C4）；G6 挂传导图（`03#L249-L252` 含 `F31_transmission_stage2_compare.png`）；F53 被 G2/G3/G4/G5 同时当主图（`03#L97/L138/L176/L213`）；`reports/04_...md` 一个完整研究交付物 **0 张图** |

---

## 6 审计结论（事实性归纳，不含评价）

1. v1 的**研究覆盖面广**：29 个脚本、19+4 份阶段报告、100 张表、53 张图、143 行结果血缘，覆盖描述性/去季节化/滞后/非线性/事件/案例/传导/异质性/物候/年度生产/预测/解释/反事实/稳健性/区县数据 16 个模块。
2. v1 的**方法纪律已在本仓库内自证**：族定义、LOO 防泄漏、块 Bootstrap、安慰剂、预登记判定规则、阴性结果登记均已实现；同时**存在 17 项可核查的方法问题**，其中 2 项为**代码与文字不一致**（`05:616` 登记未校正 p、`19:304` 声称的 HAC 带宽扫描不存在）。
3. v1 的**写作问题集中在 8 类**，核心症结是正文保留了过多"研究工程内部语境"（STEP/§/RQ/G-C 编号、单一内容源声明、交付清单、方法术语链），且结论在"研究点 → S 专题 → 第四部分 → 02 总结 → 03 索引 → 前端摘要"链上被**复述 5 次**。
4. v1 的**前端问题 8 项全部命中**，根因代码唯一：`sync-shenyang-content.mjs#L113-L136` 的切分正则只认 `^##\s+([GC]\d+)`，导致篇章边界串联、头部口径被丢弃、图与来源全部失配。
5. v1 的 `reports/01`、`02`、`03` 与 `workspace/SHENYANG_RESEARCH.md`、`SHENYANG_FINAL_REPORT.md`、`SHENYANG_RESEARCH_INDEX.json` **逐字节相同**（md5 实测），存在三份同源副本。

> 以上为审计事实。**v1 文件在本轮中未被创建、修改或删除。**
