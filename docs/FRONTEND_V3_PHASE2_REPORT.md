# AgriScope Frontend V3 第二阶段 · 施工报告

> **第三轮更新（2026-10-09 傍晚）**：上一轮"仍未完成"清单中的 §21 / §25 / §26 / §31–§34 / §38 / §42 已全部落地；**以本节为准**。
>
> - **§21 三栏 Research Workspace**：新增 `features/research-v2/EvidenceRail.tsx`；左栏策展树收窄、中栏默认「交互探索」（完整文章为次入口，顺序符合 §22）、右栏证据轨（来源/方法/样本/CI/FDR/局限，全部取自研究侧现有字段，**缺失整块不渲染**）；桌面 248/838/272 三栏，≤1024 左栏抽屉、≤768 单栏 + 证据折叠；`aria-expanded/aria-controls`、Esc 先关抽屉再退出城市、开抽屉移焦关时归位、图表补 sr-only 摘要。
> - **§25 cross-city 专页**：新增 `features/cross-city/`（`CrossCityPage`、`LiaoningMiniMap`、`comparability`）；指标切换只用**真实列**（`HHI`/`CR4`/`seasonal_corr`/`mean_corr`/`median_post_z`/`placebo_p`/`corr_at_best`，无气候表故不放气候项）；地图联动为轻量 SVG 高亮（未引入 Three.js）；**明确标注可比较性**（结构指标=可直接比较、同步/韧性/领先滞后=探索性、价格水平=不可直接比较、城际配对按真实 `freq_pair` 逐行判定）；页面写明「不提供六城菜价排行」；领先/滞后只写"探索性"。
> - **§26 synthesis 专题**：研究中心「研究成果」区独立入口「六城综合研究（专题）」，以 A11 真实内容做 hero 版式（标题/摘要/关键发现/表/图/局限/结论），不改写研究结论。
> - **§42 讲解模式**：新增 `features/presentation/`（8 步导览，全部为真实存在的路由与页面）；自动导航+滚动+高亮、旁白经 `aria-live` 播报、上一步/下一步/暂停·继续/退出、Esc 捕获阶段退出；旁白只复述真实页面文案与研究模块名，**无编造数字、无"准确率"**；未接入真实数字人资源（规范本身允许先做导览）。
> - **§31 Motion 收敛**：路由转场位移由 24px/16px 收敛到 8px（scale 保持 .994），新组件入场仅 8px + 透明度，`prefers-reduced-motion` 退化为瞬时。
> - **§32/§38 压测与无障碍**：`FRONTEND_V3_STRESS_AND_A11Y_REPORT.md` —— 20 次 hard refresh / 30 次 route change / 20 次 city change / 20 次 horizon change / 两轮 6 档 resize / back·forward / 直接 URL：**四种已知症状（底部飞线、错误按钮飞线、首刷闪烁、resize 错位）全部未出现**；键盘可达主导航/地图城市/决策页签/风险条/两个抽屉，Esc 可关抽屉，focus-visible 可见，图表有文本摘要，颜色非唯一状态表达。
> - **§49 交叉验证**：抽样 **9/9 全部一致**（短期 7 天中心值与区间、长期 150/180、朝阳与铁岭 HHI、季节幅度 0.266、沈阳 A02 天气效应、跨城 r=0.97、铁岭 NOT_SUPPORTED）。
> - **第三轮验证（本人执行）**：`vitest` **43 files / 389 passed**；`tsc --noEmit` 0 错误；`npm run build` 通过（verify-ui-strings 41 产物、禁用字样 0）；`pytest backend/tests` **74 passed**；`acceptance` **19/19 → BACKEND_FROZEN**；`secret_scan` **CLEAN**。
>
> **仍如实保留的未完成项**：§44 的**实际瘦身执行**（只出 `RESEARCH_ASSET_USAGE_REPORT.md`，`runtime/research` 仍 327MB，未删任何文件；规范本身要求"先完成接入再谈瘦身"）；production preview 与真机移动端未验收（dev server + 设备仿真代替，已在压测报告注明）；真实数字人资源未接入；`frontend/src/legacy/**` 五个零引用目录按 AGENTS 规则仍在（需先更新 `docs/ITEACH_MIGRATION_MATRIX.md` 才能删）。
>
> **§54 自测问题第三次回答**：辽宁农业态势与决策中心现在是真实、诚实、可用的产品本体（真实状态组装判断、数据不足如实降级、无编造风险/推荐）；研究中心承担证据层，并已具备三栏工作台、六城模块、NOT_SUPPORTED 正式状态、跨城与综合专题、LLM 证据页。**Frontend V3 第二阶段的核心链路已完整贯通。**

> **第二轮更新（2026-10-09 下午）**：本报告第 0/7/8/9/10–16/17–23/25/26/29/30–34/39/44/45/47/48/49/51 节的"未做"部分已大批落地。**以本节为准**，下文保留为第一轮的原始记录。
>
> **第二轮新增完成**
> - **§8 辽宁农业态势重做**：地图为唯一视觉主角；六态由真实数据推导（`capabilities.supported=false` → 数据不足；Daily 信号 WATCH/HIGH → 关注；supported 但无日度序列 → 部分数据；其余正常）；hover 描边增强+抬升+他城降权+右侧摘要同步；click 只更新全局 City Context（URL 不变），右侧给「进入决策 / 查看研究」；底部四主题（市场趋势/生产结构/气象/异常事件）取自 `/api/research/catalog` 模块原句+状态；去卡片墙；键盘 focus 即 hover、Escape 清除；四态有文字+形状标记。
> - **§10–§14 决策中心**：新增默认 `center` 视图；首屏判断句由 `market_state/forecast_direction/risk_band/confidence/evidence_status` 经固定模板拼装（不调用在线 LLM）；7/14/30 短期与 30–180 长期**语义分区**（长驻文案「用于种植与上市周期参考，不等同于短期生产预测」，150/180 标「探索性结果」）；切 horizon 不整页重载；风险剖面 5 条横向条可展开「为什么/来源/真实数值/研究链接」；作物比较表只用五个分级词、**无评分**；`INSUFFICIENT_MARKET_DATA` 如实呈现不 fallback。
> - **§15 Evidence Drawer**：右侧推入、`role=dialog`+`aria-modal`、Escape 关闭、点内容不关、锁滚动与焦点归还；七层证据全部来自真实端点，缺失层如实标注；底部「查看完整研究」按 topic 映射并经 `researchIdKind` 校验真实存在。
> - **§16 情景模拟**：`/scenario-lab` 左现实（daily 观测，实线）右模拟（long-horizon 情景，虚线）+ 图例 + SVG aria 摘要；常驻「当前正在查看模拟情景 / 现实数据 ≠ 用户假设」；缺实际投入的收益变量标 `USER_INPUT_REQUIRED`。
> - **§9 Context URL 连续性**（本人实现）：四要素 `city/crop/horizon/as_of` 进 query 并与 zustand 双向同步；URL 为准、store 补齐、`replace` 不污染历史、解析后等值则不写（无抖动）；刷新/后退/前进/直接链接均可复原；非法值（未知城市、非 7/14/30、非法日期、脚本片段）一律拒绝。
> - **§29 LLM 研究页**：新增只读端点 `GET /api/research/llm-evaluation`（产物缺失→503，响应不含任何密钥/base_url）+ 研究中心 LLM 证据区块，完整展示四件事（blind 为何无增益、context 为何回溯有增益、为何仍不能上线、独立验证缺失），并写明「决策中心禁止使用 LLM Context 作为正式生产模型」。
> - **§44 Research Asset Usage Report**：`RESEARCH_ASSET_USAGE_REPORT.md`；`runtime/research` 327M 中仅 `product/` 3.3M（约 1%）进入产品链路；最大未引用资产 `shenyang/case_studies` 261M、`shenyang/assets` 56M、`long_horizon` 940K；**本轮未删除任何文件**。
> - **§43 部分**：README 已更正"LLM 尚未评估"的过期表述并指向 RC3/LLM 报告；根目录散落报告**只报告不移动**（由本 Agent 维护）。
>
> **第二轮最终验证（本人执行）**
> - `npx vitest run` → **39 files / 370 passed**；`npx tsc --noEmit -p tsconfig.app.json` → 0 错误；`npm run build` → 通过（`verify-ui-strings` 41 个产物、禁用字样 0）。
> - `PYTHONPATH=backend pytest backend/tests` → **74 passed**；`python3 backend/scripts/acceptance.py` → **19/19 → BACKEND_FROZEN**。
> - 浏览器实测：`/liaoning`（六态+hover+右侧摘要+四主题）、`/decision` 与 `/cities/<city>/decision`（判断句、7/14/30、长期分区、风险展开、Drawer 不跳路由、大连如实 `INSUFFICIENT_MARKET_DATA`）、`/scenario-lab`（现实 vs 模拟）、`/research`（六城 + LLM 证据区块）——页面级 console error 为 0。
>
> **仍未完成**：§21 三栏 Research Workspace 的策展树侧改造（沈阳仍为既有两栏窗口）、§25 cross-city 专用指标切换/地图联动专页与「禁止绝对菜价排名」口径警示、§26 synthesis 专题封面、§31–§34 underline 四类压测与 Motion 专项、§38 a11y 专项审计、§42 讲解模式（规范本身允许置于核心功能之后）、§44 的**实际瘦身执行**（只出报告未删文件）、§49 中与长期 registry/HHI/seasonal amplitude 相关的交叉抽样。
>
> **§54 自测问题第二次回答**：辽宁态势与决策中心已具备真实、诚实、可用的产品形态（判断句来自真实状态、数据不足如实降级、风险与比较无编造）；研究中心仍在其上作为证据层。但 §21/§25/§26 与压测未完成，**因此仍不能宣称 Frontend V3 第二阶段全部完成**。

生成时间：2026-10-09
分支：`feat/frontend-v3-arch-consolidation`，基线 commit `7bbfddd`（开工时工作区 clean）

## 0. 结论摘要（先说没做完的部分）

本轮完成的是**规范 §6 标记的最高优先级：六城研究资产真正接入**（发布链路 + 后端只读 API + 前端数据源与研究中心六城化 + NOT_SUPPORTED 正式状态），全链路已真实联调与浏览器验收。

**尚未开始**：§8 辽宁农业态势重做、§10–§18 决策中心重构、§15 Evidence Drawer、§16 情景模拟、§21 三栏 Research Workspace（策展树侧）、§25 cross-city 专页、§26 synthesis 专页、§29 LLM Research 页、§9 完整 Context URL 连续性（Crop/Date/Horizon 仍未进 URL）、§31–§34 Motion/underline 压测、§42 讲解模式、§43 README/散落报告归位、§44 Research Asset Usage Report。

即：**本轮不是完整交付，是六城证据层的地基与首屏可用形态。**

## 1. 开工前真实前端状态

- 三入口骨架已在位（辽宁农业态势 / 决策中心 / 研究中心），`ContextBar`、Design Token、`ResearchCenterPage` 壳、`MarketOverview` 存在。
- 研究侧：`runtime/research` 与父目录 `data/research` 是两份 **324MB** 相同副本；`publishing` 是**整包 copytree、无索引、无白名单**。
- 前端 `frontend/public/research` **只有沈阳**；`domain/research/catalog` 只编译了 `shenyang-tree.json` 一棵树。
- backend **完全没有 research API**，也没有任何 `StaticFiles` 挂载。
- 结果：研究中心首页必须把朝阳/锦州/大连/丹东/铁岭显示为「前端浏览载荷待接入」。

## 2. 保留的旧组件

`features/research-v2/`（`CityResearchPage`、`ResearchTree`、`CityResearchPreview`、`ResearchArticleView`、`TopicExplorer`、`DataTable`、`Figure`、`markdown`）、`domain/research/catalog`（沈阳策展树 + 结构校验）、`domain/research/v2`（repository/selectors/metrics 契约）、`features/liaoning`（R3F 辽宁地图）、`features/decision`、`features/spatial`、`app/*` 外壳与 `appHistory`——**全部保留，未重写**。

## 3. 删除 / 废弃的旧逻辑

- **废弃**：前端研究数据的 `/research/<city>` 静态载荷路径（仅沈阳可用）→ 正式路径改为后端只读 `/api/research/<city>`。
- **保留为 legacy compatibility**：`frontend/public/research/shenyang`（未删除，`verify-research-integrity.mjs` 仍在校验它）。
- **未删除**：`frontend/src/legacy/{research-v1,city-v1,components-v1,insight-v1,rainstorm-v1}` 五个目录确认**零生产引用**，但本轮按「删除前先更新 `docs/ITEACH_MIGRATION_MATRIX.md`」的项目规则**未动**，仅记录判定为可废弃。

## 4. 六城研究接入方式

新增发布器 `pipelines/publishing/publish_research.py`：把 `runtime/research/<city>` 的**模块级真实导出**转成前端产品载荷。

| 目录 | 模块数 | 说明 |
|---|---|---|
| shenyang | 9 | A01–A09，`ACCEPTED` |
| chaoyang / jinzhou / dalian | 各 9 | `DRAFT`，均带 `explorer` |
| dandong / tieling | 各 9 | 7 个 `NOT_SUPPORTED`（A01–A06、A08）+ 2 个 `DRAFT` |
| cross_city | 2 | A10「辽宁六城农业市场与风险比较研究」+ A11「辽宁六城农业市场周期、气象响应与区域差异研究」 |

产物：`runtime/research/product/<city>/{manifest.json, sources.json, articles/A0x.json, tables/, figures/, references.md, sync-report.json}` + 轻量总索引 `runtime/research/research_catalog.json`（**56 个模块 / 40KB，不含正文**）。
产物体积 **3.3MB**（研究目录 324MB）；`article.json` 与源文件**逐字节一致**（sha256 抽查 3 城 × 2 篇 + A10/A11）。

## 5. runtime/research 数据流

```
data/research（父目录，只读研究源）
  ↓ pipelines/publishing/publish_runtime.py（既有）+ publish_research.py（新增，只做产品载荷与索引）
AgriScope/runtime/research/{<city> 原始研究, product/<city> 产品载荷, research_catalog.json}
  ↓ backend 只读 API（路径白名单）
  ↓ frontend ResearchRepository（统一取数）
研究中心 / 城市研究工作台
```
**未把 324MB 复制进 `frontend/public`**（规范 §6.1 红线）。

## 6. 新增 backend research API

`backend/app/routes/research.py` + `backend/app/services/research_service.py`（最小只读，不改研究方法与结果）：

| 端点 | 作用 |
|---|---|
| `GET /api/research/catalog` | 轻量总索引（研究中心首页只加载它） |
| `GET /api/research/cities` | 城市与模块概况 |
| `GET /api/research/{city}/manifest.json` | 城市研究清单 |
| `GET /api/research/{city}/sources.json` | 来源登记 |
| `GET /api/research/{city}/sync-report.json` | 同步报告 |
| `GET /api/research/{city}/articles/{id}.json` | 模块正文（逐字节透传） |
| `GET /api/research/{city}/references.md` | 来源与参考文献（纯文本） |
| `GET /api/research/{city}/tables/{file}` | CSV（按需） |
| `GET /api/research/{city}/figures/{file}` | 图片（按需） |

**路径白名单**：city `^[a-z][a-z_]{1,19}$`、article `^A\d{2,3}$`、file `^[A-Za-z0-9][A-Za-z0-9_.\-]{0,79}\.(csv|png|jpg|jpeg|svg|webp)$`，再叠加「resolve 后必须落在 product 根内」二次校验；错误统一走既有 `{error_code,message,request_id,details}` 信封（新增 `RESEARCH_UNAVAILABLE`）。
新增契约测试 `backend/tests/test_research_api.py`（19 项），含**服务层原始穿越串**拒绝（HTTP 客户端会先归一化 `..`，故必须绕过传输层断言）。

## 7. 辽宁态势如何工作

**本轮未改动**。仍然是既有 R3F 地图 + `MarketOverview`。规范 §8 要求的「地图为唯一视觉主角、去卡片墙、右侧城市摘要、底部市场趋势」尚未实施。

## 8. 地图交互如何工作

**本轮未改动**。既有实现：单 Canvas 服务全路由（`frameloop=demand`）、`ExtrudeGeometry`、`Canvas`+`Html` 城市标签、`domain/geography/cities.ts` 六城 adcode 映射（沈阳210100/铁岭211200/朝阳211300/锦州210700/丹东210600/大连210200）。规范 §8.1 要求的 `normal/hover/selected/warning/partial-data/market-data-unavailable` 六态尚未系统化。

## 9. Context 如何保持

**本轮未改动，这是已知缺口**：City 已进路径，决策 `view/plan` 与研究 `mode=article` 已进 query；**Crop / Date / Horizon 未进 URL**（horizon 仅在 sessionStorage）。back/forward 由自维护的 `appHistory`（不信任浏览器历史）实现。规范 §9 要求的四要素 URL 同步、刷新/后退/前进不丢 Context 尚未完成。

## 10–16. 决策中心（首屏 / 7-14-30 / 长期 / 风险剖面 / 作物比较 / Evidence Drawer / Scenario）

**本轮均未改动**。既有 `features/decision`（`DecisionPage`/`Input`/`ResultView`/`Compare`/`Stress`）与 `features/scenario`（`ScenarioPage`、`DecisionStressPage`）保持原状；规范 §10–§18 的重构（真实状态组装的首屏判断文案、短期/长期语义分区、风险剖面、作物比较的分级结论、右侧 Evidence Drawer、现实 vs 模拟双线）尚未实施。

## 17–23. 研究中心

**已实施（本轮主要成果）**

- **§19 研究中心首页**：数据源换成 `/api/research/catalog`；六城逐城显示真实模块数与可进入状态；跨城市与综合研究作为独立条目列出（两个真实模块标题）；底部如实计数「已发布 7 个研究目录、56 个模块；其中 6 座研究城市可进入」；索引区保留「研究报告」「方法与溯源」。
- **§20 城市研究首页**：`/cities/<city>` 对无策展树的五城 + 跨城市改走**模块级工作台**（`CityModulesWorkspace`）：左侧 A01–A09 模块清单（标题 + 真实状态），右侧模块详情（状态、关键词、研究侧摘要）。
- **§22 双模式**：默认「交互探索」，次入口「完整文章」；**没有 explorer 的模块（沈阳全部）不显示交互页签**，直接呈现完整文章——不假装可交互。
- **§22 交互探索不重算**：把研究侧 `explorer.series`（真实列名 `x/y/group/facet`）一对一映射到既有 `TopicExplorer`，只画已导出的表；另展示研究侧登记的指标列名（仅名字，不解释不排序）。
- **§23 完整文章**：复用既有 `ResearchArticleView`（含图表、来源、局限）。
- **§24 NOT_SUPPORTED 正式组件**：`NotSupportedResearchState` —— 标题「当前数据不足以支持本研究」，分块展示**研究侧原文**的「原因 / 缺失或受限的数据 / 摘要 / 方法与数据口径」，并明确「因此本研究不生成市场响应结论」；丹东 7 个模块实测命中，**不渲染任何假图表**。

## 24–26. NOT_SUPPORTED / Cross-city / Synthesis

- §24 **已实施**（见上）。
- §25 cross-city：目前仅作为一个可进入的研究目录（模块级工作台 + 完整文章），**未做**专用「辽宁六城比较」指标切换/地图联动专页；§25.1「禁止绝对菜价排名」的口径警示**未实现**。
- §26 synthesis：已作为 cross_city 的 A11 模块可进入，**未做**专题封面/hero 入口。

## 27–29. 研究结论不被改写 / 天气不是主角 / LLM 展示

- 六城接入**未改写任何研究结论**：article 逐字节透传，NOT_SUPPORTED 直接转述研究侧原文。
- §29 LLM Research 页**未实现**（LLM 结论已在根目录 `LLM_REAL_EVALUATION_REPORT.md`、`LLM_ABLATION_V2_REPORT.md`、`HYBRID_V2_REPORT.md` 与 `RC3_*` 中；决策中心仍禁止使用 LLM Context 作为生产模型，该约束未被违反）。

## 30–34. 动画 / underline / 生命周期 / reduced-motion

- 新增组件**未引入任何新动画**，只复用既有背景/边框过渡（180ms，`--ag-ease-standard`）。
- 新组件已声明 `@media (prefers-reduced-motion: reduce)` 关闭过渡。
- §32 的 20 次 hard refresh / 30 次 route change 等**压测未执行**；既有「移除 shared layoutId、改本地 scaleX」的修复保持未动。

## 35–38. Design System / 去卡片墙 / Responsive / Accessibility

- 新组件**全部使用既有 token**（`--ag-paper*`、`--ag-ink*`、`--ag-rule*`、`--ag-evidence-*`、`--ag-dur-*`），未新增颜色字面量；`--ag-radius-*` 为 0，故新组件同样**无圆角卡片**。
- 状态色语义：`NOT_SUPPORTED` 用 `--ag-evidence-unsupported`，`ACCEPTED` 用 `--ag-evidence-a`。
- 模块清单用 `<ol>` + `<button>`，页签用 `role="tablist"`/`role="tab"` + `aria-selected`，正文区 `aria-live="polite"`，错误用 `role="alert"`，`aria-busy` 标注载入态；`:focus-visible` 有可见轮廓。
- 响应式：模块清单在 ≤1024px 收起状态芯片；**未**做 1440/1920 专项验收。

## 39. Loading / Error 状态

新增三态并**如实呈现**：载入中（保留高度，文案「六城研究索引载入中」）、读取失败（`role="alert"` + 说明「后端未启动或研究产物未发布时会出现该状态；不展示占位数据」）、无该城市（「该城市暂无已发布研究」）。
**未**建立规范 §39 要求的完整状态字典（`partial_data`/`low_confidence`/`proxy_only`/`scenario_only`/`user_input_required`/`not_supported` 的统一文案体系）。

## 40. 性能 / chunk

- 研究索引 40KB、产品载荷 3.3MB，**首页只加载 catalog**；正文/表格/图片均按需（`GET .../articles/*.json`、`tables/*.csv`、`figures/*.png`）。
- 构建产物：`spatial-runtime` 943.82 kB（gzip 253.42 kB）、`react-runtime` 192.98 kB、`index` 163.37 kB、`motion-runtime` 127.11 kB —— 与改动前一致，**未新增 chunk**。
- **未**输出正式 bundle audit 报告。

## 41. 旧沈阳研究兼容

已覆盖：沈阳 9 篇 `article.json` **没有** `explorer`，工作台据此**不显示交互页签**、不生成空图表；`frontend/public/research/shenyang` 保持 legacy 载荷不动。缺 `methodology/limitations` 的老文章仍由 `ResearchArticleView` 的既有降级逻辑处理。

## 42–46. 讲解模式 / README / 瘦身 / 数据真实性 / Science Integrity

- §42 讲解模式**未实现**。
- §43 README 与根目录散落报告（`RC3_*.md`、`HYBRID_V2_REPORT.md`、`LLM_*_REPORT.md`、`PROJECT_STATUS.md`）**未归位**：这些文件由**本 Agent 在上一阶段（RC3 交付）创建并维护**，按规范「如果仍有人维护：不要擅自移动，只报告」→ **只报告，未移动**。
- §44 Research Asset Usage Report**未生成**；`runtime/research` **未删任何文件**（规范要求先完成接入再谈瘦身）。
- §45 数据真实性：新增页面所有数字均来自 `runtime/research/product`（经后端透传）；**无 mock、无随机数、无硬编码演示数字**；开发期 mock 仅存在于既有 `providers/decision` 的 DEV fixtures（未改动）。
- §46 Science Integrity 未被违反：LLM 仍 `RESEARCH_ONLY`；NOT_SUPPORTED 如实呈现；未新增因果/最优销售/跟风种植类表述。

## 47. 测试（真实结果）

| 项 | 结果 |
|---|---|
| `npm run typecheck` | 通过 |
| `npx vitest run` | **32 files / 324 tests passed** |
| `npm run build`（含 prebuild 三道 verify + tsc + vite build + production boundary + verify:ui） | **通过**；`verify-ui-strings` 39 个产物、禁用字样 0 |
| `PYTHONPATH=backend pytest backend/tests` | **71 passed**（含新增 19 项 research 契约） |
| `python3 backend/scripts/acceptance.py` | **19/19 通过 → BACKEND_FROZEN** |
| `pipelines/publishing/publish_research.py` | 退出码 0，幂等复跑一致 |

## 48. 浏览器实测（真实执行）

用浏览器子代理实测三页，**页面级 console error 均为 0**：

1. `/research`：六城齐全（顺序为沈阳、铁岭、朝阳、锦州、丹东、大连），每城「9 个研究模块 · …」+「进入研究 →」；跨城条目含两个真实模块标题；计数原文「已发布 7 个研究目录、56 个模块；其中 6 座研究城市可进入。」；无「前端浏览载荷待接入」。
2. `/cities/chaoyang`：左侧 A01–A09 均为 DRAFT；右侧默认 A01，两页签；交互探索渲染真实图表 + 14 项品种选择器 + 「研究侧登记的指标列…」+「方法与数据口径」；切「完整文章」正文正常。
3. `/cities/dandong`：A01–A06、A08 共 7 个 NOT_SUPPORTED；选中后出现「当前数据不足以支持本研究」及原因/缺失数据/摘要分块（原文含「覆盖稀疏」「作物词表碎片化」）；`img=0、svg=0`，无假图表。

控制台仅有 info 级提示（React DevTools、以及补齐前的列/取值未登记告警——**现已修复**）。

## 49. 数据交叉验证结果

| 抽样 | 前端/接口值 | 源 | 一致 |
|---|---|---|---|
| research catalog 计数 | 7 目录 / 56 模块 | `runtime/research/research_catalog.json` | ✅ |
| 朝阳 A03 explorer 系列图 | x=window, y=beta_per_sd | `runtime/research/chaoyang/A03` | ✅ |
| 丹东 A01 判定 | NOT_SUPPORTED + 原因原文 | `runtime/research/dandong/A01/article.json` | ✅ |
| 沈阳 A03 | 无 explorer（如实为空） | 同上（shenyang） | ✅ |
| 表格 CSV | `text/csv` 38,240 bytes（A03_lag_windows） | `runtime/research/product/chaoyang/tables` | ✅ |
| article 逐字节 | 3 城 × 2 篇 + A10/A11 sha256 相同 | 源 `article.json` | ✅ |
| 列名覆盖 | 193/193 列已登记（原 87） | 108 张表表头 | ✅ |

**未抽样**：短期 forecast、long horizon registry、铁岭/朝阳 HHI、seasonal amplitude、weather effect、cross-city r（这些值与本轮改动无关，属既有页面）。

## 50. 尚存问题

1. **§8/§10–§18 未做**：辽宁态势与决策中心仍是旧实现，这是与规范目标的最大差距。
2. **Crop/Date/Horizon 未进 URL**（§9）。
3. **列/取值登记**本轮已补齐 193 列 + 44 个作物取值，但 `METRIC_GAPS.md` 描述的 definition/formula 缺口仍存在（未逐列补定义）。
4. **NOT_SUPPORTED 的"推荐可支持模块"**：当前仅给通用提示，未逐城列出可支持模块清单。
5. **cross_city 无 `sources.json`**（源目录无 `source_registry.csv`），`references.md` 只有标题行 —— 后端如实返回空数组，前端不补造。
6. **五城只有模块级结构**：研究侧未导出「方向→研究点→可逐字校验引句」，故无法做沈阳那样的研究点级交互；本轮**没有**代其编造。
7. **压测与 a11y 专项未执行**（§32/§38）。
8. `runtime/research` 仍含 324MB（含沈阳 `case_studies` 261MB + `assets` 56MB），瘦身待 §44 的 usage report 之后再谈。

## 51. git status（未提交，按规范交你决定）

```
 M backend/app/errors.py
 M backend/app/main.py
 M frontend/src/domain/research/v2/metrics.ts
 M frontend/src/domain/research/v2/repository.ts
 M frontend/src/domain/research/v2/types.ts
 M frontend/src/features/research-center/ResearchCenterPage.tsx
 M frontend/src/features/research-v2/CityResearchPage.tsx
?? backend/app/routes/research.py
?? backend/app/services/research_service.py
?? backend/tests/test_research_api.py
?? frontend/src/domain/research/runtime/
?? frontend/src/features/research-v2/CityModulesWorkspace.tsx
?? frontend/src/features/research-v2/NotSupportedResearchState.tsx
?? frontend/src/features/research-v2/module-workspace.css
?? pipelines/publishing/publish_research.py
```
7 个文件修改（+319 / −42），8 项新增；`git diff` 中**没有**删除既有研究内容或既有页面功能。
`runtime/research/product/**` 与 `research_catalog.json` 被 `.gitignore` 忽略（发布产物，不入库）。

**未 commit、未 merge、未 tag、未 deploy。**

## 52. 是否存在任何 mock / hardcode / placeholder

- 新增代码：**无 mock、无随机数、无硬编码业务数字、无 placeholder**。所有数字来自 `runtime/research/product` 经后端透传。
- 未新增任何「敬请期待 / Coming soon / 暂无数据」式文案。
- 唯一保留的 mock 是既有 `providers/decision` 的 DEV fixtures（本轮未触碰，且构建期 `verify-production-boundary` 已确认正式边界为 `formal API / unavailable`）。

## 53. §54 自测问题（诚实回答）

> 「如果现在把研究中心从导航里暂时隐藏，辽宁农业态势 + 决策中心是否已经构成一个完整、有用、可信的农业决策产品？」

**答案：否。** 辽宁态势与决策中心仍是旧实现，尚未按规范 §8/§10–§18 重构，因此**本轮还不能算完成 Frontend V3 第二阶段**。本轮交付的是它必需的地基：六城证据层已真实可用、可追溯、无伪造。