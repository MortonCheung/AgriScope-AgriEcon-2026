# SKILLS_SELECTION — Writing Skills 筛选与采用说明

- 日期：2026-10-10
- Skills 目录：`/Users/morton_cheung/Desktop/比赛/大数据分析/reference/writing-skills`
- 覆盖范围：该目录下 10 个仓库、`SKILLS_INDEX.md` 索引条目 **1 514** 条
- 本轮实际阅读：**14 份 SKILL.md 全文**（含各自 `references/` 配套材料），并按索引关键词筛查中文写作/润色/审稿类条目 60 余条
- 用途界定：**这些 Skill 仅作为写作方法参考，不作为本文的数据来源或学术文献**；未执行其中任何脚本，未修改系统环境
- 原则：**不采用任何以"降低 AI 检测率"为目标的技巧**；只采用以真实论证、准确表达、审慎结论为核心的方法

---

## 一、采用清单（7 项，其中 3 项为主用）

### 1. paper-polish　★主用

- **路径**：`Supervisor-Skills/skills/paper-polish/SKILL.md`（及 `references/ai-tone-guardrails.md`、`academic-phrasebank.md`、`section-conventions.md`）
- **核心方法**：
  1. **忠实原意压倒一切**：纯语言修改可自由做；可能触及含义的修改必须标注请作者确认；绝不把"相关"改成"因果"、绝不悄悄删掉限定语（如"在本数据上"）。
  2. **不编造**：不新增数据、公式、结果、引文、方法名；缺失处留括注而非补写。
  3. **保守默认**：小改优于大改，不改优于小改；作者原本已做限定的表述不得"改强"。
  4. **分节惯例**：引言负责定位、方法负责可复现、结果负责陈述、讨论负责解释与限定、摘要是一篇微缩论文——**各节语域不同，不套用同一腔调**。
  5. **校准（claim strength ≤ evidence）**：强动词（show/demonstrate）只用于确凿证据，中（suggest/indicate），弱（may reflect/appears to）；过度声称词表（含中文：卓越、首次、唯一、最高、完美、颠覆性、最优）须软化或标注。
  6. **公平对待前人工作**：不做稻草人，用"精确差异"代替"前人都不行"。
  7. **去 AI 腔**：宏大概括、浅层 -ing 尾巴、营销形容词、高频 AI 词、强制三段式、格式噪音；**并警告"剥净信号后文字会干净但无生气"，解决之道是句子长短交错、用精确事实而非堆砌形容词承载分量、直白陈述真实权衡与局限**。
- **为何适用于本文**：本文正处在"已定稿、待精修"阶段，与 paper-polish 的适用前提完全一致；且其"校准"与"忠实原意"两条正好服务于本任务的核心约束——**不得通过文字修饰掩盖严格前向验证的不利结果**。
- **用于哪些章节**：全文，尤其摘要、绪论、第四/七/八/九章、结论
- **不适用/需改造**：其中"中译英"部分不适用（本文为中文）；`-ing 尾巴`等英文特征需转译为中文对应形态（"从而……""进而……"的尾缀式假深度）
- **采用**：✅

### 2. pre-submission-reviewer　★主用

- **路径**：`Supervisor-Skills/skills/pre-submission-reviewer/SKILL.md`
- **核心方法**：五维结构化审稿 + 严重度分级（CRITICAL / MAJOR / MINOR）+ 禁用词全文扫描（`innovative / pioneering / revolutionary / superior / surpass / excel / remarkable / unprecedented / breakthrough` 等 30 余词，同一词出现 ≥3 次升为 MAJOR）+ **claim 强度 ≤ 证据**（明确指出 "solves" 通常应降为 "improves"）+ 每条 finding 必须引用具体文本并且给具体修法。
- **为何适用于本文**：本文已进入投稿前阶段，需要的正是"审稿式预检"而非再创作；其"每条 finding 必须锚定原文"的要求，可保证语言修改不脱离论文实际证据。
- **用于哪些章节**：全文五维审查，重点第二章数据、第四章方法、第七章结果
- **不适用/需改造**：其**英文语法维度**（冠词、which/that）与 **LaTeX 格式维度**不适用；其"范式匹配"中的 STEM 阈值（baseline/ablation 要求）需按"大数据应用类"竞赛标准调整
- **采用**：✅（采用其严重度分级、禁用词扫描、claim-证据对齐；不采用英文语法与 LaTeX 维度）

### 3. humanizer（41-sticerd 版）　★主用

- **路径**：`Auto-Empirical-Research-Skills/skills/41-sticerd-eee-sewage-econometrics-check/skills/humanizer/SKILL.md`
- **核心方法**：**24 种模式 / 4 类**的可操作清单——结构性（三段并列、公式化过渡词、回声式结论、段落长度一致、每段同一结构、正文中 First/Second/Third）、词汇性（delve、landscape、crucial/pivotal、multifaceted、underscores、navigate）、修辞性（过度对冲、表演式热情、虚假平衡、空洞承认、过早综合、普遍共识断言）、格式性（过度路标、过度对仗、定义式开篇、免责声明堆叠、先摘要后内容、冒号加编号列表）。并有"**学术经济学适配**"条款：保留确需的形式结构、保留术语与引文密度、句子长短交错、**允许不完美**（真实写作有轻微不对称与个人痕迹）、尊重本领域惯用表达（"我们估计/我们发现/第(3)列显示"是惯用语，不是 AI 痕迹）、不改动公式与引用标记。
- **为何适用于本文**：这是**唯一带有"学术经济学适配"的、以清单形式给出可逐条核对的反模式表**，可直接映射为中文论文的反模式表；其"允许不完美""保留术语"两条可防止精修时把论文改成另一种套路。
- **用于哪些章节**：全文语言层；结构性模式重点查第七、八、九章
- **不适用/需改造**：其英文词汇项（delve/landscape）无中文对应，须逐一映射为中文同源现象（如"赋能/颠覆/深度赋能""值得注意的是""综上所述"）；其 `#11 underscores`、`#12 navigate` 等对中文论文需改判
- **采用**：✅（采用模式分类框架；词项按中文学术论文重写）

### 4. review-paper-light（21-claesbackman 版）

- **路径**：`Auto-Empirical-Research-Skills/skills/21-claesbackman-AI-research-feedback/Skills/review-paper-light/SKILL.md`
- **核心方法**：聚焦"**贡献—识别—过度声称**"的快速审稿；其中 Agent B 的 6 类检查尤其有用：①**无因果识别的因果语言**（causes/leads to/drives/determines/because of/results in）；②**把机制陈述为事实**；③**超出样本的泛化**；④**缺失注意事项**（选择、反向因果、测量误差、遗漏变量）；⑤**统计显著与经济显著混用**；⑥**未验证的优先权断言**（"首次""无人研究"）。
- **为何适用于本文**：本文最容易犯的正是①③⑤——把统计关联写成因果、把沈阳结论泛化、把市场机会收益与经济收益混同。
- **用于哪些章节**：绪论、第五、七、九章、结论
- **不适用/需改造**：其流程依赖 `.tex` 与子代理并行；本文为 Markdown 中文稿，只取其检查清单
- **采用**：✅（仅采用 6 类检查清单）

### 5. paper-audit（35-bahayonghang）

- **路径**：`Auto-Empirical-Research-Skills/skills/35-bahayonghang-academic-writing-skills/skills/paper-audit/SKILL.md`
- **核心方法**：**支持中英文**的深度审计，16 项问题分类，其中与本任务高度相关的有：数值不一致、**夸大/主张不准确**、误导性歧义、**内部矛盾**、**伪创新/稻草人**、**段落级论证不连贯**、方法不全。并强调"始终区分脚本发现与人工判断""findings 必须锚定引文与精确位置"。
- **为何适用于本文**：其"数值不一致 + 夸大主张 + 内部矛盾"三类正是本任务第三阶段要查的核心。
- **用于哪些章节**：全文一致性检查
- **不适用/需改造**：其脚本流水线（`uv run`、多代理委员会、`final_issues.json`）与评分公式不采用（会引入未审查的脚本执行）
- **采用**：✅（仅采用其问题分类清单，不执行脚本）

### 6. literature-review（36-taoyunudt）

- **路径**：`Auto-Empirical-Research-Skills/skills/36-taoyunudt-literature-review-skill/SKILL.md`
- **核心方法**：**面向中文**；"**五要素**"（趋势模式 / 研究主题 / 争议矛盾 / 关键核心论文 / 空白不足）+ 正文段落模板（**主题句 → 文献支持 → 综合分析 → 批判评价 → 过渡**）+ 明确反对"简单罗列文献"，要求"围绕主题而非文献组织段落"。
- **为何适用于本文**：本文绪论第二节现有"四类文献"写法接近罗列；该方法可用于把"分类罗列"改写为"围绕问题组织"。
- **用于哪些章节**：第一章第二节（文献基础与研究缺口）
- **不适用/需改造**：其检索与文献管理工具部分不采用（本文参考文献已定，**不新增任何文献**，仅在既有 12 条范围内重组论证）
- **采用**：✅（仅采用组织方法与段落模板，**不新增参考文献**）

### 7. intro-drafter（Supervisor-Skills）

- **路径**：`Supervisor-Skills/skills/intro-drafter/SKILL.md`
- **核心方法**：引言六段逻辑（背景动机 → 现有工作局限 → 问题与目标 → 关键挑战 → 方案概览 → 贡献），其中两条纪律对本文有用：**"贡献必须映射到具体章节"**（"做了大量实验"不算贡献）；**"不编造百分比或加速比"**。
- **为何适用于本文**：可用来检查本文绪论的"研究贡献四条"是否与正文章节一一对应。
- **用于哪些章节**：第一章
- **不适用/需改造**：其六段脚手架是英文技术论文范式，直接套用会显得生硬；**只借用其"贡献-章节对应"与"不编造数字"两条**，不照搬六段结构
- **采用**：✅（部分采用）

---

## 二、评估后不采用的 Skills（记录理由）

| Skill | 路径 | 不采用的理由 |
|---|---|---|
| humanize-chinese | `Auto-Empirical-Research-Skills/skills/49-voidborne-d-humanize-chinese/` | **其目标为"知网/维普/万方 AIGC 检测降重"，以规避机器检测为核心指标（含 perplexity、GLTR 等检测导向统计量）。本任务明令禁止把降低 AI 检测率作为目标**，故整体不采用 |
| writing-anti-ai | `.../33-Galaxy-Dawn-claude-scholar/skills/writing-anti-ai/` | 同上，以"remove AI-generated traces"为目标 |
| sewn-deslop / stop-slop | `.../45-stephenturner-skill-deslop/`、`.../46-hardikpandya-stop-slop/` | 与已采用的 humanizer（41 版）功能重叠，且为英文导向；择一即可，避免反复套用不同清单造成风格摇摆 |
| humanizer_academic（44） | `.../44-matsuikentaro1-humanizer_academic/` | 面向**医学论文**、基于 Wikipedia "Signs of AI writing"，与农业经济建模语境不符 |
| ssci-polish（70） | `.../70-ssci-polish/` | 面向**英文 SSCI 期刊**润色，且以 python-docx 改写 DOCX；本文为中文投稿，不适用 |
| scientific-writing（完整流程） | `scientific-agent-skills/skills/scientific-writing/` | 其报告指南体系（CONSORT/PRISMA/STROBE…）、证据编号与 Python 脚本流水线面向英文医学/科学手稿，**与本竞赛论文格式不兼容**；仅采纳其"保留不确定性、不显著≠等价、禁止编造"三条原则（已并入 paper-polish 的校准规则） |
| peer-review（完整流程） | `scientific-agent-skills/skills/peer-review/` | 其合规前置（授权表、利益冲突、保密渠道）与脚本链适用于正式期刊审稿；本轮为作者自审，不适用。仅登记其"报告完整度≠设计质量"的提醒 |
| scientific-critical-thinking | `scientific-agent-skills/skills/scientific-critical-thinking/` | GRADE/Cochrane RoB 框架面向临床与社会科学证据分级，与本文的单市场时间序列回测不匹配 |
| idea-evaluator | `Supervisor-Skills/skills/idea-evaluator/` | 用于**选题阶段**评估想法是否值得投入；本文建模与实验已完成，不适用 |
| review-paper（6-agent） | `.../21-claesbackman-AI-research-feedback/Skills/review-paper/` | 依赖 6 个并行子代理与 `.tex` 文件，面向指定期刊；本文只取其清单（见采用第 4 项） |
| figure / drawio / figure-designer / academic-figures | 多个 | 本轮不新增或重绘图表，仅沿用既有 5 图 16 表 |
| coderabbit / latex / typst / citation-management / pyzotero 等 | 多个 | 与"中文 Markdown 论文精修"无关 |

---

## 三、合并后的精修规则（本轮实际执行的工作清单）

综合上述 7 项采用技能，形成本轮的四类规则：

### A. 真实性规则（来自 paper-polish + review-paper-light + scientific-writing）
1. 任何统计结论的强弱**只能等于证据强弱**，不得通过文字修饰提高。
2. 严格前向验证的不利结果**必须保留**，且不得用"轻微""基本一致"等词淡化。
3. 统计关联不得写成因果；**不得**出现"导致""驱动""造成"等因果动词（除非有识别策略）。
4. 不得超出样本与城市范围泛化。
5. 市场机会收益**不得**表述为农户利润、收益提升、经营效益。
6. 不新增任何参考文献、案例、数据。

### B. 结构规则（来自 humanizer + literature-review + intro-drafter）
7. 破除"一段一结论、一段一免责"的机械结构；段落按其论证功能组织。
8. 破除公式化过渡词（首先/其次/最后/综上所述/值得注意的是/需要强调的是）的**例行化**使用——按论证关系决定保留、合并或删除，而非一律删除。
9. 破除强制三段并列与冒号加编号列表；确需并列时说明并列依据。
10. 贡献条目必须与正文章节对应。
11. 文献综述按**问题**组织，而非按"四类文献"罗列。

### C. 语言规则（来自 paper-polish + humanizer 中文映射）
12. 去除中文营销化与自我评价用语（赋能、颠覆、深度赋能、本文最重要的诚实结论、不会自欺、令人信服）。
13. 去除假深度尾缀（"从而……""进而……""为……提供了有力支撑"）。
14. 句子长短交错，避免均匀节奏；允许必要的不对称。
15. 保留专业术语与统计口径用词，不做模糊化改写。
16. 同一对象在同一段落内保持同一称谓，不做同义词轮换。

### D. 审稿规则（来自 pre-submission-reviewer + paper-audit）
17. 每条语言问题须锚定具体位置与原文片段。
18. 分级：CRITICAL（学术准确性/事实错误）、MAJOR（论证与结构）、MINOR（措辞）。
19. 全文扫描过度声称词表（中文）：卓越、首次、唯一、最高、完美、碾压、遥遥领先、颠覆性、最优、显著提升（当不显著时）。
20. 数值一致性：正文数字必须与 `FINAL_EVIDENCE_REGISTER.md` 与权威结果表一致。

---

## 四、明确不做的三件事

1. **不追求任何"AI 检测率下降"指标**，也不做此类承诺。
2. **不执行**任何 Skill 中的脚本或环境修改操作。
3. **不改变任何统计结论**；语言修改以"含义不变"为前提，含义相关处一律标注待作者确认。
