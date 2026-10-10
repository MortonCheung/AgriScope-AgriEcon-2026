# Final Model Freeze Gate（§73/§74）

**判定：`FINAL_MODEL_FROZEN`**
- 冻结门禁自检（check_acceptance_final）：**38/38**
- pytest：56+ passed · v1 acceptance 32/32 · v2 acceptance 35/35
- 依赖审计：Final production v1 dependency = **0**（静态 0 + 运行时 0）
- 独立复算：**887/887**（max diff 7.1e-15）
- 生产不变量：**9/9**
- 干净复现：`run_final.py` 一句话重建成功（见 `_clean_repro.log`）

## 门禁清单
| check | ok | detail |
|---|---|---|
| Final Data Audit PASS | True | DATA_AUDIT_PASS |
| Data v1 frozen (manifest) | True | 19 |
| no leakage (truncation test) | True | leak=0 |
| price_level clean (single level used) | True | nan |
| baseline complete | True | rows=90 |
| price models retrained | True | horizons=[np.int64(7), np.int64(14), np.int64(30), np.int64(60), np.int64(90)] |
| scenario range calibrated or downgraded | True | scenario_range |
| HRI validated (12w significant) | True | sig=9/10 |
| Market Risk validated | True | nan |
| HRI vs MarketRisk incremental | True | -0.0485592141787771 |
| Climate boundaries documented | True | nan |
| Profit proxy handled (graded) | True | crops=10 |
| Profit Engine 三式+来源分级 | True | crops=10 |
| Decision Score 实际应用 | True | nan |
| §15 折元数据(区间+样本数) | True | nan |
| §54 可复现性元数据 | True | nan |
| §21-23 scenario range 逐crop×horizon | True | nan |
| 极差区间已降级(不掩盖最差) | True | worst_coverage=0.5113122171945701 |
| §24/§25 HRI 时间序列稳健验证 | True | nan |
| §31/§35/§36/§50 生产不变量 | True | 9/9 |
| §6/§60 Final 生产 v1 依赖=0 | True | static=0 runtime=0 |
| §44/§46 唯一推理入口 + Contract 实运行 | True | nan |
| §12-§15 untouched + 默认策略决策 | True | decision=A no_overfit=True |
| §53 时间切分明确 | True | nan |
| Confidence calibrated | True | nan |
| Balanced root cause diagnosed | True | C (HRI 有效，但与预测收益/价格水平高相关 → 旧 score 未有效惩罚) |
| Balanced high-HRI rate reduced vs old | True | old=0.1273006134969325 fix=0.004601226993865031 profit=0.13803680981595093 |
| production Balanced fix effective | True | balanced_before=0.1304347826086956 after=0.0 profit=0.13043478260869565 |
| historical backtest complete | True | strategies=8 |
| ablation complete | True | nan |
| robustness complete | True | nan |
| portfolio rerun | True | nan |
| stress rerun | True | nan |
| counterfactual (minimax regret) rerun | True | nan |
| independent metric recalculation | True | 887/887 |
| Pareto/window/area/portfolio/stress 重跑 | True | §31-§36 |
| robustness 扩展(risk pref/budget/proxy) | True | nan |
| 13 交付物齐备 | True | missing=[] |


## 只能声明「KNOWN_LIMITATIONS」的客观数据限制
- 蔬菜真实成本/亩产缺失 → profit confidence ≈ 13.8（客观数据限制，非代码问题）
- 60/90d 价格退化 → scenario_only（客观数据限制）
- 大连/铁岭/丹东无连续官方价格 → insufficient_market_data（客观数据限制）
- 区间未达 80% 校准 → scenario range（客观限制）
