# METHOD_BENCHMARK — 六个成熟科研项目的方法对标

> 本文件为 v2 全量重建的**第一阶段强制产出**（施工手册 §4）。
> 所有结论来自**实际阅读**参考项目源码与文档（非仅 README）。
> 参考项目获取方式见 `_fetch_references.sh` / `_fetch_selected.py`（本机 git 直连 github 被网络策略拦截，
> 改用 `gh api` tarball 与 contents API；**只读、未安装、未运行**任何参考项目）。

---

## 0 获取情况

| 项目 | 版本/分支 | 本地位置 | 获取方式 | 体积 |
|---|---|---|---|---|
| scientific-agent-skills | main | `scientific-agent-skills/` | `gh api` 按需抓取 7 个技能目录（108 文件） | 1.2 MB |
| STORM | main | `storm/` | tarball 全量解压 | 6.5 MB |
| GPT Researcher | main | `gpt-researcher/` | tarball 全量解压 | 28 MB |
| PaperQA | main | `paper-qa/` | tarball 全量解压 | 36 MB |
| AI-Scientist | main | `AI-Scientist/` | `gh api` 按需抓取源码（28 文件） | 3.5 MB |
| Zotero | main | `zotero/` | `gh api` 按需抓取元数据相关源码（11 文件） | 508 KB |

---

## 1 核心对标表

| 项目 | 值得借鉴 | 不适合本项目 | 沈阳如何实现 |
|---|---|---|---|
| **scientific-agent-skills** | ①`statistical-analysis` 的 **6 步工作流**：碰数据前锁定假设/结局/设计并**承诺计划检验**；②`test_selection_guide.md` 的**检验选择决策树**（含非参/精确法/Welch 分支）；③`assumptions_and_diagnostics.md` 的**假设与诊断细则**（独立性 HIGH：ACF/PACF/DW；n≥100 时正态性以 Q-Q 图为主；VIF>10 严重）；④`effect_sizes_and_power.md` 的 **effect size 基准表 + 必须配 CI**，且**禁止 post-hoc observed power**；⑤`reporting_standards.md` 的**阴性结果措辞规则**（禁"no effect / unrelated / equivalent"，须报精确 p + 效应量 + CI + 功效）；⑥`statistical_pitfalls.md` **42 条 p 值陷阱**；⑦`evidence_workflow.md` 的 **E/C/N/M/O/R 编号 + `[claim:C001][evidence:E001]` 行内标记**；⑧`peer-review` 的 **claim-evidence 校验器**（`validate_claim_evidence.py`，强枚举 `claim_type/support_level/alignment_issue`，`causal`+`supported` 自动告警）；⑨`scholar-evaluation` 的 **missing/not_applicable 不得记 0**（score=null, uncertainty=null, evidence_ids=[]）；⑩`research-lookup` 的**引用质量规则**（按 DOI/题名去重、排除撤稿、不得发明作者/DOI/效应量） | ①`reporting_checklist` 预置的 **CONSORT/PRISMA 临床指南**与本项目（观察性生态/市场研究）不匹配；②`scholar-evaluation` 的**评分制**（rubric/weights）易被误用为"质量分"，本项目只需状态枚举；③其**医疗/临床试验语境**的术语（arms/blinding/consent）不适用；④自动化 lint **不代表同行评审**（其自身明文声明），不可用来宣称"已通过评审" | ①把 6 步工作流写进 `plan/analysis_plan.yaml` 与 `research_registry.csv`（**先注册再跑**）；②按变量类型填检验决策树并记录；③假设诊断按 HIGH/MEDIUM 分级输出到 `results/metrics/`；④所有回归一律报 **β + 95%CI + raw p + FDR q + N + AR(1)**，禁用 observed power；⑤阴性结果模板化为固定句式；⑥多重检验**预定义 family** 并 BH-FDR；⑦采用 `claim_evidence.csv` 并**逐字段对齐其校验器枚举**；⑧自建 `validate_claims.py` 复刻其硬性规则；⑨状态用 `supported/partly_supported/not_supported/descriptive_only/unsupported`；⑩来源须有 `public_url` 且经人工核验后才可置 `verified` |
| **STORM** | ①**四阶段解耦 + 每阶段可断点续跑**（`Engine` 抽象 + 磁盘产物即检查点，可只重跑某一阶段）；②**先提问/提纲、后写作**的强制依赖链——`ArticleGenerationModule.generate_article` 的必填参数就是 `information_table` + `article_with_outline`；③**提纲充当分节检索查询树**（每节用 `get_outline_as_list` 生成 query 做**局部检索**）；④`StormArticle` 的**引用重编号**机制（`url_to_unified_index`、裁掉未引用来源、按正文出现顺序重排）；⑤`StormInformationTable.construct_url_to_info` **按 URL 去重**；⑥检索器内置 **不可靠/已废弃/黑名单域名表**；⑦`wiki_writer` 的**滚动窗口 + 词数预算**上下文裁剪 | ①面向**维基百科式综述写作**，产出是散文，不要求 claim→数字级证据；②**模拟对话（persona 问答）**机制成本高且与本项目"已有真实数据"的前提不符；③依赖 LLM 生成检索 query，本项目主体是**本地真实数据统计**而非网络检索 | ①把 A01–A08 拆成 **plan → data → method → result → evidence → article → export** 七个可独立重跑的阶段，每阶段落盘检查点；②**先写 `RESEARCH_PLAN.md` 与每篇的 `outline`，通过后才允许跑模型**；③每篇文章的提纲即检索树，正文中每个数字必须回指 `claim_evidence.csv` 的 claim_id；④文献引用做**统一编号**并只保留正文实际引用者；⑤来源按 URL 去重；⑥建立不可靠来源黑名单（SEO 站、AI 摘要、无作者页）；⑦长文本按节生成，避免一次性长文 |
| **GPT Researcher** | ①**事实↔来源的物理载体**：`pretty_print_docs()` 把每段上下文渲染为 `Source: <url>\nTitle:\nContent:`，使 LLM 面对的是 `(url,title,content)` 三元组；②**report prompt 硬约束**：每个实质性论断必须带行内引用、**禁止引用未提供的来源**；③**空上下文护栏**：`writer.py` 在 context 为空时**拒绝写作**（防止无源生成"看起来有引用"的报告）；④**多 Agent 的 reviewer/reviser/fact_checker 分工 + 两处有界内环**（`max_draft_revisions` / `max_fact_check_revisions`，超限即 accept）；⑤`ResearchState`/`DraftState` 的**显式状态 schema**；⑥`visited_urls` 全局去重且**父子研究者共享、不清空**；⑦详细报告的**跨子主题防重复**（回传 `global_written_sections` + `existing_headers`） | ①其 citation grounding 是**提示词级软绑定**——文末 References 由 `visited_urls` **全量超集**生成，**无法反查"某句出自哪个 URL"**（本项目明确禁止这一点）；②FactChecker 是**整篇对整篇**，无法定位到句；③`CURATE_SOURCES` 默认关闭；④面向网页检索场景，不适用于"本地数据 + 官方来源"研究 | ①**升级为可验证的硬绑定**：给每个来源分配稳定 `source_id`（如 `SY_STAT_2025_3-5`），正文只允许引用已登记的 source_id；②由代码**从结构化 claim 列表渲染正文数字**，而非让 LLM 自由书写链接；③`references` **只收正文实际引用的来源**，不用 `visited_urls` 超集；④写作前置**空证据护栏**：claim 无 evidence 则拒绝写入正文；⑤self-review / fact-check 采用**有界循环**（最多 N 轮，超限强制收敛）并落盘 `reviews/`；⑥建立显式状态 schema 供 exporter 消费 |
| **PaperQA** | ①**身份与载体分离**：`DocDetails.url / doi_url / pdf_url`（互联网指针）与 `file_location`（本地/云盘路径）**是不同字段**；②**主键用内容派生 ID 而非路径**：`dockey` 默认 = `content_hash`，`doc_id = encode_id(doi+content_hash)`；③**证据块级引用键** `Context.id = pqac-{8位hash}`，答案中的引用被映射为 docname 并**删除未出现在上下文中的幻觉键**；④**摘要即携带出处**（`citation = text.name + doc.formatted_citation`）；⑤**元数据提供方溯源** `other["client_source"]` / `other["bibtex_source"]`，合并时取并集；⑥`ParsedMetadata/ChunkMetadata` 记录**解析与分块过程元数据**；⑦`source_quality`(0–3) 与 `is_retracted` 字段 | ①面向**学术 PDF 问答**，MMR 向量检索 + LLM 打分（0–10）与 100 词摘要，本项目核心是**统计估计**而非文献问答；②其检索/嵌入管线依赖向量库与 LLM 打分，成本与不确定性高；③`evidence_relevance_score_cutoff` 等阈值需 LLM 判断，不可复现 | ①`source_registry.csv` 严格分离 **`public_url`（互联网身份）** 与 **`local_snapshot`（本地副本）**；②本地文件**永不**作为展示来源；③给每条证据分配稳定 ID（`EV-xxxx`）并用**内容哈希**做去重键；④`claim_evidence.csv` 的 `evidence_id` 指向 EV 号，**不允许悬空 ID**；⑤引文元数据经人工核验后才置 `verified`；⑥记录数据获取/解析过程元数据（版本、日期、抽取方式）；⑦每个来源标 `source_grade`（A/B/C/D） |
| **AI-Scientist** | ①**闭环纪律**：`baseline → experiment → notes → results → writeup → review → improvement`，**每个 run 落盘 `final_info.json` + `notes.txt`**；②**基线作为外部契约固定**（由用户预跑，实验阶段不再重跑）——避免基线被"调优"；③**写作前的逐节 tips + 错误清单 + 编译前程序化校验**（引用是否在 bib、图片文件是否存在、节标题是否重复）；④**反思循环有终止条件**（`"I am done"` / `MAX_ITERS` / `MAX_RUNS`）；⑤**评审结果直接驱动改写并重评**；⑥实验失败**自动回滚**（拷贝快照 + 失败回吐 stderr + `rmtree`）；⑦`notes.txt` 是实验与写作之间的**唯一事实通道**（写作阶段禁止幻觉结果） | ①其**自动科研**（让 LLM 自己提 idea 并改代码）**本项目明确不采用**；②NeurIPS 评审表 + 集成评分机制面向 ML 论文；③依赖 Aider/LaTeX 工具链与 GPU 预跑 | ①把 A01–A08 每篇做成 **"计划→数据→方法→结果→写作→自审→修订"闭环**，每步落盘；②**基线必须在分析开始前固定并写入 `analysis_plan.yaml`**（如"天气模型必须对比仅用历史量价的 baseline"），禁止看到结果后换基线；③写作前冻结 outline 与"每节必须报告的要素清单"，成稿后跑**程序化校验**（数字是否见于 `claim_evidence.csv`、图文件是否存在、编号是否唯一）；④自审循环设上限；⑤新旧结果差异**必须解释而非偷偷改掉**（→ `V1_V2_COMPARISON.md`）；⑥失败的实验保留记录，不隐藏 |
| **Zotero** | ①**父条目（引用元数据）↔ 子附件（文件载体）的严格分离**，并用 `attachmentLinkMode` 显式声明载体类型：`LINKED_URL`（**活的互联网原始来源**，禁止设本地 path） / `IMPORTED_URL`（**网络快照**） / `IMPORTED_FILE`（导入副本） / `LINKED_FILE`（外部本地文件）；②字段系统区分 **title / creator(数组+creatorType) / publicationTitle / publisher / institution / date / url / accessDate**（机构与出版物经 **base-field 机制**区分），`year` 与 `firstCreator` 为**派生字段**；③`toJSON` 的 API 序列化字段集（`key/version/itemType/fields/creators/tags/collections/accessDate/dateAdded/dateModified`）；④附件层独立记录 `contentType` / `filename` / `path` / `mtime` / `md5` | ①其 UI、同步、插件体系与本项目无关；②`citationKey`（Better BibTeX）等扩展字段非本项目必需；③其完整数据模型面向"用户文库管理"，本项目只需**来源登记 + 证据绑定** | ①`source_registry.csv` 字段落地为：`source_id, source_type, title, publisher, authors, published_date, data_period, public_url, accessed_at, local_snapshot, carrier_type, source_grade, notes`；②**`carrier_type` 强制枚举**：`linked_url`（原始网页仍在线）/ `snapshot`（已抓取的网络快照）/ `imported_file`（下载的官方 PDF/XLS）/ `derived`（由 A 级数据加工）；③`public_url` 与 `local_snapshot` **绝不可混**（施工手册 §14/§34）；④所有展示给前端的来源只取 `public_url` + `publisher` + `title` + `data_period` + `accessed_at`；⑤本地路径只允许出现在内部 provenance |

---

## 2 我们自己项目的六条研究原则（P1–P6）

> 以下六条为**强制约束**，写入 `plan/analysis_plan.yaml` 与每篇文章的写作规范；违反即不予接受。

### P1 先问题，后分析
每一个统计分析必须回答一个**明确写下的问题**（`research_registry.csv` 的 `research_question`）。
不允许"先跑一批回归，再从结果里找故事"。
落地：`RESEARCH_PLAN.md` 中每项研究先写问题、总体、分析单位、暴露、结局、时间范围，**通过后才允许进入 `scripts/`**。

### P2 先计划，后跑模型
不得看到结果以后再修改研究问题、更换主模型、更换基线、更换样本区间。
所有主模型、稳健性模型、多重检验 family、阈值与窗口必须在 `analysis_plan.yaml` **预注册**；
探索性内容必须显式标为 `exploratory`，**不得伪装成验证性研究**（`hypothesis_type` 字段强制区分 confirmatory / exploratory / descriptive）。

### P3 数字必须绑定证据
所有写入文章的数字必须能找到：**数据 → 表 → 模型 → 图 → 方法**。
落地：`claim_evidence.csv` 的每一行 `claim` 必须携带 `estimate / ci_low / ci_high / p_raw / p_adjusted / sample_size / table_id / figure_id / method_id`；
`validate_claims.py` 校验：正文出现的数字必须能在 registry 中检索到，否则构建失败。

### P4 外部事实必须绑定原始来源
政府数据、天气数据、农学定义、方法依据必须能回到**公开 URL / DOI**。
落地：`source_registry.csv` 的 `public_url` 非空且可访问；`local_snapshot` 仅作内部留档，**绝不允许作为展示来源**（施工手册 §34）；
来源分级 A/B/C/D；只有经人工核验的来源才可置 `verified`。

### P5 结果和解释严格分开
"观察到了什么"（结果）与"为什么会这样"（讨论）**不得混写**。
落地：文章结构强制 `4 研究结果` 与 `5 讨论` 分离；
结果段只允许"数据显示 / 估计值 / 置信区间 / 未得到支持"；机制性语言（"价格承担供需调节功能"等）只允许出现在讨论段，且须标注为解释而非证据。

### P6 学术文章和前端数据彻底分离
学术文章负责完整研究；前端数据由学术文章**再次结构化导出**，不从前端反向影响文章。
落地：`reports/v2/*.md` 为唯一权威正文；`exports/frontend/articles/A0X.json` 由 exporter **按篇生成**（一文一文件、一文一 JSON），
禁止 `MASTER.md` 字符切片、禁止 `text[:500]` 截断、禁止跨篇串联；每篇 Markdown 末尾带 `<!-- ARTICLE_END:A0X -->` 由 validator 校验。

---

## 3 从对标中得到的**流程顺序**（施工手册 §47 的本地化）

```
QUESTION          → plan/RESEARCH_PLAN.md + research_registry.csv（预注册）
   ↓
DATA              → plan/variable_dictionary.csv + sources/source_registry.csv
   ↓
METHOD            → plan/analysis_plan.yaml（主模型/稳健性/family 全部预定）
   ↓
RESULT            → results/tables + results/figures + results/metrics（脚本可重跑）
   ↓
EVIDENCE          → evidence/claim_evidence.csv（claim → estimate/CI/p/N → table/figure/method）
   ↓
INTERPRETATION    → 文章第 5 节（与第 4 节物理分离）
   ↓
ARTICLE           → reports/v2/*.md（每篇独立文件 + ARTICLE_END 标记）
   ↓
FRONTEND          → exports/frontend/articles/*.json + sources.json + manifest.json
```

**禁止反向**：先编故事 → 再找数字证明。

---

## 4 明确不采用的做法（负面清单）

| 做法 | 来源项目 | 为何不用 |
|---|---|---|
| 让 LLM 自动生成研究 idea 并自我改代码 | AI-Scientist | 本项目是**已有真实数据**的统计研究，问题由领域与政策需求决定 |
| 模拟对话（persona 问答）扩写内容 | STORM | 与"数据→估计"的研究范式不符，且引入不可追溯文本 |
| 文末 References 用访问过的 URL **全量超集** | GPT Researcher | 会显示未实际引用的来源，违反 P3/P4 |
| 用 LLM 打分（0–10）决定证据取舍 | PaperQA | 不可复现；本项目证据取舍由**预注册方法**决定 |
| 从前端 `MASTER.md` 按字符位置切片 | v1 旧流程 | 串篇/截断的根因（施工手册 §29/§32/§33） |
| 用 `text[:500]` 生成摘要 | v1 旧流程 | 破坏语义；改为文章自身提供 `abstract` 与 `frontend_summary` 两个独立字段 |
| CONSORT/PRISMA 等临床报告清单 | scientific-agent-skills | 研究设计不匹配；本项目使用 STROBE 类观察性研究要素并自定义清单 |
| scholar-evaluation 的评分/权重体系 | scientific-agent-skills | 易被误读为"质量分"；本项目只用状态枚举 |
| post-hoc observed power | scientific-agent-skills（禁用） | 是 p 值的确定性函数，循环且误导 |
