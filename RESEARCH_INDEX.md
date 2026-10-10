# 研究总索引（RESEARCH_INDEX）

> 本索引用于让读者（含 ChatGPT 研究审查）**直接定位**每项研究的报告、结果、指标、程序、输入数据与来源登记。

> 路径均为本仓库内相对路径。

> **复现状态图例**：`依赖齐备·未复算` = 数据链路与程序文件齐备，但本工作区**未执行重训/重算**，因此不得标注“已复现”。

---

## 0. 快速定位

| 需求 | 入口 |
|---|---|
| 六城 54 专题报告 | `research/<city>/A0x/report.md` |
| 跨城市综合 | `research/cross_city/report.md`、`research/cross_city/synthesis/report.md` |
| 沈阳 v1 历史专题 | `research/shenyang/v1_reports/` |
| 沈北暴雨玉米案例 | `research/shenyang/case_studies/shenbei_2026_rainstorm_corn/09_reports/` |
| 正式模型报告 | `models/reports/final/` |
| 模型指标表 | `models/reports/final/tables/` |
| 模型注册表 | `models/registry/` |
| 研究/建模程序 | `pipelines/research/`、`pipelines/modeling/`、`pipelines/data_foundation/` |
| 模型输入数据 | `data/model_ready/` |
| 派生研究数据 | `data/processed/` |
| 数据治理与来源 | `data/metadata/`、`data/source_registry/` |
| Parquet 结构 | `data/SCHEMA/PARQUET_SCHEMA.md` |
| 项目总报告 | `docs/RC3_FINAL_REPORT.md`、`docs/PROJECT_STATUS.md`、`docs/RESEARCH_ASSET_USAGE_REPORT.md` |

---

## 1. 六城 × A01–A09 专题研究（54 项）

### 1.1 沈阳市（`research/shenyang/`）

| 编号 | 主题 | 正式研究报告 | 结果表 | 统计指标 | 图 | 计算程序 |
|---|---|---|---|---|---|---|
| A01 | 沈阳市主要蔬菜批发市场的时间结构与季节性特征 | `research/shenyang/A01/report.md` | `A01/tables/` (5) | `A01/metrics/` (—) | `A01/figures/` (1) | `pipelines/research/modules/a01_market_time.py` |
| A02 | 气象条件与沈阳市主要蔬菜批发市场日度响应 | `research/shenyang/A02/report.md` | `A02/tables/` (2) | `A02/metrics/` (—) | `A02/figures/` (—) | `pipelines/research/modules/a02_weather_market.py` |
| A03 | 气象影响的滞后累积与非线性特征 | `research/shenyang/A03/report.md` | `A03/tables/` (3) | `A03/metrics/` (—) | `A03/figures/` (—) | `pipelines/research/modules/a03_lag_accumulation.py` |
| A04 | 极端天气事件下沈阳市蔬菜批发市场响应及 2026 年强降雨案例 | `research/shenyang/A04/report.md` | `A04/tables/` (3) | `A04/metrics/` (1) | `A04/figures/` (—) | `pipelines/research/modules/a04_extreme_events.py` |
| A05 | 沈阳市不同蔬菜的气象响应差异与市场恢复特征 | `research/shenyang/A05/report.md` | `A05/tables/` (3) | `A05/metrics/` (—) | `A05/figures/` (—) | `pipelines/research/modules/a05_crop_heterogeneity.py` |
| A06 | 沈阳市蔬菜市场量价关系风险传导与天气信息预测增量 | `research/shenyang/A06/report.md` | `A06/tables/` (3) | `A06/metrics/` (2) | `A06/figures/` (—) | `pipelines/research/modules/a06_predictability.py` |
| A07 | 沈阳市农业生产的区县格局与作物结构（2018-2024） | `research/shenyang/A07/report.md` | `A07/tables/` (3) | `A07/metrics/` (—) | `A07/figures/` (1) | `pipelines/research/modules/a07_production_structure.py` |
| A08 | 气象条件与沈阳市农业单产变化的区县面板研究 | `research/shenyang/A08/report.md` | `A08/tables/` (3) | `A08/metrics/` (1) | `A08/figures/` (—) | `pipelines/research/modules/a08_robustness.py` |
| A09 | 沈阳市农业气象风险、生产响应与农产品市场表现综合研究 | `research/shenyang/A09/report.md` | `A09/tables/` (—) | `A09/metrics/` (—) | `A09/figures/` (—) | `pipelines/research/modules/a09_city_special.py` |

**沈阳市 公共登记**

- 结构化文章：`research/shenyang/A0x/article.json`
- 同行评审（如有）：`research/shenyang/A0x/review.md`
- 计算程序目录：`pipelines/research/modules/`（A01–A09 模块 + `cross_city.py`），运行入口 `pipelines/research/run_research.py`，配置 `pipelines/research/config/`
- 输入数据：`data/model_ready/`（城市扩展表）+ `data/processed/`（市场/生产/气象/成本聚合）
- 原始来源登记：`research/shenyang/sources/source_registry.csv`、`research/shenyang/city_meta/manifest.json`
- 证据登记：`research/shenyang/evidence/claim_evidence.csv`
- 已知限制：见该城 `report.md` 内“边界/局限”小节与 `research/shenyang/city_meta/manifest.json`；跨城价格层级不可直接比较
- 复现状态：`依赖齐备·未复算（NOT RE-RUN）`

### 1.2 朝阳市（`research/chaoyang/`）

| 编号 | 主题 | 正式研究报告 | 结果表 | 统计指标 | 图 | 计算程序 |
|---|---|---|---|---|---|---|
| A01 | 朝阳市主要农产品价格的时间结构与季节性特征 | `research/chaoyang/A01/report.md` | `A01/tables/` (5) | `A01/metrics/` (1) | `A01/figures/` (1) | `pipelines/research/modules/a01_market_time.py` |
| A02 | 朝阳市气象条件与主要农产品市场响应 | `research/chaoyang/A02/report.md` | `A02/tables/` (2) | `A02/metrics/` (1) | `A02/figures/` (1) | `pipelines/research/modules/a02_weather_market.py` |
| A03 | 朝阳市气象影响的滞后、累积与非线性特征 | `research/chaoyang/A03/report.md` | `A03/tables/` (3) | `A03/metrics/` (1) | `A03/figures/` (1) | `pipelines/research/modules/a03_lag_accumulation.py` |
| A04 | 朝阳市极端天气事件前后市场变化 | `research/chaoyang/A04/report.md` | `A04/tables/` (3) | `A04/metrics/` (1) | `A04/figures/` (1) | `pipelines/research/modules/a04_extreme_events.py` |
| A05 | 朝阳市作物响应差异与市场恢复特征 | `research/chaoyang/A05/report.md` | `A05/tables/` (3) | `A05/metrics/` (1) | `A05/figures/` (1) | `pipelines/research/modules/a05_crop_heterogeneity.py` |
| A06 | 朝阳市市场可预测性与天气信息预测增量 | `research/chaoyang/A06/report.md` | `A06/tables/` (1) | `A06/metrics/` (1) | `A06/figures/` (1) | `pipelines/research/modules/a06_predictability.py` |
| A07 | 朝阳市农业生产结构与变化 | `research/chaoyang/A07/report.md` | `A07/tables/` (5) | `A07/metrics/` (1) | `A07/figures/` (1) | `pipelines/research/modules/a07_production_structure.py` |
| A08 | 朝阳市稳健性与可信度检验 | `research/chaoyang/A08/report.md` | `A08/tables/` (3) | `A08/metrics/` (1) | `A08/figures/` (1) | `pipelines/research/modules/a08_robustness.py` |
| A09 | 朝阳市城市特色专项研究 | `research/chaoyang/A09/report.md` | `A09/tables/` (2) | `A09/metrics/` (1) | `A09/figures/` (1) | `pipelines/research/modules/a09_city_special.py` |

**朝阳市 公共登记**

- 结构化文章：`research/chaoyang/A0x/article.json`
- 同行评审（如有）：`research/chaoyang/A0x/review.md`
- 计算程序目录：`pipelines/research/modules/`（A01–A09 模块 + `cross_city.py`），运行入口 `pipelines/research/run_research.py`，配置 `pipelines/research/config/`
- 输入数据：`data/model_ready/`（城市扩展表）+ `data/processed/`（市场/生产/气象/成本聚合）
- 原始来源登记：`research/chaoyang/sources/source_registry.csv`、`research/chaoyang/city_meta/manifest.json`
- 证据登记：`research/chaoyang/evidence/claim_evidence.csv`
- 已知限制：见该城 `report.md` 内“边界/局限”小节与 `research/chaoyang/city_meta/manifest.json`；跨城价格层级不可直接比较
- 复现状态：`依赖齐备·未复算（NOT RE-RUN）`

### 1.3 锦州市（`research/jinzhou/`）

| 编号 | 主题 | 正式研究报告 | 结果表 | 统计指标 | 图 | 计算程序 |
|---|---|---|---|---|---|---|
| A01 | 锦州市主要农产品价格的时间结构与季节性特征 | `research/jinzhou/A01/report.md` | `A01/tables/` (5) | `A01/metrics/` (1) | `A01/figures/` (1) | `pipelines/research/modules/a01_market_time.py` |
| A02 | 锦州市气象条件与主要农产品市场响应 | `research/jinzhou/A02/report.md` | `A02/tables/` (2) | `A02/metrics/` (1) | `A02/figures/` (1) | `pipelines/research/modules/a02_weather_market.py` |
| A03 | 锦州市气象影响的滞后、累积与非线性特征 | `research/jinzhou/A03/report.md` | `A03/tables/` (3) | `A03/metrics/` (1) | `A03/figures/` (1) | `pipelines/research/modules/a03_lag_accumulation.py` |
| A04 | 锦州市极端天气事件前后市场变化 | `research/jinzhou/A04/report.md` | `A04/tables/` (3) | `A04/metrics/` (1) | `A04/figures/` (1) | `pipelines/research/modules/a04_extreme_events.py` |
| A05 | 锦州市作物响应差异与市场恢复特征 | `research/jinzhou/A05/report.md` | `A05/tables/` (3) | `A05/metrics/` (1) | `A05/figures/` (1) | `pipelines/research/modules/a05_crop_heterogeneity.py` |
| A06 | 锦州市市场可预测性与天气信息预测增量 | `research/jinzhou/A06/report.md` | `A06/tables/` (1) | `A06/metrics/` (1) | `A06/figures/` (1) | `pipelines/research/modules/a06_predictability.py` |
| A07 | 锦州市农业生产结构与变化 | `research/jinzhou/A07/report.md` | `A07/tables/` (5) | `A07/metrics/` (1) | `A07/figures/` (1) | `pipelines/research/modules/a07_production_structure.py` |
| A08 | 锦州市稳健性与可信度检验 | `research/jinzhou/A08/report.md` | `A08/tables/` (3) | `A08/metrics/` (1) | `A08/figures/` (1) | `pipelines/research/modules/a08_robustness.py` |
| A09 | 锦州市城市特色专项研究 | `research/jinzhou/A09/report.md` | `A09/tables/` (2) | `A09/metrics/` (1) | `A09/figures/` (1) | `pipelines/research/modules/a09_city_special.py` |

**锦州市 公共登记**

- 结构化文章：`research/jinzhou/A0x/article.json`
- 同行评审（如有）：`research/jinzhou/A0x/review.md`
- 计算程序目录：`pipelines/research/modules/`（A01–A09 模块 + `cross_city.py`），运行入口 `pipelines/research/run_research.py`，配置 `pipelines/research/config/`
- 输入数据：`data/model_ready/`（城市扩展表）+ `data/processed/`（市场/生产/气象/成本聚合）
- 原始来源登记：`research/jinzhou/sources/source_registry.csv`、`research/jinzhou/city_meta/manifest.json`
- 证据登记：`research/jinzhou/evidence/claim_evidence.csv`
- 已知限制：见该城 `report.md` 内“边界/局限”小节与 `research/jinzhou/city_meta/manifest.json`；跨城价格层级不可直接比较
- 复现状态：`依赖齐备·未复算（NOT RE-RUN）`

### 1.4 大连市（`research/dalian/`）

| 编号 | 主题 | 正式研究报告 | 结果表 | 统计指标 | 图 | 计算程序 |
|---|---|---|---|---|---|---|
| A01 | 大连市主要农产品价格的时间结构与季节性特征 | `research/dalian/A01/report.md` | `A01/tables/` (5) | `A01/metrics/` (1) | `A01/figures/` (1) | `pipelines/research/modules/a01_market_time.py` |
| A02 | 大连市气象条件与主要农产品市场响应 | `research/dalian/A02/report.md` | `A02/tables/` (2) | `A02/metrics/` (1) | `A02/figures/` (1) | `pipelines/research/modules/a02_weather_market.py` |
| A03 | 大连市气象影响的滞后、累积与非线性特征 | `research/dalian/A03/report.md` | `A03/tables/` (3) | `A03/metrics/` (1) | `A03/figures/` (1) | `pipelines/research/modules/a03_lag_accumulation.py` |
| A04 | 大连市极端天气事件前后市场变化 | `research/dalian/A04/report.md` | `A04/tables/` (2) | `A04/metrics/` (1) | `A04/figures/` (1) | `pipelines/research/modules/a04_extreme_events.py` |
| A05 | 大连市作物响应差异与市场恢复特征 | `research/dalian/A05/report.md` | `A05/tables/` (3) | `A05/metrics/` (1) | `A05/figures/` (1) | `pipelines/research/modules/a05_crop_heterogeneity.py` |
| A06 | 大连市市场可预测性与天气信息预测增量 | `research/dalian/A06/report.md` | `A06/tables/` (1) | `A06/metrics/` (1) | `A06/figures/` (1) | `pipelines/research/modules/a06_predictability.py` |
| A07 | 大连市农业生产结构与变化 | `research/dalian/A07/report.md` | `A07/tables/` (5) | `A07/metrics/` (1) | `A07/figures/` (1) | `pipelines/research/modules/a07_production_structure.py` |
| A08 | 大连市稳健性与可信度检验 | `research/dalian/A08/report.md` | `A08/tables/` (3) | `A08/metrics/` (1) | `A08/figures/` (1) | `pipelines/research/modules/a08_robustness.py` |
| A09 | 大连市城市特色专项研究 | `research/dalian/A09/report.md` | `A09/tables/` (2) | `A09/metrics/` (1) | `A09/figures/` (1) | `pipelines/research/modules/a09_city_special.py` |

**大连市 公共登记**

- 结构化文章：`research/dalian/A0x/article.json`
- 同行评审（如有）：`research/dalian/A0x/review.md`
- 计算程序目录：`pipelines/research/modules/`（A01–A09 模块 + `cross_city.py`），运行入口 `pipelines/research/run_research.py`，配置 `pipelines/research/config/`
- 输入数据：`data/model_ready/`（城市扩展表）+ `data/processed/`（市场/生产/气象/成本聚合）
- 原始来源登记：`research/dalian/sources/source_registry.csv`、`research/dalian/city_meta/manifest.json`
- 证据登记：`research/dalian/evidence/claim_evidence.csv`
- 已知限制：见该城 `report.md` 内“边界/局限”小节与 `research/dalian/city_meta/manifest.json`；跨城价格层级不可直接比较
- 复现状态：`依赖齐备·未复算（NOT RE-RUN）`

### 1.5 丹东市（`research/dandong/`）

| 编号 | 主题 | 正式研究报告 | 结果表 | 统计指标 | 图 | 计算程序 |
|---|---|---|---|---|---|---|
| A01 | 丹东市主要农产品价格的时间结构与季节性特征 | `research/dandong/A01/report.md` | `A01/tables/` (—) | `A01/metrics/` (1) | `A01/figures/` (—) | `pipelines/research/modules/a01_market_time.py` |
| A02 | 气象条件与主要农产品市场响应 | `research/dandong/A02/report.md` | `A02/tables/` (—) | `A02/metrics/` (1) | `A02/figures/` (—) | `pipelines/research/modules/a02_weather_market.py` |
| A03 | 气象影响的滞后、累积与非线性特征 | `research/dandong/A03/report.md` | `A03/tables/` (—) | `A03/metrics/` (1) | `A03/figures/` (—) | `pipelines/research/modules/a03_lag_accumulation.py` |
| A04 | 极端天气事件前后市场变化 | `research/dandong/A04/report.md` | `A04/tables/` (—) | `A04/metrics/` (1) | `A04/figures/` (—) | `pipelines/research/modules/a04_extreme_events.py` |
| A05 | 作物响应差异与市场恢复特征 | `research/dandong/A05/report.md` | `A05/tables/` (—) | `A05/metrics/` (1) | `A05/figures/` (—) | `pipelines/research/modules/a05_crop_heterogeneity.py` |
| A06 | 市场可预测性与天气信息预测增量 | `research/dandong/A06/report.md` | `A06/tables/` (—) | `A06/metrics/` (1) | `A06/figures/` (—) | `pipelines/research/modules/a06_predictability.py` |
| A07 | 丹东市农业生产结构与变化 | `research/dandong/A07/report.md` | `A07/tables/` (5) | `A07/metrics/` (1) | `A07/figures/` (1) | `pipelines/research/modules/a07_production_structure.py` |
| A08 | 稳健性与可信度检验 | `research/dandong/A08/report.md` | `A08/tables/` (—) | `A08/metrics/` (1) | `A08/figures/` (—) | `pipelines/research/modules/a08_robustness.py` |
| A09 | 丹东市城市特色专项研究 | `research/dandong/A09/report.md` | `A09/tables/` (2) | `A09/metrics/` (1) | `A09/figures/` (1) | `pipelines/research/modules/a09_city_special.py` |

**丹东市 公共登记**

- 结构化文章：`research/dandong/A0x/article.json`
- 同行评审（如有）：`research/dandong/A0x/review.md`
- 计算程序目录：`pipelines/research/modules/`（A01–A09 模块 + `cross_city.py`），运行入口 `pipelines/research/run_research.py`，配置 `pipelines/research/config/`
- 输入数据：`data/model_ready/`（城市扩展表）+ `data/processed/`（市场/生产/气象/成本聚合）
- 原始来源登记：`research/dandong/sources/source_registry.csv`、`research/dandong/city_meta/manifest.json`
- 证据登记：`research/dandong/evidence/claim_evidence.csv`
- 已知限制：见该城 `report.md` 内“边界/局限”小节与 `research/dandong/city_meta/manifest.json`；跨城价格层级不可直接比较
- 复现状态：`依赖齐备·未复算（NOT RE-RUN）`

### 1.6 铁岭市（`research/tieling/`）

| 编号 | 主题 | 正式研究报告 | 结果表 | 统计指标 | 图 | 计算程序 |
|---|---|---|---|---|---|---|
| A01 | 铁岭市主要农产品价格的时间结构与季节性特征 | `research/tieling/A01/report.md` | `A01/tables/` (—) | `A01/metrics/` (1) | `A01/figures/` (—) | `pipelines/research/modules/a01_market_time.py` |
| A02 | 气象条件与主要农产品市场响应 | `research/tieling/A02/report.md` | `A02/tables/` (—) | `A02/metrics/` (1) | `A02/figures/` (—) | `pipelines/research/modules/a02_weather_market.py` |
| A03 | 气象影响的滞后、累积与非线性特征 | `research/tieling/A03/report.md` | `A03/tables/` (—) | `A03/metrics/` (1) | `A03/figures/` (—) | `pipelines/research/modules/a03_lag_accumulation.py` |
| A04 | 极端天气事件前后市场变化 | `research/tieling/A04/report.md` | `A04/tables/` (—) | `A04/metrics/` (1) | `A04/figures/` (—) | `pipelines/research/modules/a04_extreme_events.py` |
| A05 | 作物响应差异与市场恢复特征 | `research/tieling/A05/report.md` | `A05/tables/` (—) | `A05/metrics/` (1) | `A05/figures/` (—) | `pipelines/research/modules/a05_crop_heterogeneity.py` |
| A06 | 市场可预测性与天气信息预测增量 | `research/tieling/A06/report.md` | `A06/tables/` (—) | `A06/metrics/` (1) | `A06/figures/` (—) | `pipelines/research/modules/a06_predictability.py` |
| A07 | 铁岭市农业生产结构与变化 | `research/tieling/A07/report.md` | `A07/tables/` (5) | `A07/metrics/` (1) | `A07/figures/` (1) | `pipelines/research/modules/a07_production_structure.py` |
| A08 | 稳健性与可信度检验 | `research/tieling/A08/report.md` | `A08/tables/` (—) | `A08/metrics/` (1) | `A08/figures/` (—) | `pipelines/research/modules/a08_robustness.py` |
| A09 | 铁岭市城市特色专项研究 | `research/tieling/A09/report.md` | `A09/tables/` (1) | `A09/metrics/` (1) | `A09/figures/` (1) | `pipelines/research/modules/a09_city_special.py` |

**铁岭市 公共登记**

- 结构化文章：`research/tieling/A0x/article.json`
- 同行评审（如有）：`research/tieling/A0x/review.md`
- 计算程序目录：`pipelines/research/modules/`（A01–A09 模块 + `cross_city.py`），运行入口 `pipelines/research/run_research.py`，配置 `pipelines/research/config/`
- 输入数据：`data/model_ready/`（城市扩展表）+ `data/processed/`（市场/生产/气象/成本聚合）
- 原始来源登记：`research/tieling/sources/source_registry.csv`、`research/tieling/city_meta/manifest.json`
- 证据登记：`research/tieling/evidence/claim_evidence.csv`
- 已知限制：见该城 `report.md` 内“边界/局限”小节与 `research/tieling/city_meta/manifest.json`；跨城价格层级不可直接比较
- 复现状态：`依赖齐备·未复算（NOT RE-RUN）`

---

## 2. 跨城市综合研究

- 主报告：`research/cross_city/report.md`；结果表：`research/cross_city/tables/`（4 表）；指标：`research/cross_city/metrics/cross_city_summary.json`；图：`research/cross_city/figures/cross_city_overview.png`
- 综合稿：`research/cross_city/synthesis/report.md` + `synthesis/tables/`（4 表）+ `synthesis/article.json`
- 研究计划：`research/cross_city/plan/FIVE_CITY_RESEARCH_PLAN.md`
- 计算程序：`pipelines/research/modules/cross_city.py`
- 复现状态：`依赖齐备·未复算（NOT RE-RUN）`

## 3. 沈阳市 v1 历史专题与 QA

- v1 专题报告：`research/shenyang/v1_reports/`（01_DATA_AUDIT … 17_DISTRICT_DATA_SUPPLEMENT，另含 `MILESTONE_1_REPORT.md`、`LIMITATIONS.md`、`BLOCKERS.md`、`DECISION_LOG.md`）
- QA/审计：`research/shenyang/qa/`（`FINAL_QA_REPORT.md`、`V1_AUDIT.md`、`V1_V2_COMPARISON.md`）
- 计算脚本：`research/shenyang/scripts/`（00–60 全链路脚本）、`research/shenyang/run_all.py`、`run_district.py`
- 来源与证据：`research/shenyang/sources/`、`research/shenyang/evidence/`、`research/shenyang/references.md`
- 复现状态：`依赖齐备·未复算（NOT RE-RUN）`；`v1` 与 `v2` 口径差异见 `V1_V2_COMPARISON.md`

## 4. 沈北 2026 暴雨玉米案例研究

- 目录：`research/shenyang/case_studies/shenbei_2026_rainstorm_corn/`
- 阶段报告：`09_reports/`（PHASE_1/2/3/4、PHASE_4R、FULL_DATA_ACQUISITION_REPORT、DATA_REQUEST_DRAFT）
- 模型：`06_models/`（M1 贝叶斯产量响应、M2 渍涝空间、M3/M4 预构建与状态方程、反事实引擎）
- 分析结果：`05_analysis/`（含 `M2_stability_map`、并行研究排名与集成得分表）
- 数据整理层：`03_clean/`、`04_marts/`（结果表）；**原始件 `01_sources/`、`02_raw/` 未上传**
- 图件：`08_figures/`
- 复现状态：`依赖齐备·部分未复算`（原始遥感/空间件未上传，栅格派生步骤不可在本仓库重跑）

## 5. 正式模型研究（`models/`）

报告与清单：

- `models/reports/final/ABLATION_REPORT.md`
- `models/reports/final/BACKTEST_REPORT.md`
- `models/reports/final/FAILED_EXPERIMENTS.md`
- `models/reports/final/FINAL_ANSWERS.md`
- `models/reports/final/FINAL_DATA_AUDIT.md`
- `models/reports/final/FINAL_METRICS.csv`
- `models/reports/final/FINAL_MODEL_FREEZE_GATE.md`
- `models/reports/final/FINAL_MODEL_OUTPUT_SCHEMA.json`
- `models/reports/final/FINAL_MODEL_REGISTRY.csv`
- `models/reports/final/FINAL_MODEL_REPORT.md`
- `models/reports/final/FINAL_RUN_META.json`
- `models/reports/final/FREEZE_CHECKLIST.csv`
- `models/reports/final/HRI_VALIDATION_REPORT.md`
- `models/reports/final/INFERENCE_AND_DEPENDENCY_REPORT.md`
- `models/reports/final/OPTIMIZATION_REPORT.md`
- `models/reports/final/POLICY_AND_UNTOUCHED_REPORT.md`
- `models/reports/final/PRICE_MODEL_REPORT.md`
- `models/reports/final/PROFIT_REPORT.md`
- `models/reports/final/RECOMMENDATION_REPORT.md`
- `models/reports/final/RISK_MODEL_REPORT.md`
- `models/reports/final/ROBUSTNESS_REPORT.md`

- 指标表目录：`models/reports/final/tables/`（59 个文件，含 HRI/价格/风险/优化/组合/情景/稳健性/消融等指标）
- 模型注册表：`models/registry/model_registry.json`、`tuned_params.json`、`interval_selection.json`、`LONG_HORIZON_V2_REGISTRY.csv`
- 计算程序：`pipelines/modeling/`（`src/decision_engine/**` + `scripts/**` + `tests/**`）
- 模型清单/血缘：`data/metadata/model_manifests/`（含 `final/` 冻结清单与独立重算对照）
- 关键限制：见 `models/reports/final/FINAL_ANSWERS.md`（跨城不可比、成本/亩产缺口、区间仅情景范围、HRI 与价格共线、60/90 天误差大）
- 复现状态：`依赖齐备·未复算（NOT RE-RUN）`；负面结果保留于 `FAILED_EXPERIMENTS.md`、`ABLATION_REPORT.md`

---

## 6. 计算程序（`pipelines/` 与 `code/`）

| 目录 | 内容 | 文件数 |
|---|---|---:|
| `pipelines/research/` | A01–A09 研究模块 + 库 + 配置 + 运行入口 | 25 |
| `pipelines/modeling/` | 决策引擎源码（final/risk/optimization/portfolio/recommendation/models）+ 脚本 + 测试 | 117 |
| `pipelines/data_foundation/` | 采集/解析/标准化/治理/校验程序与依赖说明 | 173 |
| `pipelines/daily/` | 日度链路（配置/特征/归一化/快照/验收） | 14 |
| `pipelines/long_horizon/` | 长期预测研究（含报告与指标，排除权重二进制） | 58 |
| `pipelines/publishing/` | 研究/运行时发布程序 | 2 |
| `code/llm/` | LLM 评测、上下文与提示、报告（含真实评测报告） | 31 |
| `code/scripts/` `code/tests/` `code/agriscope_env.py` | 验收/校验脚本与测试 | 16 |

> 依赖说明：`pipelines/data_foundation/requirements.txt`、`pipelines/daily/requirements.txt`、`research/shenyang/requirements.txt`。
> **已排除**：浏览器日志（`.playwright-cli`）、`__pycache__`、运行日志、编译产物。

## 7. 研究数据（`data/`）

| 目录 | 内容 | 文件数 |
|---|---|---:|
| `data/model_ready/` | 正式模型输入：`features/`、`climate/`、`hri/`、`profit/`、`recommendation/`、`shenyang_core/`、`*_extended/` + `FEATURE_SOURCE_MAP.csv` | 41 |
| `data/processed/` | 清洗/标准化/集成数据：market/production/cost/climate/demand/disaster/policy/dimensions/integrated/decision_dataset 等 | 93 |
| `data/metadata/governance/` | 治理：CANONICAL_TABLE_REGISTRY、SOURCE_REGISTRY、UNIT_REGISTRY、DO_NOT_USE_FOR_MODEL、DATA_LINEAGE 等 | 15 |
| `data/metadata/evidence/` | 证据索引：raw_source_index、YEARBOOK_ALL_TABLES、bulletin_parse_index 等 | 6 |
| `data/metadata/quality/` | 质量：MISSINGNESS、OUTLIERS、COVERAGE_CUBE、QC_REPORT、TIME_COVERAGE 等 | 10 |
| `data/metadata/model_manifests/` | 模型清单与冻结/独立重算对照（含 `final/`） | 22 |
| `data/metadata/inventory/` | 库存：ALL_FILES、ALL_TABLES、FILE_SHA256、DUPLICATE_*、MIGRATION_STATUS 等 | 13 |
| `data/metadata/requirements/` | 数据需求/缺口矩阵 | 5 |
| `data/source_registry/` | 原始来源登记（`metadata/` 城市/市场/来源登记 CSV）+ 各原始目录说明 | 23 |
| `data/SCHEMA/` | `PARQUET_SCHEMA.md` + `parquet_schemas.json`（自动生成，不改原始数据） | 2 |

**Parquet 直读**：117 个 parquet 文件的结构（字段/类型/行数）见 [`data/SCHEMA/PARQUET_SCHEMA.md`](data/SCHEMA/PARQUET_SCHEMA.md)。
单位对照 `data/metadata/governance/UNIT_REGISTRY.csv`；来源对照 `data/source_registry/metadata/source_registry.csv`。

**数据分发限制**：`data/model_ready/`、`data/processed/` 为派生数据，原始受限来源未上传，仅供本次研究内部使用，不得再分发。详见 [`DATA_DISTRIBUTION_LIMITATIONS.md`](DATA_DISTRIBUTION_LIMITATIONS.md)。

## 8. 项目文档（`docs/`）

- `docs/API.md`
- `docs/ARCHITECTURE.md`
- `docs/FRONTEND_V3_PHASE2_REPORT.md`
- `docs/FRONTEND_V3_STRESS_AND_A11Y_REPORT.md`
- `docs/HYBRID_V2_REPORT.md`
- `docs/LLM_ABLATION_V2_REPORT.md`
- `docs/LLM_REAL_EVALUATION_REPORT.md`
- `docs/PROJECT_STATUS.md`
- `docs/RC2_EXECUTION_PLAN.md`
- `docs/RC3_DEPLOYMENT_REPORT.md`
- `docs/RC3_FINAL_REPORT.md`
- `docs/RC3_TEST_REPORT.md`
- `docs/README.md`
- `docs/RESEARCH_ASSET_USAGE_REPORT.md`
- `docs/RUNTIME_ASSETS.md`
- `docs/models/`（15 文件）
- `docs/v4/`（11 文件）

## 9. 审计（`audit/`）

- `audit/EXCLUDED_FILES.csv`
- `audit/GITHUB_UPLOAD_CANDIDATES.csv`
- `audit/MIGRATION_REPORT.md`
- `audit/MISSING_DEPENDENCIES.csv`
- `audit/RESEARCH_ASSET_MATRIX.csv`
- `audit/SHA256_MANIFEST.csv`
- `audit/SOURCE_PATHS.csv`
- `audit/UPLOAD_MANIFEST.csv`

---

## 10. 全局复现状态与诚信声明

- 本索引中所有研究的复现状态均为 **`依赖齐备·未复算（NOT RE-RUN）`**（案例研究为部分未复算）。
- 本工作区**未执行任何数据抓取、模型训练或程序重构**；不得将任何报告标注为“已复现”。
- 源项目内部**已推翻/降级的结论**（如区间 80% 覆盖不足、Balanced“更强抑制跟风”不成立）必须如实保留，见 `models/reports/final/FINAL_ANSWERS.md`。
- 负面结论与失败实验一律保留：`models/reports/final/FAILED_EXPERIMENTS.md`、`ABLATION_REPORT.md`。
