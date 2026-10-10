# 01 DATA AUDIT — 沈阳农业气象风险研究（Phase 0 数据冻结与审计）

> 生成时间：2026-09-21T15:19:53  
> 数据仓库：`/Users/morton_cheung/Desktop/比赛/大数据分析/liaoning-agri-risk`  
> 分析项目：`/Users/morton_cheung/Desktop/比赛/大数据分析/shenyang`  
> 环境：Python 3.9.6 / pandas 2.3.3 / statsmodels 0.14.6 / lightgbm 4.6.0

本报告由 `src/00_inventory.py`（冻结与来源）与 `src/02_data_qa.py`（质量检查）共同生成。

---

## 0. 数据事实优先级

```text
当前真实 Mart / Curated  >  最新 Metadata  >  Raw  >  最新模板  >  历史报告
```

文档与磁盘冲突时 **以实际数据为准，并记录冲突**（见 §3）。

## 1. 数据快照（data_snapshot.json）

| 输入表 | 行数 | 列数 | 日期范围 | SHA256(前16) |
|---|---|---|---|---|
| fact_price_city | 168,559 | 20 | 2020-01-02 ~ 2026-09-21 | `329cc09c6b28f443` |
| fact_market_supply | 16,550 | 13 | 2020-01-03 ~ 2026-09-21 | `78279f4534f32694` |
| fact_price_weekly | 14,510 | 20 | 2021-01-04 ~ 2026-09-07 | `ba931a6b2bd74055` |
| fact_weather_daily | 14,581 | 13 | 2021-01-01 ~ 2026-09-14 | `4f234d979f7ef2a5` |
| fact_weather_extra_daily | 14,581 | 12 | 2021-01-01 ~ 2026-09-14 | `a614df2a3934c9dc` |
| fact_soil_daily | 14,581 | 9 | 2021-01-01 ~ 2026-09-14 | `7bf273ef5a302383` |
| fact_city_climate_official | 672 | 10 | — | `5cf6f7eb3df50c65` |
| fact_disaster_events | 140 | 24 | 2021-06-10 ~ 2026-08-26 | `b532611370a4ed04` |
| fact_disaster_events_shenyang_2026_official | 6 | 19 | 2026-07-12 ~ 2026-07-15 | `dbbff736b1c1cc2e` |
| fact_disaster_reports | 3 | 7 | — | `ceab63bd0e5fe4db` |
| weekly_disaster_exposure | 1,794 | 10 | 2020-12-28 ~ 2026-09-14 | `bb04975a0a6c136d` |
| fact_production_yearly | 392 | 10 | — | `a7718246053cabfe` |
| fact_production_yearly_2020_2024 | 297 | 16 | — | `38f5e577add3b33b` |
| fact_production_yearly_2025_shenyang | 8 | 16 | — | `3b98d01b15128847` |
| dim_calendar | 2,191 | 11 | 2021-01-01 ~ 2026-12-31 | `b135aee1b853a81a` |
| crops | 34 | 14 | — | `c6b03dd5de9c85ea` |
| cities | 7 | 7 | — | `424dc3e791dae19e` |
| city_static | 7 | 12 | — | `8ee941161f7149d8` |
| crop_calendar | 22 | 18 | — | `bcbce10da1980dac` |
| crop_agronomy | 20 | 12 | — | `3e8859bfecc44ede` |
| source_registry | 30 | 12 | — | `8ee4a99bdc7a1909` |
| weekly_climatology | 371 | 6 | — | `ed4f7c1b88c2af76` |

沈阳 1991–2020 日值气候基线：`baseline_daily_json`，10,958 天，变量 ['et0_fao_evapotranspiration', 'precipitation_sum', 'relative_humidity_2m_mean', 'shortwave_radiation_sum', 'soil_moisture_0_to_10cm_mean', 'temperature_2m_max', 'temperature_2m_mean', 'temperature_2m_min', 'time', 'wind_speed_10m_max']

原始市场价格语料：5,262 个 JSON（批发 1754 / 超市零售 1754 / 集市零售 1754），2020-01-01 ~ 2026-09-21

## 2. 沈阳关键覆盖事实（磁盘实测）

| 事实 | 规模 | 范围 |
|---|---|---|
| 批发成交量记录（仅批发口径有真实 volume） | 16,550 条 / 1655 个交易日 / 10 个品种 | 2020-01-03 ~ 2026-09-21 |
| 城市价格记录（含零售，沈阳） | 143,527 条 | 2020-01-02 ~ 2026-09-21 |
| 气象日值（沈阳，ERA5 再分析） | 2,083 天 | 2021-01-01 ~ 2026-09-14 |
| 土壤日值（沈阳，ERA5-Land） | 2,083 天 | 2021-01-01 ~ 2026-09-14 |
| 扩展气象日值（沈阳） | 2,083 天 | 2021-01-01 ~ 2026-09-14 |
| 派生极端天气事件（沈阳） | 见 §4 | — |
| 官方灾害通报（沈阳，2026） | 6 条 | 2026-07-12 ~ 2026-09-02 |

## 3. 版本冲突与处理（以磁盘事实为准）

| 冲突项 | 文档主张 | 磁盘事实 | 处理 |
|---|---|---|---|
| 天气覆盖结束日 | SHENYANG_DATA_TEMPLATE.md 记价格 2020-01-02~2026-09-21；任务书 §八 期望核心窗口至 2026-09 | 沈阳 ERA5 日值气象实际截止 2026-09-14（再分析数据滞后于实时价格） | 核心研究窗口结束日 = 三源共同覆盖最后一天 = 2026-09-14；不补造 2026-09-15 以后的气象 |
| 成交量单位 | fact_market_supply.unit_raw = 「未标注(推断为吨)」 | 官方接口无 volume 单位字段；推断值仅为备注 | 全研究保留 volume_unit=unknown；禁止任何「吨」表述，仅用相对变化/标准化 |
| 文档滞后性 | 05_reports/FINAL_REPORT.md、AUDIT_REPORT.md、README 含历史结论 | 本轮以 04_marts 实际表体为准重新核对（见下表覆盖事实） | 结论一律来自 04_marts 实体读取，不引用历史报告数字 |

## 4. 极端天气事件（两种来源严格分离）

详见 `outputs/tables/event_catalog.csv`（由 `src/02_data_qa.py` 生成）与 `outputs/tables/event_overlap_flags.csv`。

- `event_source = derived_weather`：ERA5 日值阈值识别，**不是**官方灾情；
- `event_source = official`：沈阳市 / 沈北新区政府门户通报，含空间级别 city/district/township/village；
- 省级 290 万亩受灾口径 `spatial_level = province`，**禁止**摊派到市级。

## 5. 数据仓库未取得（NOT_PUBLIC）与本研究影响

| 缺口 | 状态 | 对研究的影响 |
|---|---|---|
| 沈阳批发成交量单位 | 官方未公开 | volume 仅做相对/标准化分析，报告禁止「吨」 |
| 批发蔬菜产地追踪 | 未公开 | 天气—市场关系不得表述为已证明的本地因果 |
| 市级农业受灾/成灾/绝收面积、直接经济损失 | 未公开 | 报告不得给出市级灾损估算值当作事实 |
| 10 种批发蔬菜分品种年度生产 | 年鉴/公报未单列 | 年度生产层仅到「蔬菜及食用菌」合计 |
| 2026-09-15 以后气象再分析 | 再分析滞后 | 核心窗口截止 2026-09-14 |


---

## 6. 数据字典（本研究实际使用字段）

### 6.1 市场层 `data/interim/shenyang_market_daily.parquet`

| 字段 | 类型 | 单位 | 说明 |
|---|---|---|---|
| `date` | date | — | 市场实际观测日（非完整日历） |
| `crop` | str | — | 10 种核心批发蔬菜，原文名 |
| `price` | float | 元/500g | 批发价（原始单位永久保留） |
| `volume` | float | unknown | 批发日成交量指标；**单位官方未公开** |
| `day_price_ratio` | float | % | 官方接口 dayRriceRatio（日价格环比，原始值） |
| `day_volume_ratio` | float | % | 官方接口 dayVolumeRatio（日成交量环比） |
| `grade` | str | — | 官方等级描述（如「新鲜一级，水黄瓜」） |
| `price_unit_raw` | str | — | 原始单位字符串 |
| `volume_is_zero` | bool | — | 成交量是否为 0（原始层已过滤 0 值，本列用于核验） |

### 6.2 气象 / 土壤层 `data/interim/shenyang_weather_daily.parquet`（完整日序列）

| 字段 | 单位 | 来源 | 说明 |
|---|---|---|---|
| `temp_mean / temp_max / temp_min` | ℃ | ERA5 | 日均/最高/最低气温 |
| `precipitation` | mm | ERA5 | 日累计降水 |
| `humidity` | % | ERA5 | 日均相对湿度 |
| `wind_speed` | km/h | ERA5 | 日最大风速 wind_speed_10m_max |
| `radiation` | MJ/m² | ERA5 | 日累计短波辐射 |
| `et0` | mm | ERA5 | FAO 参考蒸散 |
| `sunshine_duration` | s | ERA5 | 日照时长 |
| `pressure_msl / surface_pressure` | hPa | ERA5 | 海平面/地面气压 |
| `dew_point` | ℃ | ERA5 | 露点 |
| `snowfall / snow_depth` | cm / m | ERA5 | 降雪 / 积雪深度 |
| `cloud_cover` | % | ERA5 | 云量 |
| `vpd` | kPa | ERA5 | 日最大饱和水汽压差 |
| `wind_gust_max` | km/h | ERA5 | 日最大阵风 |
| `soil_moisture_0_7 / _7_28 / _28_100` | m³/m³ | ERA5-Land | 分层土壤含水量（hourly→daily 均值） |
| `soil_temperature` | ℃ | ERA5-Land | 0-7cm 土壤温度 |
| `precip_{1,3,5,7,14}d` | mm | 派生 | calendar day 滚动累计 |
| `hot_days_{3,5,7}d` | 天 | 派生 | 滚动高温日数（≥35℃） |
| `vpd_{3,7}d` | kPa | 派生 | 滚动 VPD 均值 |
| `dry_spell_days / wet_spell_days` | 天 | 派生 | 连续无有效降水 / 连续降雨日数 |
| `temp_anomaly / temp_z` | ℃ / σ | 派生 | 对 1991-2020 同日基线 |
| `precipitation_anomaly / precipitation_pct` | mm / 0-1 | 派生 | 降水距平 / 同期经验分位 |
| `precip_deficit_{14,30}d` | mm | 派生 | 降水亏缺（基线累计 − 实际累计），正=偏干 |

### 6.3 核心面板 `data/interim/shenyang_daily_panel.parquet`

粒度 `date × crop`，仅包含市场实际观测日（2020-01-03 起），天气按 calendar day 对齐。价格/成交量滞后明确区分：

- `price_prev_obs` / `price_calendar_lag_days`：**上一次观测滞后**（并给出间隔日历天数）；
- `precip_*_lagNd` / `temp_*_lagNd`：**日历日滞后**（天气为完整日序列）。

## 7. 日期检查

- 气象日序列 2083 天，断裂 0 处（完整连续）；
- 市场观测日 1655 天，其中落在周末 0 天；
- 无效/无法解析日期 0 条；
- **核心研究窗口（三源共同覆盖）＝ 2021-01-01 ~ 2026-09-14**，面板 14,100 行。

## 8. 重复记录处理

Raw 中存在的重复**全部保留**，仅在 Curated/面板层去重并留档（`outputs/tables/market_duplicate_rows.csv`）。

## 9. 缺失归因（禁止把「没有发布」插成 0）

逐日归因见 `outputs/tables/market_missing_calendar.csv`（2020-01-01 ~ 2026-09-21 全部日历日）。归类优先级：**已发布 > 未发起请求(采集缺口) > 已请求但网站未发布（按日历类型细分）**。

| 类别 | 含义 | 天数 | 占比 |
|---|---|---|---|
| `published(已发布有观测)` | 当日真实发布，有观测值 | 1,655 | 67.4% |
| `collection_gap(采集缺口：未发起请求)` | 采集器未请求该日 → 数据缺口，非「网站未发布」 | 702 | 28.6% |
| `not_published_weekend(已请求·周末未发布)` | 已请求，但平台周末不发布 | 0 | 0.0% |
| `not_published_holiday(已请求·法定节假日未发布)` | 已请求，但法定节假日不发布 | 76 | 3.1% |
| `not_published_workday(已请求·工作日未发布)` | 已请求的工作日仍无发布 | 23 | 0.9% |

> 采集器实际请求 1,754 天（`*_mt1.json` 文件数）；**周末不在请求范围内**（平台周末不发布），故未请求本身不构成数据缺陷。

> **关键结论**：无论是「未请求」还是「网站未发布」，面板中一律保持 **null**，绝不插值、绝不记作 0；成交量字段的缺失与 0 严格区分。

## 10. 数据质量结论

- 价格：批发 10 品种各 1410 天齐备，价格缺失 0；
- 成交量：批发口径全部 >0（无「零成交」污染），但仍保留 `volume_unit=unknown`；
- 气象/土壤：无物理越界值；降水经验分位覆盖率 100.00%；
- 事件：派生 20 起 / 官方 6 条，`event_source` 严格分离；
- 生产：10 种批发蔬菜**无分品种年度生产数据**，年度层仅到「蔬菜及食用菌」合计（见 §5）。
