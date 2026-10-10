# METHOD_LITERATURE_REVIEW.md（R17 方法文献核验 / §八十九）

> 目的：为本轮使用的**方法**提供正式文献依据（**方法学证据**，非 Data Agent 的数据抓取任务）。
> 纪律：**不修改** Data Agent 维护的 `01_sources/DATA_SOURCE_REGISTRY.csv`；新增引用登记在
> `logs/PHASE_4R/REGISTRY_ADDENDUM.csv`（独立文件）。

覆盖 §八十九 列出的 8 个方法主题：

---

## 1. 空间渍涝易感性验证 / presence–background 空间数据
本研究 M2 属 **presence–background**（有“明确受淹”正样本、**无可靠负样本**），与生态学 SDM 的
“presence-only + background”结构同构。
- **Phillips et al. 2009**（*Ecological Applications* 19(1):181–197）——*Sample selection bias and presence-only distribution models: implications for background and pseudo-absence data*。
  → 关键结论：**背景点若与样本采集偏差不一致会导致估计偏误**；应尽量使用“同偏差”背景。**直接支持本研究的做法**：以**全区耕地背景**为对照、而非把未报道区域当作 absence。
- **Li & Guo 2021**（*Ecology and Evolution* 11:10192–10206, DOI 10.1002/ece3.7826）——*Plotting ROC and PR curves from presence and background data*。
  → 明确：**把 background 当 pseudo-absence 会误导评估**。**支持本研究“不给 ROC/AUC”的决定**。
- **Valavi et al. 2022**（*Ecological Monographs* 92(1):e01486, DOI 10.1002/ecm.1486）——presence-only SDM 基准研究（含可复现代码）。
  → 支持：在 presence-only/背景设定下应报告 **排名类指标**与**空间一致性**，而非校准概率。
- Miok et al. 2026（*Diversity and Distributions* 32(5):e70199, DOI 10.1111/ddi.70199）——环境约束下的 pseudo-absence 采样。
  → 支持：**背景采样策略**对结果影响显著，须报告并做敏感性。

**对应本研究**：`M2_EVIDENCE_REGION_VALIDATION.md`（证据区域 vs 背景 + 置换检验）、
`M2_RESOLUTION_SENSITIVITY_REAUDIT.md`（多设定秩相关/重叠）、`M2_STABILITY_MAP.md`。

---

## 2. 空间交叉验证（空间自相关）
- **Roberts et al. 2017**（*Ecography* 40:913–929）——*Cross-validation strategies for data with temporal, spatial, hierarchical or phylogenetic structure*。
- **Valavi et al. 2019**（*Methods in Ecology and Evolution* 10(2):225–232, DOI 10.1111/2041-210X.13107）——`blockCV`。
- Huang et al. 2025（*Ecography* 2025(1):e07354）——CV matters in SDM。

**对应本研究**：§二十二“一个村 500 格 ≠ n=500”、`M2_EVIDENCE_REGION_VALIDATION.md` 中
**以 evidence region 为验证单位**；并在 `M2_VALIDATION.md` 预先声明：**若未来获得 G1 标签，必须用 spatial block CV**。

---

## 3. Waterlogging dose–response（M3 核心）
- **Tian et al. 2021**（*Frontiers in Plant Science* 12:634898, DOI 10.3389/fpls.2021.634898）——*How Does the Waterlogging Regime Affect Crop Yield? A Global Meta-Analysis*。
  → 115 篇 / 2419 组比较；全作物平均 **−32.9%**；并按**积水历时分组**（0–3/3–6/6–9/9–15/15–28 d）给出剂量-响应。
  → **这是 M3-B 层次先验的直接来源**（见 `M3_LITERATURE_EVIDENCE_AUDIT.csv` 新增行 `LIT-TIAN2021META`）。
- Ploschuk et al. 2018（*Front Plant Sci* 9:1863, DOI 10.3389/fpls.2018.01863）——旱作**早/晚生育期**渍涝比较。
  → 支持“**生育期依赖**”与“**恢复能力差异**”，支持 M3 的 **stage × duration** 结构。

## 4. Bayesian meta-analysis / 损失函数方法学
- **Bill-Weilandt et al. 2026**（*NHESS* 26:925–942, DOI 10.5194/nhess-26-925-2026）——*Flood damage functions for rice*。
  → 给出 **Bayesian 回归（水深 × 历时 × 生育期）** 的损失函数范式，并**量化跨区迁移误差**（“模型迁移会引入显著误差”）。
  → **直接支持**本研究 M3 的三点设计原则：① 自变量优先 **depth + duration + stage**；② 必须给**区间**；③ 必须报告**跨区迁移不确定性**（对应 §三十四、§九十一）。

## 5. Counterfactual simulation / SCM
- **Karvanen, Tikka & Vihola 2024**（arXiv:2306.15328）——*Simulating counterfactuals*：在 SCM 下用（粒子滤波式）算法从**反事实分布**抽样，且在证据为连续变量时条件分布难以解析。
  → **直接支持**本研究 §六十七 的 **Common Random Numbers + 逐 draw 完整跑一个 world** 的设计（而非“取均值再取均值”）。
- Lally et al. 2026（arXiv:2608.02893）——*Robust Counterfactual Policy Optimisation via Nondeterministic Causal Models*。
  → 强调**区分“潜在混杂”与“不可约随机性”**，并用**敏感性分析**界定隐含混杂影响 → 支持 §六十五/§九十三的**纪律**：在**未校准**前只允许 definition/graph/interface/skeleton/synthetic。

## 6. Uncertainty propagation
- 上述 Karvanen 2024 与 SIM4Action 类系统的实践共识：复杂系统“what-if”须用 **Monte Carlo ensemble** 产生**结果分布**而非单值。
  → 支持 §六十六/§六十八：**每次 draw 从 M2/M3/M4/weather 分布抽样 → Outcome distribution → median + 50/80/95% 区间**。

## 7. Drainage water balance（M4）
- 本研究采用**简化水量平衡**（§四十六）。文献层面（Bill-Weilandt 2026）一致强调：**单一设施（应急泵）不能解释全部排水**，须区分自然下渗/沟渠/外排。
  → 支持 §四十八“**emergency pumping ≠ 全部排水**”“8000 亩/96h 仅作 weak aggregate constraint”。

## 8. 空间预测模型的“可迁移性”
- Valavi et al. 2022、Huang et al. 2025、Bill-Weilandt 2026 一致指出：**随机切分会高估性能、跨区迁移会显著劣化**。
  → 支持本研究拒绝在**无 G1 标签**时训练监督模型（Route A），并在 Runbook Step 4/9 设置**性能与迁移性门禁**。

---

## 汇总：方法文献对本研究决策的支持对照
| 本研究决策 | 依据文献 |
|---|---|
| 不给 ROC/AUC（无负样本） | Li & Guo 2021；Valavi et al. 2022 |
| 用“背景”而非“伪 absence” | Phillips et al. 2009；Miok et al. 2026 |
| 以 evidence region 为验证单位 | Roberts et al. 2017；Valavi et al. 2019；Huang et al. 2025 |
| M3 用 stage×duration、优先区间 | Tian et al. 2021；Bill-Weilandt et al. 2026；Ploschuk et al. 2018 |
| M3-B 用全球 meta 作弱信息先验 | Tian et al. 2021 |
| 反事实用 CRN + 逐 draw 全跑 | Karvanen et al. 2024；Lally et al. 2026 |
| 未校准前只做 skeleton/synthetic | Lally et al. 2026；§九十三 |
| 应急泵≠全部排水 | Bill-Weilandt et al. 2026 的方法学共识 |

> 全部引用已登记：`logs/PHASE_4R/REGISTRY_ADDENDUM.csv`（8 条，含 DOI/URL 与用途）。
