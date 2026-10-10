# 00_AUDIT_EXISTING_DATA.md

> 阶段一 · Step1 现有环境只读审计
> 审计对象：(1) 本案例库 `沈北新区 2026 暴雨—玉米案例库`；(2) AgriScope 原项目（`liaoning-agri-risk/`、`data/research/shenyang/`、`liaoning-agri-data/`）。
> 审计方式：**只读扫描 + 复制留档**，未移动/覆盖/删除任何原有数据。
> 审计时间：2026-09-22。

---

## 0. 空间粒度分层（严禁混用）

本研究全程区分以下空间层级，任何数据进入分析前必须先归层：

```
辽宁省  >  沈阳市  >  沈北新区（区/县）  >  街道/乡镇  >  村  >  站点  >  栅格/网格点
```

**关键判据**：`district_crop_*.csv` 中"沈北新区"是**区级单列**（可用）；省级/市级口径**不得**冒充沈北。

---

## 1. 现有可复用数据集清单

| 数据集 | 原路径 | 空间粒度 | 时间范围 | 时间粒度 | 字段 | 来源 | 能否用于沈北 | 问题 |
|---|---|---|---|---|---|---|---|---|
| 沈北玉米播种面积/总产量/单产（分区县） | `data/research/shenyang/workspace/data/processed/district_crop_area.csv`、`..._production.csv`、`..._yield.csv` | 区县（沈北单列） | 2018–2024 | 年 | 作物/面积/产量/单产/来源表 | 沈阳统计年鉴（市统计局）**A** | ✅ 直接可用 | 仅7年；2018、2019 玉米面积同为14084（需留待核）|
| 沈北官方作物数据（区级年鉴） | `data/research/.../bulletins/沈北新区/yearbook_2025_54515cb9b3.pdf`、`yearbook_2022_a670af99a3.pdf` | 区（全区） | 2021–2022、2024–2025 | 年 | 玉米面积/总产/单产；粮食/水稻/大豆 | 沈北新区统计局 **A**（扫描件转录） | ✅ 直接可用（补2025+交叉验证） | 扫描件无文本层，需渲染目视转录；单位口径为“亩/万吨” |
| 沈北日值气象 | `liaoning-agri-risk/01_raw/weather/openmeteo_沈北新区_{baseline,current,extra}.json` | 网格点(42.0035,123.5371) | 1991–2020；2021–2026-09-14 | 日 | 降水/气温/湿度/风速/辐射/ET0/土壤湿度 | Open-Meteo ERA5 **D** | 🟡 仅作背景/基线 | **再分析非观测**，不能写“实测”；网格平滑极值 |
| 沈北逐小时气象 | 本案例库 `02_raw/weather/openmeteo_hourly_沈北新区_YYYY.json`（本研究新采） | 网格点 | 2015–2026-09-14 | 小时 | 降水/气温/湿度/风速 | Open-Meteo ERA5 **D** | ✅ 用于高频暴雨特征 | 同上；102,600行，缺测0 |
| 沈北土壤含水量 | `liaoning-agri-risk/01_raw/soil/openmeteo_soil_沈北新区_YYYY.json` | 网格点 | 2021–2026 | 小时→日 | 0-7/7-28/28-100cm含水量、0-7cm土温 | ERA5-Land **D** | ✅ 前期土壤饱和判据 | 再分析；需转日均 |
| 沈北日照时数 | `liaoning-agri-risk/01_raw/weather/openmeteo_sunshine_沈北新区_*.json` | 网格点 | 2021–2026 | 日 | sunshine_duration | ERA5 **D** | 🟡 辅助 | 再分析 |
| NASA POWER 沈北 | `liaoning-agri-risk/01_raw/weather/nasapower_沈北新区_current.json` | 网格点 | 2021–2026 | 日 | 降水/气温/辐射 | NASA MERRA2 **D** | 🟡 交叉验证 | 再分析 |
| 区县天气年值/农业气象面板 | `data/research/.../processed/district_weather_yearly.csv`、`district_yearly_agri_weather_panel.csv` | 区县 | 2015–2025 | 年 | 生育期温度/降水/极端指标/土壤湿度 | Open-Meteo ERA5 **D** | 🟡 背景 | 再分析；**非观测** |
| 2026-07 官方灾情事件（沈阳） | `liaoning-agri-risk/01_raw/disaster/official_2026/`（HTML/JSON）+ `04_marts/fact_disaster_events_shenyang_2026_official.csv` | 市/区/街道/村 | 2026-07 | 日 | 雨量/响应/转移/设施影响 | 政府门户/沈阳日报 **A/E** | ✅ 现实世界重建核心 | 含6条，均带 URL 与 raw_file |
| 官方降雨观测事件库（省水利厅） | `liaoning-agri-risk/04_marts/fact_disaster_event_observed.csv` | 省/市/县 | 2026-05–09 | 日 | 最大小时/累计雨量出现地、转移、调度 | 省水利厅汛情快报 **A** | ✅ 事件锚点 | 沈北仅1条（2026-08-24 兴隆台 97.1mm/h）|
| 政策/干预文本事件 | `liaoning-agri-risk/04_marts/fact_policy_event.csv` | 省 | 2025 | 日 | 政策类型/机构/摘要/URL | 省发改委等 **A** | 🟡 背景 | 时段为2025，未含2026-07排涝 |
| 作物日历（辽宁春玉米生育期） | `liaoning-agri-risk/00_metadata/crop_calendar.csv` | 省 | 常年 | 旬/月 | 播/苗/雄/丝/灌浆/熟 | 辽宁省统计年鉴等 **B** | 🟡 物候区间 | **区域粒度、非2026沈北实测** |
| 作物农学需求（玉米阶段敏感性） | `liaoning-agri-risk/00_metadata/crop_agronomy.csv` | 区域 | 常年 | 定性 | 温度/水分需求、渍涝风险 | 农技推广资料 **C** | 🟡 机制先验 | 参考阈值，非观测 |
| 沈北统计公报 | `data/research/.../bulletins/沈北新区/bulletin_YYYY_*.html/pdf` | 区 | 2022–2025 | 年 | 农林牧渔总产值分项 | 沈北区政府 **A** | ❌ 无作物面积/产量 | 公报只给总产值，**不含玉米** |
| 沈阳六城价格/成交量 | `liaoning-agri-risk/04_marts/fact_price_city*.csv`、`fact_market_supply.csv` | 市/市场 | 2020–2026 | 日 | 蔬菜/粮油/农资价格、成交量 | 沈阳发改委等 **A** | ⚪ 暂不需要 | 无玉米价格，与玉米单产链不直接相关 |
| 辽宁统计年鉴六城生产 | `liaoning-agri-risk/04_marts/fact_production_yearly_2020_2025.csv` | 市 | 2020–2025 | 年 | 六城×作物面积/产量/单产 | 辽宁统计年鉴 **B** | 🟡 市级对照 | **市级口径**；沈阳含玉米，非沈北 |

图例：✅ 数据足够 · 🟡 部分/需补充 · 🔴 缺关键数据 · ⚪ 当前阶段暂不需要

---

## 2. 复用的既有数据（已复制留档，来源已登记）

复制目的地与 `source_id` 对应见 [DATA_SOURCE_REGISTRY.csv](../01_sources/DATA_SOURCE_REGISTRY.csv)：

- `02_raw/agriculture/shenyang_yearbook_district_crop_{area,production,yield}.csv` → `SRC-SY-YB-DISTRICT`
- `02_raw/agriculture/沈北新区国民经济统计资料_2025年度.pdf`、`_2022年度.pdf` → `SRC-PNB-YB-2025`、`SRC-PNB-YB-2022`
- `02_raw/disaster/shenyang/`、`official_agricultural_disaster_events.json`、两个灾情 CSV → `SRC-LN-GOV-2026-0717` 等
- `02_raw/weather/openmeteo_hourly_沈北新区_*.json` → `SRC-OM-ERA5-HOURLY`（本研究新采）
- `01_sources/metadata/{weather_stations,crop_calendar,crop_agronomy}.csv` → 元数据快照

---

## 3. 明确的数据缺口（本阶段结论）

| 缺口 | 层级 | 状态 | 说明 |
|---|---|---|---|
| 沈北玉米 2010–2017 面积/产量/单产 | 区级 | 🔴 **not_available** | 沈阳统计年鉴 2016–2018 卷落地页无附件（原项目已核）；沈北区级年鉴本地仅存 2022/2024/2025 卷 |
| 沈北玉米 2025（年鉴口径） | 区级 | ✅ 已由区级年鉴补上 | 2026卷（数据年2025）尚未出版，但《沈北新区国民经济统计资料2025年度》已给出 |
| 沈北 2026-07 **农业受灾/成灾/绝收面积、直接经济损失** | 区级 | 🔴 **not_available** | 官方未按沈北单列公开；仅有省/市口径与街道级定性/人员指标 |
| 2026-07 沈北**逐小时气象站实测**降水 | 站点 | 🔴 **not_available** | 中国气象数据网需实名登录（未绕过）；现仅 ERA5 网格点逐小时（D级） |
| 沈北**玉米物候实测**（2026 播/雄/丝具体日） | 田块 | 🔴 **not_available** | 无区级物候观测；仅有官方适播期区间 + 省级作物日历（旬/月） |
| 沈北 DEM/坡度/沟渠/泵站/土壤类型 | 空间 | 🔴 **not_available** | 本阶段未获取；排水设施仅见文字证据（12台8寸泵等） |
| 沈北 NDVI/EVI/LAI、遥感积水 | 栅格 | 🔴 **not_available** | 未获取；需后续独立采集 |
| 沈北 2026 排涝**面积/设备总量**精确值 | 区级 | 🟡 部分 | 仅个案级（八间房村12台8寸泵、8000余亩） |

---

## 4. 审计结论

1. **已有可支撑“现实世界重建 + 暴雨异常度 + 玉米生产基线 + 物候暴露”四件事的数据**（A/B/D 级混合）。
2. **不足以支撑**“沈北 2026 产量损失估计”与“干预效果量化”——因缺少沈北区级灾损面积、2026 逐小时实测、田块物候、地形/排水设施。
3. 全部进入分析的数据均可通过 `source_id` 回溯；模糊项一律标注 `missing/not_available/reanalysis`，**未做任何插值或编造**。
