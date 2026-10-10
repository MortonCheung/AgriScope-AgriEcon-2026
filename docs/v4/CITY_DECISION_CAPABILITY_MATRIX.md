# AgriScope V4 Phase 0：六城决策与已发布运行资产审计

审计日期：2026-10-10（Asia/Shanghai）。只读检查代码、正式 Registry、运行快照、已发布研究 CSV/JSON；未改产品、正式模型、原始研究。所有下述产品建议仅依赖 `AgriScope/runtime`，不依赖外层 `data/models/archive/reference`。

## 1. 关键结论与真实源码落点

1. `backend/app/services/capability_service.py:86` 的 `supported` = `has_price_model && 有通过 crop_capability 的作物 && 市场日期非空`。这是旧 Final 价格推理入口可调用性，不是城市整体是否有决策价值。
2. `frontend/src/features/decision/DecisionCenter.tsx:77` 以该旧布尔值提前返回“决策数据待接入”；`FinalDecisionInput.tsx:38` 同样整页拒绝种植决策。四城真实生产和气候资产被该门禁遮断。
3. `useDecisionCenter.ts:142,160` 又以短期布尔值开启长期查询和长期作物比较。朝阳短期为 true，但 `backend/app/services/long_horizon_service.py:99,145` 明确只支持沈阳，因而朝阳会发起注定失败的长期请求。
4. `backend/app/schemas.py:28` 的 CapabilityResponse 使用 `extra="forbid"`。添加功能级能力需要显式扩展 schema；不能只在 service 多返回字段。前端 `providers/decision/index.ts:14` 的 parser 对旧字段严格验证，但允许额外字段；类型与 parser 仍应显式接入新合同。
5. Final 引擎 `inference.py:343` 先检查 `has_price_model`，失败就返回所有风险、气候、收益为空。因此用户填成本/亩产也不能让无价格模型城市使用旧 Final。这是保护科学边界的真实语义，不应篡改。
6. Final `_profit_block` 已有收入、成本、利润、ROI、保本价公式，但耦合 Final 模型价格与十种蔬菜成本参考；现有 `stress` 接口又只支持单项压力及两组固定组合。复用公式和呈现组件，另建明确“用户假设”的确定性经营工具，不能用旧 forecast endpoint 假装全城已支持。

## 2. 实际运行绑定与 Registry

实际执行 `runtime_snapshot.state()`：绑定 `runtime/data/processed/daily/final_input/extended_snapshot`，状态 LIVE，冻结 Final 版本 `final_v1`，指纹 `b19b187268ee92db`。extended fingerprint 与冻结版本相容；运行快照内容只读。

实际执行六城 capability 与长期 capability：

- 沈阳：短期 supported=true，FULL，市场截至 2026-10-06；10 作物（土豆、西红柿、黄瓜、韭菜、青椒、尖椒、茄子、芹菜、芸豆、甘蓝）。长期 supported=true，但是情景产物。
- 朝阳：短期 supported=true，EXTENDED，市场截至 2026-09-21；8 作物（上述十种去掉尖椒和甘蓝），市场口径为全市均价。长期 supported=false。
- 锦州：短期 supported=false，LIMITED，价格多层级与 OCR 来源，不满足单一口径 Final 模型要求；长期 false。
- 大连、铁岭、丹东：短期 supported=false，INSUFFICIENT_MARKET_DATA；长期 false。

权威生产落点是 `runtime/models/reports/final/FINAL_MODEL_REGISTRY.csv`、`tables/price_model_selection.csv`、`tables/final_model_artifacts.csv`，配合 runtime 中实际可加载 artifacts 和 `FINAL_RUN_META.json`。外层 `models/registry/model_registry.json` updated_at=2026-10-04，比最终冻结报告早，不应作为 Final 推理权限的唯一依据。

- price_model_selection：90 行（沈阳 50、朝阳 40）；包括 7/14/30/60/90 回测，但 Final 能力只把 7/14/30 当模型，60/90 为 scenario_only。
- final_model_artifacts：54 个（沈阳 30、朝阳 24），对应生产的 7/14/30。
- OOT walk-forward folds 为 2024/2025/2026 截尾，非随机 split；价格特征无天气、无 volume。
- 7/14/30 平均 WAPE：沈阳 5.212/7.586/10.819%，朝阳 5.634/8.143/10.814%。这是模型选择回测误差，不能写成当前未来价格保证。
- Registry 中 BASELINE 是经比较胜出的 baseline 路线，仍可称经验证的参考模型，但不能把每一作物宣传为机器学习超过基线。
- scenario_range_by_crop_horizon：50 行全部沈阳；35 widened、15 scenario_range。朝阳缺对应逐作物区间校准报告，不能冒称已校准置信区间。
- `runtime/LONG_HORIZON_V2_REGISTRY.csv` 120 行，80 SCENARIO_ONLY、40 EXPLORATORY_SCENARIO_ONLY，没有生产 VERIFIED 未来预测。沈阳 30–180 天长期功能应称市场情景/探索。
- Final audit 中沈阳 14100 价格行（单 wholesale）、朝阳 37129 全品类行（模型只筛 market_average 同口径）、锦州 35123 全品类行（多层级）；大连、丹东、铁岭无 Final market table，但研究层仍有周报/稀疏 B2B 等观察资产。

## 3. 六城逐功能矩阵（当前真实能力与 V4 可实现能力分开）

以下类别来自施工手册：VERIFIED_MODEL / OBSERVATIONAL_ANALYSIS / DETERMINISTIC_CALCULATION / USER_ASSUMPTION_SCENARIO / EXPLORATORY_REFERENCE / NOT_SUPPORTED。

- 沈阳：短期价格=VERIFIED_MODEL（7/14/30，10作物）；长期=EXPLORATORY_REFERENCE；年度生产=OBSERVATIONAL_ANALYSIS（2018–2024，8农业区县）；历史气候=OBSERVATIONAL_ANALYSIS（运行资产六城日值与发布月度暴露表）；市场风险/HRI=模型派生观察指标，不能写行为概率；成本=按来源逐条参考，缺亩产需用户输入；V4 盈亏平衡=DETERMINISTIC_CALCULATION、压力敏感性=USER_ASSUMPTION_SCENARIO。
- 朝阳：短期价格=VERIFIED_MODEL（7/14/30，8作物，扩展参考、全市均价）；长期=NOT_SUPPORTED；年度生产=OBSERVATIONAL_ANALYSIS（结构最新2024）；历史气候=OBSERVATIONAL_ANALYSIS；HRI/市场风险=有 Final 模块但只对可用作物和同口径输出；成本多为历史研究参考而非当前本地统一亩成本；V4 经营工具同上。
- 锦州：短/长期价格=NOT_SUPPORTED；研究市场趋势=OBSERVATIONAL_ANALYSIS（OCR/超市等分层描述，禁止混层比较）；生产=OBSERVATIONAL_ANALYSIS（结构最新2023）；历史气候=OBSERVATIONAL_ANALYSIS；HRI正式输出=NOT_SUPPORTED；V4 经营工具同上。
- 大连：短/长期价格=NOT_SUPPORTED；市场周报/节点=OBSERVATIONAL_ANALYSIS或EXPLORATORY_REFERENCE（周度、价格层级混合，禁止拼成日频本地模型）；生产=OBSERVATIONAL_ANALYSIS（结构最新2024）；历史气候=OBSERVATIONAL_ANALYSIS；当前本地完整作物成本/亩产=NOT_SUPPORTED；V4 经营工具同上。
- 铁岭：短/长期价格=NOT_SUPPORTED；B2B产地行情=EXPLORATORY_REFERENCE（稀疏，质量C）；生产=OBSERVATIONAL_ANALYSIS（结构最新2024）；历史气候=OBSERVATIONAL_ANALYSIS；玉米/水稻成本有2020历史本地参考，蔬菜2013研究参考，不能默认当前成本；V4 经营工具同上。
- 丹东：短/长期价格=NOT_SUPPORTED；特色作物观察=EXPLORATORY_REFERENCE（板栗284、草莓94、蓝莓91等观测，不能虚构连续预测）；生产=OBSERVATIONAL_ANALYSIS（结构最新2022）；历史气候=OBSERVATIONAL_ANALYSIS；本地统一成本/亩产=NOT_SUPPORTED；V4 经营工具同上。

矩阵中的 V4 工具是建议下一阶段实施，当前尚未实现，不能把它写成现状已可调用。

## 4. 可直接用于产品的已发布生产 CSV

### 4.1 五城统一表

目录：`runtime/research/product/{chaoyang,jinzhou,dalian,tieling,dandong}/tables/`。

- `A07_crop_structure.csv`：`crop`、`area_kha`（千公顷）、`area_share`（0–1份额）。每城8类作物，占比合计约1。这是八类已覆盖作物的构成，不是所有农业作物的完整总量。
- `A07_concentration.csv`：`metric,value`；HHI、CR4均0–1，n_crops=8。集中度仅结构指标，非跟风概率。
- `A07_change.csv`：`crop,area_first,area_last,pct_change`；前后面积千公顷、相对变化0–1。花生首年缺失，应保持 null，不填0。
- `A07_total_area.csv`：`year,total_area_kha`，仅2017/2018/2019，不能用作最新2024全部播种面积。生产脚本会在无“农作物总”时汇总粗类，需保留已有统计边界，默认不以该表造全省总量。
- `A07_data_quality_note.csv`：英文编码行另一来源单位不一致，未参与结构。朝阳16行（2025）、大连7行（2025）；其他三城0行。
- 最新年份由 `articles/A07.json` 的研究结果/summary，或 `cross_city/tables/cross_city_production_concentration.csv` 的 `years` 提供。不能使用 CSV 文件更新时间作为数据年。

最新实值：

- 朝阳，2024：玉米370.60千公顷/82.4490%，谷子36.70/8.1648%，高粱28.30/6.2960%；已覆盖8类合计449.49千公顷，HHI0.690736。
- 锦州，2023：玉米317.5/73.9748%，花生61.7/14.3756%，水稻37.4/8.7139%；8类429.20千公顷，HHI0.575834。
- 大连，2024：玉米191.8/66.8293%，大豆42.9/14.9477%，花生19.1/6.6551%；8类287.00千公顷，HHI0.479815。
- 铁岭，2024：玉米445.8/84.5407%，水稻35.5/6.7322%，花生30.9/5.8598%；8类527.32千公顷，HHI0.723154。
- 丹东，2022：玉米118.9/65.2257%，水稻48.0/26.3317%，大豆8.8/4.8275%；8类182.29千公顷，HHI0.497732。

出处：各城 published article A07、sources.json 中《辽宁统计年鉴》来源；root 数据/研究源不用作为产品读取路径。

### 4.2 沈阳表与区别

`runtime/research/product/shenyang/tables/A07_change_2018_2024.csv`：`crop,district,area_2018,area_2024,area_chg_pct,prod_2018,prod_2024,prod_chg_pct`。

- area字段=公顷；prod字段=吨；变化字段已经百分数（不同于五城 pct_change 0–1）。
- 2018/2024 单年原值，8农业区县；可以对同一 crop 合计区县，明确范围“8农业区县合计”。研究原文写区县合计不等于市级合计（核心5区未单列）。
- 2024 玉米408901公顷、3119023吨；稻谷103543公顷、722008吨；粮食532614公顷、3900292吨；蔬菜及食用菌64001公顷、4011022吨。
- 粮食、谷物、玉米、稻谷、豆类、大豆有包含关系，不能把9条 crop 全部相加造“总播种面积”。可展示单项农业指标，或只对明确互不重叠的玉米/稻谷/大豆呈现构成并注明所选三类范围。

`A07_district_crop_structure.csv`：`crop,district,years,sown_area_median_ha,production_median_t,yield_median_kg_ha`；是2018–2024中位数，不是2024现值。`A07_district_grain.csv` 的 area_median/prod_median/yield_median也相同。不要把这些中位数与五城最新单年面积一起汇总。

## 5. 可直接用于产品的气候资产

五城 `runtime/research/product/<city>/tables/A09_climatology.csv`：17行，2010–2026。列 `year,precip_ann,tmean_ann,precip_gs,tmean_gs`。

- precip=mm，tmean=℃；gs=4–9月（研究脚本 a09_city_special._climatology 明确月份）；ERA5再分析网格、非气象站实测。
- 2026原始日值止于09-14，因此CSV的2026 annual也只是截至数据期的累积/均温。主界面取2025“最近完整年”，2026只能明确写截至09-14，不能作为全年比较。
- 2025 完整年降水/年均温/4–9月降水/生长季均温：朝阳528.8mm/11.4318℃/506.4mm/21.6732℃；锦州566.2/11.5123/535.0/20.9421；大连788.3/12.6814/697.4/20.3563；铁岭805.0/9.6871/743.8/20.7656；丹东1165.0/11.2707/990.4/20.4148。
- 沈阳 product 没有 A09_climatology.csv，不能无声回退到别城。已发布 `runtime/data/model_ready/climate/climate_daily.parquet` 具有六城相同6101天，2010-01-01–2026-09-14；可用同样公式只读汇总出沈阳2025：963.5mm/10.1016℃/897.2mm/20.9967℃（验证与五城CSV逐项相符）。这是基于运行资产的明确派生计算，不修改研究产物。
- `runtime/models/reports/final/tables/climate_exposure.csv` 已发布72行（6城×12月），列 `city,month,n_years,heat_days_mean,heavy_rain_days_mean,ndvi_anomaly_mean,ndvi_is_monthly,note,heat_exposure,rain_exposure,climate_exposure_score`。high-temp阈值>32℃，heavy-rain>25mm，`heat_days_mean`/`heavy_rain_days_mean` 是日频率×30的月等效天数，不能叫精确某月日数；scores是同城月份排名，不能直接给城市灾害损失排名。
- 气候结构与阈值历史暴露属于观察分析，不是未来天气预报、作物减产预测或价格因果。

## 6. 什么可以作为“六城研究区整体”

可以：6座研究城市；各城最近生产年份与主要作物；按统一2025完整年比较六城降水/温度范围；六城共用2010–2025完整历史气候覆盖。2025降水范围528.8–1165.0mm，来源以上六城共同运行口径。省域地图仍覆盖辽宁全部市，但研究总体只能称“六城研究区”。

不能：将不同年份五城八类结构、沈阳区县数据合成辽宁全省总面积/产量；将五城2017–2019 totals冒称2024全省；对跨价格层级求省均价；平均六城气候并称辽宁面积加权气候；把HHI与HRI混为一物。

推荐省视图：标题“辽宁农业观察”，说明“六城研究区”；一个轻量六城主要作物带状/列表区块、最近完整年气候范围与关注区域、城市选择。不强求单一全省农业总数。

## 7. 农事历与成本边界

- crop_calendar_v2.parquet 61行，仅沈阳10/朝阳27/锦州24；甚至包含鸡蛋、牛肉等非种植项和 price-derived harvest month。不能把价格季节性月份当正式农事历；对五城统一规划页不要新增种植适宜性断言。
- phenology 为事件，不是六城统一可执行种植日历。正式引擎也明确不约束种植日历、不执行预算/面积优化。
- crop_cost.parquet 16行：沈阳玉米2024/2025 1276.38/1219.65元每亩；水稻1684.39/1696.64；铁岭2020玉米510、水稻820；辽阳调查作为REGIONAL_PROXY；设施建设不是年度作物经营成本。只逐条呈现来源/年份/生产方式，不能默认代入六城所有作物。
- cost_components.parquet 13行大多 RESEARCH_REFERENCE，包括铁岭2013蔬菜、沈阳2000/2009/2013/2014案例、灵武韭菜、东北温室等；Final cost按 crop跨城归总得到的参考不能叫当前本城成本。
- 用户亩产、亩成本和销售单价显式填写是六城经营工具最稳妥的第一条业务链。不会使用3500kg/亩硬编码默认值冒充本地统计。

## 8. 两种补强方案比较与推荐

方案A：前端直接复用研究Repository取CSV；新增纯函数经营工具；旧能力对象添加功能级标志。优点：修改小，最快形成六城可操作链；缺点：前端承担不同生产单位与年份适配，地图与决策重复逻辑。

方案B（推荐）：新增薄只读 observation 服务（仅runtime），将六城农业结构与气候压缩为稳定业务合同；功能能力聚合仍保留旧 supported语义；前端复用观察摘要 + 独立确定性经营函数。优点：地图/决策用同一指标、单位与证据、避免重复请求；没有重训，也不改 Final。

最小合同建议：

1. 保留现有 `supported,crops,market_as_of,...`，新增 `features` 对象。字段至少 `supported,result_type,data_sources,required_inputs,validated_model,limitations`。键包含 short_term_price/long_horizon_scenario/production_structure/historical_climate/break_even/user_scenario；old supported只控制 old evaluate。
2. observation endpoint 每城返回 `city_id`、`production`（available/period/scope/unit/items/source_paths）、`climate`（available/complete_year/precipitation_mm/mean_temp_c/source_paths/semantics）、`evidence`；省级返回 `scope='six_city_research_area'`、city summaries与同年气候范围，不伪造总量。
3. 经营工具输入：area_mu>0、yield_kg_per_mu>0、cost_cny_per_mu>=0、assumed_sale_price_cny_per_kg>=0、sale_fraction 0–1。成本0则ROI=null；产量/价格/销售比例为0则涉及除法的保本项=null，不能 Infinity。finite验证，缺输入明确提示。模型最新价格只能主动选择作为历史/模型参考，并记录 provenance，不能自动冒充用户假设或本地实测。
4. 公式：sales_quantity=area×yield×sale_fraction；revenue=sales_quantity×assumed_price；total_cost=area×cost；profit=revenue−cost；break_even_price=cost/(yield×sale_fraction)；敏感性对成本、亩产、价格用户改动的组合重新算同式。注明“基于用户设定条件的情景结果”。
5. 未登记城市仍拒绝；功能原始资产缺失则该功能 supported=false，确定性用户工具仍可用，不跨城fallback。
6. 验证重点：六城功能合同、沈阳区县口径、五城年份、千公顷/公顷换算、2026不全年化、朝阳不发长期请求、null和除零、切城市取消旧请求、原Final supported和evaluate回归保持。

## 9. 可复用组件与改动文件范围

后端：capability_service.py、schemas.py、capabilities.py、新增只读 observation_service.py / route；需 main.py 注册 route。research_service 的 path白名单和runtime根可复用，但不要改变其纯透传语义。新服务可 csv.DictReader读取小表，气候历史只读parquet复用pandas；不要复制大规模研究资产到前端。

前端：DecisionCenter外壳、DecisionVisuals格式化、EvidenceDrawer、formal数据provider、researchRepository表请求/缓存可复用；domain新增经营计算纯函数，Planning工具放feature/decision；types/parser加功能能力；useDecisionCenter按短期/长期各自能力开请求。

无需修改模型、研究文章、Registry、Daily、原始统计口径。Phase 5完成标准为六城每城可明确填写真实输入/假设→计算收入成本利润保本→查看生产气候与来源→返回同城状态；不能仅以build通过宣称功能完成。
