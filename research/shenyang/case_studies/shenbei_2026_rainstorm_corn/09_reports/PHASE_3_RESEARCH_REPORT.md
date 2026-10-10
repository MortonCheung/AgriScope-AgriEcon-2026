# PHASE_3_RESEARCH_REPORT.md
## 《2026 年沈北新区极端暴雨对玉米生产影响及反事实推演研究》—— 第三阶段研究报告
### M1′ 小样本贝叶斯单产响应模型 + 无灾害反事实资格验证

> 执行纪律：先定义问题 → 冻结数据 → 冻结主变量 → 审计文献 → 定义 prior → Prior Predictive → 拟合 → 采样诊断 →
> Posterior Predictive → Exact LOYO → Prior Sensitivity → 可识别性模拟 → 2026 外推审计 → 反事实资格判断。
> **未颠倒；未先算反事实；未碰前端。** 时间：2026-09-22。

---

## 1. Phase 3 研究问题：为什么从机器学习转向小样本 Bayesian

Phase 2 已用数据证明：`n=8`、核心特征 12、**自由度 = −5**，LOYO 下岭回归 R²=−44（灾难性），只有线性趋势可外推。
→ **纯数据驱动的多特征模型在沈北当前数据结构下不可行**。
因此本轮转向**极简、透明、可检验**的小样本贝叶斯模型：
> 在控制一个极简长期趋势后，抽雄—吐丝期极端降水是否对年度玉米单产提供**额外、稳定、可预测**的信息？
第二个问题（用历史正常暴露替换 2026 暴露会怎样）**只有在第一个问题通过全部验证后才允许回答**。

## 2. Phase 2 约束（本轮不可逾越）
- `n = 8`（2018–2025）；**无 2026 正式单产**；**无区级灾损**；**Waterlogging 为隐变量**。
- 主变量只能 **趋势 + 一个极端降水变量**；禁止加入温度/湿度/Rx1day/Rx5day/R95p/CWD/7d/14d/暴雨日数等（否则回到已被否定的路线）。

## 3. 主天气变量选择
**`primary_exposure = repro_precip_max_5d`（抽雄吐丝期最大连续 5 日累计降水，mm）**；备选 `repro_heavy_rain_days`。
理由（**先按机制与数据质量选定，未看产量结果**）：
- **机制**：渍涝由“连续强降雨”而非单日成灾，连续 5 日累计更能表达强度；`heavy_rain_days` 丢失强度信息。
- **变异**：max_5d 在 2018–2025 有 8 个唯一值（24.6–149.0，SD 41.0）；`heavy_rain_days` 仅 4 个取值（0/1/2/5），离散度不足。
- **共线**：`cor(max_5d, time)=0.18`（无强共线）。
- **2026 表达**：2026=252.8mm（1991–2025 100 分位）。
- **来源可靠性**：两者均为 ERA5 再分析，**对极端降水日的识别一致性仅 0.391**（Phase 2），该误差须随结论引用。
详见 `EXPOSURE_SELECTION.md`；登记于 `MODEL_PREREGISTRATION.md`（**不得因结果不好换变量**）。

## 4. 文献先验审计
- **Class A（可直接数值先验）：无。** 没有文献研究「抽雄—吐丝阶段累计极端降水(mm)→玉米单产」且单位可映射。
- **Class B：无严格可比项。**
- **Class C（机制证据）：4 篇全部属于此**（余卫东2014、刘祖贵2013、刘小飞2021、冯跃华2013）——
  均为「**淹水天数 → 减产%**」，支持“渍涝不利 + 抽雄吐丝敏感”，用于 **M3**，**不作 M1 降雨斜率数值先验**。
→ 结论（规格 §13）：**当前文献不足以构造直接的 rainfall→yield 信息性先验**；M1′ 使用 skeptical/weakly-informative prior，**不伪造文献先验**。

## 5. 模型结构
```
log(Y_t) = α + β_T · Z(T_t) + β_R · Z(R_t) + ε_t ,   ε_t ~ Normal(0, σ)
M0（Baseline）: log(Y_t) = α + β_T · Z(T_t) + ε_t
```
- `log` 尺度：保证正产量、系数≈比例变化、反事实差异易转百分比。
- 标准化：全样本模型用 2018–2025 均值/标准差；**LOYO 每折只用该折训练年份**（防泄漏）。

## 6. Prior 设计（S0/S1/S2）
| Prior | 含义 | β_R | 其它 |
|---|---|---|---|
| **S0** Skeptical | 看数据前不假设降雨必有大影响 | `N(0, 0.07)` | α N(8.987,0.25)；β_T N(0,0.15)；logσ N(−2.526,0.45) |
| **S1** Direction-implied (weakly-informed) | **仅**机制方向的轻微负向（非可映射数值文献先验） | `N(−0.05, 0.13)` | 同上 |
| **S2** Discounted/Wider | 削弱 S1 的信息 | `N(−0.025, 0.15)` | α N(.,0.26)；β_T N(0,0.16)；logσ N(.,0.45) |

- **`β_R` 不硬截断为负**（允许 P(β_R≥0)>0）：降雨≠渍涝，适度降雨可能有益。
- 先验修改全部登记于 `priors/PRIOR_CHANGELOG.md`（v0.1→v0.2→v0.3）。

## 7. Prior Predictive
见 `diagnostics/PRIOR_PREDICTIVE_CHECK.md`、`prior_predictive.png`。
- 训练设计下三组先验的 2.5–97.5% 预测单产均落在农业合理区间，越界比例 S0 1.00% / S1 0.95% / S2 1.11% → **通过**。
- 极端暴露情景（ZR≈+4.25）下区间显著变宽、出现物理不可能量级 → **不是先验缺陷，而是“线性模型外推到 4.25 SD”的固有后果**，直接指示 2026 强外推。

## 8. 模型拟合与采样诊断
| 指标 | 值 | 判据 |
|---|---|---|
| 最大 R-hat | **1.0067** | ≤1.01 ✅ |
| 最小 bulk ESS | **573** | 合理 ✅ |
| 接受率 | M0=0.280 / S0=0.277 / S1=0.261 / S2=0.307 | ~0.234 附近 ✅ |
| divergence | 无（本采样器为 RWM，以 R-hat/ESS/接受率为收敛证据） | ✅ |

→ **Gate A：PASS**。（详见 `diagnostics/SAMPLER_DIAGNOSTICS.md`）

## 9. Posterior 结果（S0 主设定）
| 参数 | median | 95% CrI |
|---|---|---|
| α | 8.986 | [8.923, 9.048] |
| β_T | 0.107 | [0.035, 0.174] |
| **β_R** | **−0.0216** | **[−0.0739, 0.0379]** |
| log σ | −2.497 | [−2.964, −1.939] |

- **趋势 β_T 明显为正**（CrI 排除 0）——与“技术/管理驱动单产上升”一致。
- **β_R 后验为轻微负向，但 95% CrI 含 0**：`P(β_R<0)=0.775`（S1=0.816，S2=0.791）。
  ▶ 正确表述：**“在给定模型/数据/先验下，降雨响应系数低于 0 的后验概率约 0.78”**，
  **不是**“有 78% 概率暴雨导致减产”。

## 10. Prior → Posterior 更新
见 `diagnostics/prior_posterior_update.csv`、`PRIOR_DOMINANCE_AUDIT.md`。
- `β_R` 的 `posterior_sd/prior_sd`：S0 **0.435**、S1 **0.258**、S2 **0.219** → 均 `<0.5` ⇒ **DATA_INFORMATIVE**。
- 且三组先验的 β_R 后验几乎相同（median −0.022/−0.027/−0.024）⇒ **后验主要由数据决定，而非先验主导**。
  （说明：**先验不主导 ≠ 数据识别能力强** —— 见 §13。）

## 11. LOYO 验证（主要验证结果）
见 `validation/LOYO_predictions.csv`、`LOYO_metrics.csv`、`LOYO_COMPARISON.md`。

| 模型 | MAE (kg/ha) | RMSE | mean logPD | cov50 | cov80 | cov95 | 最差年 |
|---|---|---|---|---|---|---|---|
| **M0（趋势）** | **697.1** | **749.3** | **0.918** | 12.5% | 25.0% | 62.5% | 2025 |
| M1_S0 | 707.7 | 776.5 | 0.836 | 25.0% | 37.5% | 62.5% | 2025 |
| M1_S1 | 717.0 | 799.3 | 0.814 | 25.0% | 37.5% | 75.0% | 2025 |
| M1_S2 | 734.3 | 809.2 | 0.798 | 25.0% | 37.5% | 75.0% | 2025 |

> **M1 相比 M0：ΔMAE=+10.6、ΔRMSE=+27.2、ΔlogPD=−0.082 —— 加入极端降雨后，未见年份预测不仅没有改善，反而变差。**
> **Gate C：FAIL。** 共同最差年份为 **2025**；各模型 95% 区间覆盖率仅 62.5–75%（区间偏窄/模型失配）。

## 12. Prior 敏感性
见 `sensitivity/prior_sensitivity_summary.csv`、`PRIOR_SENSITIVITY.md`。
- β_R median 跨先验极差仅 **0.0058**；P(β_R<0) 区间 **[0.78, 0.82]**；**方向反转 = 否**。
- ⇒ **不是“换先验就反转”的那类 prior-sensitive**；三组先验一致给出“轻微负向、与 0 不可区分”。
- `Gate D：PASS`。
- ⚠️ 表中 `Y_A/Y_B/dY/rel` 仅为**模型算式**（如 S0 下 dY 中位 836 kg/ha、rel 8.66%，95% CrI [−17.2%, +26.7%]），
  **不构成反事实结论**，本阶段不据此发布 B 世界数字。

## 13. 小样本可识别性模拟（n=8 究竟能学到什么）
见 `validation/identifiability_simulation.md`。

| 真实 β_R | 95%CrI 排除 0 的识别率 | CrI 覆盖真值 | 平均 P(β_R<0) |
|---|---|---|---|
| 0（零假设） | 0.05 | 0.95 | 0.468 |
| −0.03（轻度） | **0.11** | 0.965 | 0.742 |
| −0.06（中度） | **0.34** | 0.955 | 0.899 |
| −0.10（较强） | 0.75 | 0.920 | 0.973 |

> **结论：零假设下假阳性 5%（校准良好）；但即使真实存在“中度”负效应（β=−0.06），n=8 也只有 34% 的概率识别出来。**
> 本地数据**几乎没有独立识别能力**，只能提供有限更新 —— 这直接决定了反事实结果的表达等级。

## 14. 2026 支持域审计
见 `validation/EXTRAPOLATION_AUDIT.md`。
- 训练 2018–2025 暴露范围 **24.6–149.0 mm**（中位 73.3）；**2026 = 252.8 mm**（1991–2025 **100 分位**，P99=201.9）。
- 标准化后 **ZR_2026 = +4.25 SD** ⇒ **`STRONG_EXTRAPOLATION`**。
- ⇒ `Gate E：STRONG_EXTRAPOLATION`（对反事实 → 最高只能标 `EXPLORATORY_EXTRAPOLATION`）。

## 15. 反事实资格判断（Gate A–F）
见 `06_models/M1_bayesian_yield_response/COUNTERFACTUAL_ELIGIBILITY.md`。

| Gate | 检查 | 结果 |
|---|---|---|
| A 收敛 | R-hat 1.0067、ESS≥573 | **PASS** |
| B 后验预测 | 观测被 95% 区间覆盖 = 1.00 | **PASS** |
| C LOYO | M1 全面劣于 M0 | **FAIL** |
| D 先验敏感性 | 无方向反转 | **PASS** |
| E 2026 外推 | ZR=+4.25 SD | **STRONG_EXTRAPOLATION** |
| F 机制 | 变量=降雨暴露，非 waterlogging | **CAUTION** |

**总判定：`NOT_ELIGIBLE`**（对应规格 §76 的**情况 C**）。

## 16. B 世界（无灾害世界）
**未生成。** 依据规格 §48/§59/§76：Gate C 失败且 Gate E 为强外推 → M1′ **不具备反事实资格**，
按纪律**不产出任何 B 世界定量数字**，改建 `07_counterfactual/B_no_disaster/NOT_ELIGIBLE.md`。
> 这是 Phase 3 的**有效完成**，而非失败：它回答了“在当前数据条件下我们究竟能知道多少”。

**关于“无灾害世界”的定义（备查，即使本轮不计算）**：
“无灾害”**不是“不下雨”**，而是在**其他条件一致**下，把 2026 的**异常极端降雨暴露**替换为**历史正常水平**。
- Primary baseline `NORMAL_P50` = **80.7 mm**（1991–2025 同一物候阶段 primary exposure 中位数）；
- Baseline 敏感性备选：**2011–2025 P50 = 86.7 mm**；**非极端年份(≤P90) P50 = 75.1 mm**。
（本轮因 Gate C FAIL，未据此计算任何 B 世界数字。）

## 17. 研究结论（严格分级）
- **数据事实（Level A）**：2026-07-13 前后沈北发生历史级极端降雨，且玉米处于抽雄—吐丝期；2018–2025 沈北玉米单产呈显著上升趋势（β_T CrI 排除 0）。
- **模型结果（Level B）**：在 M1′ 下，抽雄吐丝期极端降水响应系数 `β_R` 后验中位数约 **−0.02**（每 1 SD 降水），
  95% CrI **含 0**，P(β_R<0)≈**0.78**；**但该变量未通过 LOYO 增量检验**（M1 不优于趋势模型 M0）。
- **情景推演（Level C）**：**本轮不发布。** 仅在模型算式层面记录（见 §12），并明确标记 `NOT_ELIGIBLE / EXPLORATORY_EXTRAPOLATION`。

## 18. 局限（诚实清单）
1. **n=8**，可识别性模拟显示中度效应识别率仅 0.34；
2. 暴露为**ERA5 再分析**，极端日识别一致性 0.391；
3. 主变量是**降雨暴露**，**不能代表 waterlogging**（机制缺口）；
4. **2026 强外推**（+4.25 SD）；
5. 无对照区县、无 2026 单产、无区级灾损；
6. 物候为 **GDD 模型估计**（非田块实测）；
7. 采样器为**自实现 RWM**（环境无 PyMC），已提供 R-hat/ESS/接受率诊断，但非 HMC。
8. LOYO 区间覆盖率偏低（62.5–75%），说明模型**区间校准不足**。

## 19. Phase 4 建议
**不要**继续在 n=8 上堆模型。应并行推进：
1. **扩样本**：沈北历史序列（线下年鉴/信息公开）+ **对照区县面板**（同饮沈阳年鉴分区县表）；
2. **Unlock Track**（见 `09_reports/PHASE3_PARALLEL_UNLOCK_TRACK.md`）：DEM/水系/沟渠/泵站 + 区级灾损 + 农险理赔，
   以解锁 **M2（降雨→渍涝）** 与 **M3（渍涝→损伤）**；
3. **站点实测降水**替换再分析；
4. 若扩样成功，重估 **GAM / Synthetic Control / BSTS**；否则走 **partial identification / scenario bounds**（宽区间情景界）。

---

## §75 必答 20 问

1. **M1 最终选了哪个极端降雨指标？** `repro_precip_max_5d`（抽雄吐丝期最大 5 日累计降水）。
2. **为什么不是另一个？** 机制上“连续强降雨→渍涝”更贴合；8 年变异充足（8 个唯一值 vs 4）；与时间趋势无强共线；能表达 2026 极端程度；**且不按拟合优度选择**。
3. **该指标 2018–2025 有多少变化？** 24.6–149.0 mm（均值 78.6，SD 41.0）。
4. **2026 的值是多少？** **252.8 mm**。
5. **2026 是否超出训练范围？** **是**，超出训练上限 149.0，ZR=+4.25 SD ⇒ **强外推**。
6. **哪些文献真正用于数值 prior？** **没有**（无 Class A）。
7. **哪些只能作机制证据？** 4 篇论文全部（余卫东2014、刘祖贵2013、刘小飞2021、冯跃华2013）→ 用于 M3。
8. **S0、S1、S2 分别是什么？** S0 以 0 为中心的 skeptical；S1 仅机制方向的弱信息负向（**非数值文献先验**）；S2 削弱 S1。
9. **Prior Predictive 是否合理？** 训练设计下通过（越界 ≤1.1%）；极端情景出现荒谬量级（源于外推，非先验缺陷）。
10. **MCMC 是否收敛？** 是：最大 R-hat 1.0067、最小 bulk ESS 573、接受率 0.26–0.31。
11. **β_R 的 posterior 是什么？** median ≈ −0.02（S0 −0.0216；S1 −0.0274；S2 −0.0235）。
12. **P(β_R<0)？** S0 **0.775**、S1 **0.816**、S2 **0.791**。
13. **posterior 相比 prior 更新多少？** β_R 的 sd 比 = 0.435/0.258/0.219（均 <0.5）⇒ **DATA_INFORMATIVE**，且后验跨先验一致。
14. **M1 的 LOYO 是否优于 M0？** **否**，全面劣化（ΔMAE +10.6、ΔRMSE +27.2、ΔlogPD −0.082）。
15. **哪些年份预测最差？** **2025**（各模型共同最差年）。
16. **结果是否对 prior 敏感？** 方向上**不敏感**（三先验一致）；但数值不确定性大（CrI 含 0）。
17. **n=8 的模拟识别能力？** 零假设假阳性 5%；轻度效应识别率 11%、中度 34%、较强 75%。
18. **M1 是否达到 LEVEL 3？** **否**。虽可收敛、可预测，但 **LOYO 未通过增量检验 + 强外推** ⇒ 仍为 **LEVEL 1–2**（见 `MODEL_READINESS_PHASE3.md`）。
19. **B 世界是否有资格计算？** **无资格**（`NOT_ELIGIBLE`）。
20. **Phase 4 下一步？** 扩样本（含对照区县）+ Unlock Track（DEM/水系/排水/区级灾损）+ 站点实测；不达条件则走 partial identification。

---

## 本轮产物
```
06_models/M1_bayesian_yield_response/
  M1_INPUT_AUDIT.md, EXPOSURE_SELECTION.md, MODEL_PREREGISTRATION.md,
  MODEL_SPECIFICATION.md, MODEL_ENVIRONMENT.md, M1_DATA_VERSION.md,
  MODEL_CARD_M1.md, COUNTERFACTUAL_ELIGIBILITY.md
  data/   M1_dataset_frozen.csv, M1_DATA_DICTIONARY.md, EXPOSURE_AUDIT.csv, M1_UPSTREAM_FINGERPRINTS.csv
  priors/ PRIOR_EVIDENCE_AUDIT.csv, PRIOR_EVIDENCE_AUDIT_SUMMARY.md, PRIOR_CHANGELOG.md
  fits/   M0_posterior.npz, M1_S0_posterior.npz, M1_S1_posterior.npz, M1_S2_posterior.npz, posterior_summary.csv
  diagnostics/ prior_predictive.{png,csv,md}, sampler_diagnostics.csv, SAMPLER_DIAGNOSTICS.md,
               posterior_predictive.png, POSTERIOR_PREDICTIVE_CHECK.md, prior_posterior_update.csv,
               PRIOR_DOMINANCE_AUDIT.md
  validation/ LOYO_predictions.csv, LOYO_metrics.csv, LOYO_COMPARISON.md,
              EXTRAPOLATION_AUDIT.md, identifiability_simulation.csv, IDENTIFIABILITY_SIMULATION.md
  sensitivity/ prior_sensitivity_summary.csv, PRIOR_SENSITIVITY.md
  figures/ F1..F7 png + FIGURES_README.md
07_counterfactual/B_no_disaster/NOT_ELIGIBLE.md
09_reports/{PHASE_3_RESEARCH_REPORT.md, PHASE3_PARALLEL_UNLOCK_TRACK.md, DATA_REQUEST_DRAFT.md}
scripts/{m1_lib, m1_priors, 70..78}_p3*.py
```

## 一句话结论
> **Phase 3 完成了完整的 Bayesian workflow：模型收敛、后验预测通过、先验不主导；但加入极端降雨后跨年预测未改善（Gate C FAIL），且 2026 暴露强外推（+4.25 SD），
> 加之 n=8 对中度效应的识别率仅 0.34 —— 因此 M1′ 不具备 B 世界反事实资格，本轮按纪律不产出无灾害世界数字。**
> 这回答的是本项目最核心的问题：**在当前真实数据条件下，我们究竟能知道多少。**
