# V4 六城观测与功能能力 API

`GET /api/observations?city=dandong` 返回城市农业与历史气候；省略 `city` 返回六城研究区摘要。只读 `runtime` 发布资产，没有未来天气、产量、利润预测，也没有全省农业合计。未知或非研究城市返回 `422 UNSUPPORTED_CITY`。

## TypeScript 合同

```ts
export type ResultType = 'VERIFIED_MODEL' | 'OBSERVATIONAL_ANALYSIS'
  | 'DETERMINISTIC_CALCULATION' | 'USER_ASSUMPTION_SCENARIO'
  | 'EXPLORATORY_REFERENCE' | 'NOT_SUPPORTED';

export interface DecisionFeature {
  supported: boolean;
  result_type: ResultType;
  data_sources: string[]; // 路径相对 runtime；不能将路径当 UI 标题
  required_inputs: string[];
  validated_model: boolean;
  limitations: string[];
  horizons: number[];
  crop_ids: string[];
}
export type DecisionFeatures = Record<
  'short_term_price' | 'long_horizon_scenario' | 'production_structure'
  | 'historical_climate' | 'break_even' | 'user_scenario', DecisionFeature>;

export interface ProductionObservation {
  available: boolean;
  period_start: number | null;
  period_end: number | null;
  latest_year: number | null;
  scope: 'eight_agricultural_districts' | 'eight_crop_categories';
  unit: 'ha';
  items: { crop: string; area_ha: number; share: number | null }[];
  source_paths: string[];
  limitations: string[];
}
export interface ClimateYear {
  year: number;
  precipitation_mm: number;
  mean_temp_c: number;
  growing_season_precipitation_mm: number;
  growing_season_mean_temp_c: number;
}
export interface ClimateObservation {
  available: boolean;
  period_start: number | null;
  period_end: number | null;
  complete_year: number | null;
  series: ClimateYear[]; // 升序，2010–2025 完整年；最后一行即最近完整年
  source_paths: string[];
  limitations: string[];
}
export interface CityObservation {
  contract_version: '1';
  scope: 'city';
  city_id: string;
  city_name: string;
  production: ProductionObservation;
  climate: ClimateObservation;
}
export interface ResearchAreaObservation {
  contract_version: '1';
  scope: 'six_city_research_area';
  cities: CityObservation[];
  summary: {
    city_count: number;
    climate_year: number | null;
    precipitation_range_mm: { min: number; max: number } | null;
    mean_temp_range_c: { min: number; max: number } | null;
  };
  limitations: string[];
}
export type ObservationResponse = CityObservation | ResearchAreaObservation;
```

现有 `GET /api/decision/capabilities?city=<slug>`（及 `/api/capabilities` 别名）保留所有旧字段，新增 `features: DecisionFeatures`。旧 `supported`、`crops`、`market_as_of` 仍仅表示 Final 价格推理入口，不表示整座城市是否能经营核算。未登记城市改为 `422 UNSUPPORTED_CITY`；已登记但非六城的城市仍返回旧 unsupported，并且不开放六城工具。

## 实例与单位

丹东 `production.items[0]`：`{crop:'玉米',area_ha:118900,share:0.6522573920675846}`，`latest_year=2022`。原已发布CSV千公顷乘1000换成公顷，share仍为0–1份额。

丹东 `climate.series.at(-1)`：

```json
{
  "year": 2025,
  "precipitation_mm": 1165.0,
  "mean_temp_c": 11.27068493150685,
  "growing_season_precipitation_mm": 990.4,
  "growing_season_mean_temp_c": 20.414754098360657
}
```

无城市摘要：`summary.city_count=6`、`climate_year=2025`、`precipitation_range_mm={min:528.8,max:1165.0}`、`mean_temp_range_c={min:9.687123287671234,max:12.681369863013698}`。范围只在六城共同完整年存在时输出；某城气候资产不可用就返回 null，不以五城冒充六城。

朝阳短期 feature 为 `VERIFIED_MODEL`、supported=true，长期 feature 为 `NOT_SUPPORTED`、supported=false。沈阳长期 supported=true 但类型是 `EXPLORATORY_REFERENCE`、validated_model=false。六城 break_even/user_scenario 均支持，类型分别为确定性公式与用户假设情景，不开放无价格模型城市的旧 evaluate 接口。

## 范围、来源与错误处理

- 五城生产来自 `research/product/<city>/tables/A07_crop_structure.csv`；年份来自已发布 cross-city 年段或本城A07文章。最近年份：朝阳/铁岭/大连2024、锦州2023、丹东2022。份额仅8类已覆盖作物，不能伪装全部农业。
- 沈阳来自 `A07_change_2018_2024.csv`，对同一作物逐区县汇总2024原值，范围8个农业区县。只展示玉米、稻谷、大豆、蔬菜及食用菌、瓜果；不把粮食/谷物/豆类等包含项与子项叠加，share为null。
- 五城气候来自 `A09_climatology.csv`；沈阳无同表，从 `data/model_ready/climate/climate_daily.parquet` 同口径派生，只收录365/366个唯一日值且温度/降水齐全的完整年。ERA5再分析网格，非站点实测。生长季4–9月。
- 当前快照2026年止于09-14，故不进入完整年度series。未来发布若要扩展年段，需先核验完整性再更新合同。
- 数据文件或必要字段缺失时，相应模块available=false、items/series为空、年份为null；不回退别城。其他模块及独立用户经营工具仍可用。
- 没有合并异年生产面积、跨层级市场均价、全省加权气候，也没有推导未来灾害损失。Evidence Drawer可按 `city_id` 指向A07生产与A09气候文章。
- 服务缓存只保存当前已发布资产，发布新资产后重启后端读取；`reset_cache()`用于测试与显式刷新。

经营工具字段名：`area_mu`、`yield_kg_per_mu`、`cost_per_mu`、`assumed_sale_price_per_kg`、`sale_fraction`。它们属于前端独立公式工具输入；该只读API不另行提供利润预测端点。所有输入与结果应显示“基于用户设定条件的情景结果”。
