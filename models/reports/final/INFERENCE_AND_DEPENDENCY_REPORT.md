# Final Inference Entry · Output Contract · Dependency Audit

## 唯一 Final 生产推理入口（§44/§45）
```
from decision_engine.final.inference import FinalDecisionEngine
eng = FinalDecisionEngine()
out = eng.evaluate({"city":"沈阳","crop":"西红柿","area_mu":60,"budget":300000,
                    "horizon_days":30,"risk_preference":"balanced",
                    "actual_cost_per_mu":20000,"actual_yield_per_mu":4000})   # 可选用户真实输入
ranking = eng.evaluate_many([...])     # 批量 + NO_CLEAR_WINNER / NO_FEASIBLE_PLAN 判定
```
- 前端 / Daily / LLM 只能调用此入口（数值唯一真源）；禁止各自重算。
- 数据来源仅 `models/data/snapshots/final_v1` + `models/reports/final/tables/*`。

## 旧 v1 依赖审计（§6/§60）—— 静态 + 运行时
- 静态（Final 生产范围内 v1 代码读取）：**0**
- 运行时（Final 推理+优化实际访问文件中命中 v1/legacy）：**0**
- **Final production dependency on old v1 = 0** → `pass=True`
- 运行时仅访问：['/Users/morton_cheung/Desktop/比赛/大数据分析/models/data/snapshots/final_v1/model_ready/profit/cost_components.parquet', '/Users/morton_cheung/Desktop/比赛/大数据分析/models/data/snapshots/final_v1/model_ready/profit/crop_cost.parquet', '/Users/morton_cheung/Desktop/比赛/大数据分析/models/data/snapshots/final_v1/model_ready/shenyang_core/market_daily.parquet', '/Users/morton_cheung/Desktop/比赛/大数据分析/models/evaluation/final/price_predictions.parquet', '/Users/morton_cheung/Desktop/比赛/大数据分析/models/reports/final/tables/pareto_frontier.csv', '/Users/morton_cheung/Desktop/比赛/大数据分析/models/reports/final/tables/pareto_summary.csv']
- legacy 文件（train_models/build_*/engine 等）仍读 v1，但**仅用于 v1/v2 旧验收与历史比较**，不在 Final 生产链。

## 生产不变量（§31/§33/§35/§36/§50）—— 9/9 通过
| invariant | pass | detail |
|---|---|---|
| I1_user_input_overrides_source | True | proxy=local_reference user=user_input |
| I1_user_input_weight_1 | True | proxy_rel=None user_rel=1.0 |
| I1_user_input_changes_decision | True | profit_weight=1.0 |
| I2_missing_risk_not_zero | True | hri_avail=True,mr_avail=True;hri_avail=True,mr_avail=True |
| I3_status_enum | True | ['INSUFFICIENT_MARKET_DATA', 'OK', 'SCENARIO_ONLY', 'USER_INPUT_REQUIRED'] |
| I6_contract_fields | True | required=15 |
| I4_no_cross_city_fallback | True | status=INSUFFICIENT_MARKET_DATA price=None |
| I7_horizon_capability | True | h30_scenario_only=False h90_scenario_only=True |
| I5_profit_semantics | True | profit 不可用（符合诚实原则） |


## 城市能力注册表（§48）
| city | tier | price_level | has_price_model | model_horizons | scenario_horizons | n_crops | basis |
|---|---|---|---|---|---|---|---|
| 沈阳 | FULL | wholesale | True | [7, 14, 30] | [60, 90] | 10 | shenyang_core/market_daily.parquet（发改委菜篮子，单一 wholesale，2021-2026 日频） |
| 朝阳 | EXTENDED | market_average | True | [7, 14, 30] | [7, 14, 30, 60, 90] | 10 | chaoyang_extended/market_daily.parquet（发改委全市均价 market_average 单层，密度低于沈阳） |
| 锦州 | LIMITED | mixed_ocr | False | [] | [] | 0 | jinzhou_extended/market_daily.parquet（多 price_level / OCR 转录，口径不单一） |
| 大连 | INSUFFICIENT_MARKET_DATA | nan | False | nan | nan | 0 | nan |
| 铁岭 | INSUFFICIENT_MARKET_DATA | nan | False | nan | nan | 0 | nan |
| 丹东 | INSUFFICIENT_MARKET_DATA | nan | False | nan | nan | 0 | nan |


## 作物能力注册表（§49，节选）
| city | crop | status | available_horizons | scenario_range_availability | hri_availability |
|---|---|---|---|---|---|
| 沈阳 | 土豆 | OK | [7, 14, 30, 60, 90] | scenario_range | True |
| 沈阳 | 西红柿 | OK | [7, 14, 30, 60, 90] | scenario_range | True |
| 沈阳 | 黄瓜 | OK | [7, 14, 30, 60, 90] | scenario_range | True |
| 沈阳 | 韭菜 | OK | [7, 14, 30, 60, 90] | scenario_range | True |
| 沈阳 | 青椒 | OK | [7, 14, 30, 60, 90] | scenario_range | True |
| 沈阳 | 尖椒 | OK | [7, 14, 30, 60, 90] | scenario_range | True |
| 沈阳 | 茄子 | OK | [7, 14, 30, 60, 90] | scenario_range | True |
| 沈阳 | 芹菜 | OK | [7, 14, 30, 60, 90] | scenario_range | True |
| 沈阳 | 芸豆 | OK | [7, 14, 30, 60, 90] | scenario_range | True |
| 沈阳 | 甘蓝 | OK | [7, 14, 30, 60, 90] | scenario_range | True |
| 朝阳 | 土豆 | OK | [7, 14, 30, 60, 90] | scenario_range | True |
| 朝阳 | 西红柿 | OK | [7, 14, 30, 60, 90] | scenario_range | True |

