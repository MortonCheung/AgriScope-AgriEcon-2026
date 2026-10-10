# Decision Engine v2 执行计划（种植方案推荐与优化层）

> 制定日期：2026-10-04
> 定位：在 v1（能评估「用户已想好的方案」）之上，构建 **「自动搜索 → 比较 → 推荐」** 的决策层。
> 架构原则：`Forecast + Risk + Profit + Constraint + Optimization + Ranking`，**不训练黑盒分类器直接输出"推荐西红柿"**。

---

## 一、需求理解（要点复述）

v2 要回答的问题：**现在在沈阳准备种地——种什么？什么时候种？什么时候上市？种多少？哪个收益最好/风险最低/最稳？为什么？如果价格下跌、跟风风险升高怎么办？**

必须交付：

| 阶段 | 能力 | 关键 API |
|---|---|---|
| 1 | 候选方案自动生成（含农事约束） | `generate_candidate_plans()` |
| 2 | 批量评估（复用 v1 `evaluate_plan`，带缓存） | `evaluate_candidates()` |
| 3 | 多目标优化 + Pareto 前沿 | `compute_pareto_frontier()` |
| 4 | 上市窗口优化（含"避免利用预测噪音择时"） | `optimize_harvest_window()` |
| 5 | 面积优化（经营风险约束，非"生物学最优"） | `optimize_area()` |
| 6 | 多作物组合优化（多样性/集中度/相关性/地块占用） | `optimize_crop_portfolio()` |
| 7 | 反事实压力测试 + 鲁棒决策 + Minimax Regret | `simulate_counterfactual()` / `robust_plan_selection()` |
| 8 | 每日动态风险信号与告警（阈值驱动） | `daily_signal()` |
| 9 | 推荐解释器（确定性规则，非 LLM） | 返回 `reasons/tradeoffs/alternatives/comparison_reason` |
| 10 | 历史推荐回测 + 政策基准 + 跟风抑制评估 | `backtest_recommender()` |
| 11 | 推荐置信度、机会成本、盈亏平衡 v2、价格×亩产敏感性 | 见 §38/§47/§48/§49/§50 |
| 12+ | 10 个真实案例 + 1 个失败案例、朝阳/锦州简化推荐、V3 适配器 | 见 §63/§65 |

不可逾越的边界（写死在代码里）：
- 风险偏好只改 utility/ranking，**不改**价格预测、HRI、Market Risk、Climate Exposure；
- 禁止「面积 → 市场供给 → 价格」因果；禁止「组合 → 一定降风险」；禁止「暴雨 → 减产 X%」；
- 亩产/成本若来自 proxy/reference，输出必须标注并降低 confidence；
- 核心理由全部由确定性规则生成。

---

## 二、现状可复用清单（不重做 v1）

已核实可直接复用的 v1 资产：

| 资产 | 位置 | v2 用法 |
|---|---|---|
| `DecisionEngine(as_of=).evaluate_plan()` | `src/decision_engine/engine/engine.py` | 候选方案评估内核（唯一评估入口） |
| `compare_plans()` | 同上 | 组合/多方案比较基础 |
| 价格区间选择与校准结论 | `models/registry/interval_selection.json` | 区间宽度 → 择时显著性阈值 |
| 逐作物最终模型 + WAPE | `evaluation/metrics/model_selection.csv` | 模型误差 → material difference 阈值、推荐置信度 |
| HRI / Market Risk 日频 | `data/features/hri_v1.parquet`、`market_risk_v1.parquet` | 每日信号、风险排序、跟风抑制指标 |
| Climate / Production | `risk/climate.plan_exposure()`、`risk/production.context_for()` | 气候暴露、生产背景 |
| 朝阳/锦州 简化价格与风险 | `data/features/regional_*.parquet`、`regional_risk_*.parquet` | P1/P2 简化推荐 |
| 历史回放口径 | `scripts/run_replay.py`（每 15 天、as_of 截断） | 推荐回测沿用同一严格 point-in-time 规则 |
| 模型注册表 | `models/registry/model_registry.json` | 记录 v2 新增模型/策略 |

---

## 三、侦察发现的三个阻塞点与应对（重要）

### 阻塞 1：P0 蔬菜的农事历覆盖不足
- `district calendar` 实测：`decision_engine_supplement/crop_calendar.csv`（沈阳 47 行）**只有粮食作物**；
- `supplement_v2/crop_calendar_detailed.csv`（238 行，含 `production_system`/`season`）有 **番茄、马铃薯、黄瓜、设施蔬菜(番茄/茄子/辣椒/黄瓜)、设施蔬菜(辣椒/豆角/茄子/黄瓜等)、大白菜**，但**沈阳本地蔬菜条目稀少**（多为大连/铁岭/朝阳/锦州，且精度为月级/单日）；
- 韭菜、芹菜、甘蓝 **完全无日历条目**。

**应对（分层 + 显式标注，不伪造）**：
1. `observed_calendar`：城市×作物精确条目（最高优先，约束强度 strong）；
2. `regional_reference`：同省同作物/设施蔬菜组（跨城市条目，强度 medium）；
3. `inferred_from_price_seasonality`：用该作物 **自身历史价格季节性（past-only）** 推断本地上市高峰月（价格低位窗口），并按公开生育期区间（文档化假设，如 番茄/黄瓜 75–105 天）反推种植窗口，强度 **weak**；
4. `user_window`：用户显式给定 → 覆盖一切。
   → 输出 `planting_date_source`、`constraint_strength`、`calendar_evidence`；weak 约束自动 **降低 confidence**。
   → 硬拒绝规则仅在有强证据时生效（如「露地 × 冬季 × 喜温作物」）。

### 阻塞 2：蔬菜亩产/成本只有 proxy
- 无 `city×crop` 真实蔬菜亩产/成本（v1 审计结论仍成立）；
- 可用的 proxy（必须标注）：
  - `supplement_v3/crop_spatial_structure.csv`：沈阳设施蔬菜及部分作物 `yield_kg_per_mu`（含 `source_level`/`confidence`）；
  - `supplement_v3/crop_cost_components.csv`：番茄/黄瓜 沈阳(东北8市加权, `regional_proxy`)、西红柿/黄瓜/芸豆 铁岭(`neighboring_city`, per_season)、番茄/黄瓜 朝阳北票；
  - `supplement_v2/crop_cost_yearly_extended.csv`：粮食作物为主。

**应对**：`reference_inputs.py` 建立 **provenance 表**（user_input > observed_city > neighboring_city > regional_proxy > inferred），每条记录 `source_level/unit/cost_basis/evidence`；用户显式输入永远优先；proxy 参与推荐时输出标注 + confidence 折扣；**不得**把 proxy 成本写成官方成本。

### 阻塞 3：v1 快照未包含 supplement_v2 / v3
**应对**：新增 `snapshots/v2/` 冻结本阶段用到的 v2/v3 文件（SHA256 + 行数 + 字段），并把 v3 作为 **optional enhancement** 接入（`refresh_external_data()`）：
| V3/V2 数据 | 接入位置 | 说明 |
|---|---|---|
| `crop_cost_components.csv` | Profit / reference_inputs | reference_cost（标注 proxy） |
| `crop_spatial_structure.csv` | reference_inputs / Production context | reference_yield（标注来源） |
| `market_registry_v3.csv`、`market_supply_proxy.csv` | 推荐解释/证据层 | 市场通道背景，**不进入价格预测** |
| `remote_sensing_ndvi/evi_*` | Climate / Production Context | 做简单 ablation；仅当改善解释才保留 |
| `agri_insurance_claims_v3`、`cold_chain_capacity_v3` | Limitations / 背景 | 不进入利润模型 |
| `herding_events_v3`、`herding_events_extended` | HRI 定性验证案例 | 扩充案例库 |

---

## 四、执行计划（12 个阶段，逐步推进）

### Phase 0　基础与快照（0.5 步）
- 新建目录：`optimization/ recommendation/ portfolio/ monitoring/ counterfactual/`、`evaluation/{recommendation,optimization,portfolio}/`；
- `scripts/snapshot_inputs_v2.py`：冻结 v2/v3 输入 → `data/snapshots/v2/` + `manifests/input_manifest_v2.csv`；
- `recommendation/reference_inputs.py`：provenance 表 + `refresh_external_data()`（§54 适配器）。

### Phase 1　农事约束层
- `recommendation/calendar.py`：`build_crop_calendar()`、`derive_planting_window()`、`check_agronomic_feasibility()`；
- 产出 `data/features/crop_calendar_v2.parquet` + `evaluation/recommendation/calendar_coverage.csv`。

### Phase 2　候选生成
- `recommendation/candidates.py`：`generate_candidate_plans(city, available_area_mu, budget, earliest_plant_date, latest_harvest_date, risk_preference, allowed/excluded_crops, cost/yield overrides, area bounds)`；
- 上市窗口离散化（默认 10 天窗 + 月窗；可配 7/14 天）→ 由窗口反推种植窗口；面积阶梯按 §26 自适应步长。

### Phase 3　批量评估 + 缓存
- `recommendation/evaluate_candidates.py`：`evaluate_candidates()`；单例 engine + 结果缓存 key=(city,crop,plant,harvest,area,cost,yield)；
- 输出 `candidate_id ... decision_score/confidence` 全字段表。

### Phase 4　效用 / Pareto / 排序稳定性
- `optimization/utility.py`（三套权重 + 标准化 + 惩罚/奖励）、`optimization/pareto.py`（6 目标 Pareto）、`optimization/ranking.py`（±10% 权重抖动与 bootstrap → `ranking_stability`、`score_separation`）。

### Phase 5　窗口与面积优化
- `optimization/harvest_window.py`：`optimize_harvest_window()` + `material_difference_threshold`（由区间宽度/模型 WAPE 推导）→ 不显著则合并为区间；
- `optimization/area.py`：`optimize_area()`（面积阶梯、worst_case_loss、盈亏平衡 v2：价格/亩产/成本三式、价格×亩产矩阵 + `loss_region_ratio`、损失容忍下建议最大暴露）。

### Phase 6　组合优化
- `portfolio/optimizer.py`：离散搜索/启发式（10 作物规模自实现，若 `pulp`/`ortools` 可用则加速）；
- `portfolio/risk.py`：`portfolio_market_risk/HRI/climate/downside` = 加权平均 + 集中度(HHI)惩罚 + 相关性惩罚；
- 硬约束：预算、面积、地块占用期不冲突（同季组合，不做复种）、max_area_per_crop。

### Phase 7　反事实 / 鲁棒
- `counterfactual/stress.py`：`simulate_counterfactual()`（price ±10/20%、cost +10/20%、yield −10/20%、harvest delay +7/14d、climate↑、market risk↑）→ profit/score/ranking 变化；
- `robust_plan_selection()`：worst_case_profit/score、`scenario_regret`、Minimax Regret 方案。

### Phase 8　每日监测
- `monitoring/daily_signal.py`：`daily_signal(city,crop,as_of_date)` → 分位/动能/HRI/market risk/scenario/confidence + `signal_change_1d/7d` + `risk_level_change`；
- 告警阈值来自历史分布（HRI≥P90→HIGH，≥P95→VERY_HIGH），阈值表落盘。

### Phase 9　推荐器与解释
- `recommendation/recommender.py`：`recommend_plans()`、`explain_recommendation()`、`comparison_reason()`、`opportunity_cost()`、`recommendation_confidence()`、`make_planting_decision()`；
- 模式：`single_crop / multi_crop / compare_both`（默认 compare_both）；Top5 标签允许重复方案；
- 输出 schema 按 §38/§39。

### Phase 10　回测 / 政策基准 / 案例
- `evaluation/recommendation/recommender_backtest.py`：历史 cutoff（复用 v1 节奏）→ 生成→排序→推荐→等真实结果；
- 对比：Top1 / Top3 均值 / 随机 / 当期最高价 / last-value naive / seasonal；指标：realized return、downside、max drawdown、hit rate、regret；
- `policy_benchmark.csv`（Policy A/B/C/D）、`ranking_stability.csv`、`High-HRI Recommendation Rate`（§43/§44）；
- 10 个真实推荐案例 + 1 个失败案例。

### Phase 11　测试 / 图表 / 报告 / 一键
- 14 个测试文件（§59）；9 类图表（§62）；6 份报告（§61）+ 产物 CSV/parquet（§61）；
- `check_acceptance_v2.py`（§67 清单自检）+ `run_all.py --v2` 集成。

---

## 五、验收对照（§67 → 实现位置）

| 验收项 | 实现位置 |
|---|---|
| v1 完整复用 | `recommendation/evaluate_candidates.py` 调 `evaluate_plan` |
| Candidate Plan Generator / 农事约束 | `recommendation/candidates.py` / `calendar.py` |
| Harvest Window / Planting Window / Area Optimizer | `optimization/{harvest_window,area}.py` |
| Multi-Crop Portfolio / Pareto / Risk Preference / Utility | `portfolio/*`、`optimization/*` |
| Counterfactual / Robust / Minimax Regret | `counterfactual/stress.py` |
| Daily Signal / Warning Level | `monitoring/daily_signal.py` |
| Explanation / Opportunity Cost / Break-even v2 / Sensitivity | `recommendation/explainer.py`、`optimization/area.py` |
| Recommendation Confidence / Ranking Stability | `recommendation/recommender.py`、`optimization/ranking.py` |
| Historical Backtest / Policy Benchmark / Herding Suppression | `evaluation/recommendation/*` |
| 10 案例 + 1 失败案例 / 朝阳锦州简化 / V3 Adapter | `evaluation/recommendation/cases.json`、`recommendation/reference_inputs.py` |
| 全部测试 / 报告 / 图表 / `make_planting_decision()` / 一键重建 | `tests/*`、`docs/*`、`scripts/*` |

---

## 七、实施状态（本阶段已完成）

| 阶段 | 状态 | 主要产物 |
|---|---|---|
| Phase 0 快照 + reference 层 | ✅ | `data/snapshots/v2/`（59 文件）、`recommendation/reference_inputs.py`、`refresh_external_data()` |
| Phase 1 农事约束 | ✅ | `recommendation/calendar.py`、`data/features/crop_calendar_v2.parquet`、`calendar_coverage.csv` |
| Phase 2 候选生成 | ✅ | `recommendation/candidates.py`（沈阳示例 164 候选） |
| Phase 3 批量评估+缓存 | ✅ | `recommendation/evaluate_candidates.py`（面积变体缓存，41 次推理覆盖 164 候选） |
| Phase 4 效用/Pareto/稳定性 | ✅ | `optimization/{utility,pareto,ranking}.py`（含数据可靠性折扣） |
| Phase 5 窗口/面积/盈亏平衡 v2 | ✅ | `optimization/harvest_window.py` |
| Phase 6 组合优化 | ✅ | `portfolio/{optimizer,risk}.py`、`evaluation/portfolio/portfolio_backtest.csv` |
| Phase 7 反事实/鲁棒 | ✅ | `counterfactual/stress.py`、`evaluation/optimization/stress_test_results.csv` |
| Phase 8 每日信号/告警 | ✅ | `monitoring/daily_signal.py`、`daily_signal_snapshot.csv`、`warning_thresholds.csv` |
| Phase 9 推荐器/解释/最高层 API | ✅ | `recommendation/recommender.py`、`explainer.py`、`outputs/v2_recommendation.json` |
| Phase 10 回测/政策基准/案例 | ✅ | `evaluation/recommendation/{recommender_backtest.parquet,policy_benchmark.csv,...}` |
| Phase 11 测试/图表/报告/一键 | ✅ | 14 个 v2 测试、9 张图表、6 份报告、`run_all_v2.py`、`check_acceptance_v2.py` |

一键重建：`python3 decision_engine/scripts/run_all_v2.py --full`（或 v1+v2 联合：`run_all.py --with-v2`）。