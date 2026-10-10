# AgriScope 研究资产使用情况报告（RESEARCH_ASSET_USAGE_REPORT.md）

- 生成日期：2026-10-09
- 依据：项目架构规范 §44（研究资产使用与瘦身评估）
- 性质：**只读测量**。本轮**未删除、未修改任何文件**，仅新建本报告一个文件。
- 数据来源：全部为 `du -sh` / `du -sk` / `find … | wc -l` / `ls` / `cat` 的真实输出，未做估算。
- 代码依据：`AgriScope/pipelines/publishing/publish_research.py`、`AgriScope/backend/app/services/research_service.py`、`AgriScope/backend/app/routes/research.py`、`AgriScope/frontend/src/domain/research/v2/repository.ts`。

## 0. 结论摘要（TL;DR）

- `runtime/research` 实测总体积 **327M**（`du -sk` = 334844 KB ≈ 327.0 MiB）。其中真正进入产品链路（`product/`）的仅 **3.3M**，占比约 **1.0%**；**约 99%** 的运行副本体积未被 `publishing` 选中。
- 未引用部分几乎全部集中在 **shenyang**：
  1. `shenyang/case_studies/` — **261M**（386 文件）
  2. `shenyang/assets/` — **56M**（274 文件）
  3. `long_horizon/` — **940K**（3 文件，未纳入 `CITY_ORDER`，整目录未发布）
- 未发布/未引用的三城结构基本一致；非沈阳城市本体都很小（合计约 3.1M）。
- 前端只通过后端只读 API `/api/research/*` 读取 `product/`；`frontend/public/research/shenyang`（**580K**，42 文件）仅作 legacy 兼容保留。
- 源目录 `data/research` 实测 **324M**，保持完整、未被本报告触碰。

## 1. 使用的命令（测量口径）

```bash
# 总量与一级项
du -sh runtime/research
du -sh runtime/research/{shenyang,chaoyang,jinzhou,dalian,dandong,tieling,cross_city,long_horizon,product,README.md,research_catalog.json}
du -sk runtime/research            # 精确 KB：334844
du -sh runtime/research/product
du -sh runtime/research/product/*

# 一级子路径体积 + 文件数
for c in shenyang chaoyang jinzhou dalian dandong tieling cross_city; do
  for d in runtime/research/$c/*/; do
    echo "$(du -sh "$d"|cut -f1)  $(find "$d" -type f|wc -l)files  $d"
  done
done

# product 载荷文件数与子目录构成
for c in runtime/research/product/*/; do find "$c" -type f | wc -l; done
find runtime/research/product/shenyang -maxdepth 2 -type f | sort

# 未引用判断（publishing 输出即证据）
cat runtime/research/product/<city>/sync-report.json   # tablesPresentButUnreferenced / figuresPresentButUnreferenced

# 前端请求与 legacy 载荷
grep -rn "api/research" frontend/src
grep -rn "public/research\|research/shenyang" frontend/src backend/app
du -sh frontend/public/research/shenyang

# 源目录对照
du -sh data/research data/research/shenyang
diff -rq data/research runtime/research
```

测量用「选中/未引用」口径：某源文件被 `publishing` 选中 = 它是 `A0X/article.json`，或它位于 `A0X/tables|figures/` 且文件名出现在对应 `article.json` 的 `tables[].file` / `figures[].file` 中，或它是 `sources/source_registry.csv`，或它是城市根 `references.md`。其余一律记为**未被选中**。

## 2. 体积分布（`runtime/research` 各一级项）

命令：`du -sh runtime/research/*` + `du -sk runtime/research`（总计 334844 KB）。

| 一级项 | 体积 | 占比 | 说明 |
|---|---:|---:|---|
| `shenyang/` | **320M** | ~97.8% | 单城研究源，绝大多数未进入产品 |
| `product/` | 3.3M | ~1.0% | 六城 + cross_city 的产品载荷（唯一被前端消费的部分） |
| `long_horizon/` | 940K | 0.3% | 未纳入 `CITY_ORDER`，整目录未发布 |
| `dalian/` | 916K | 0.3% | |
| `chaoyang/` | 832K | 0.2% | |
| `jinzhou/` | 796K | 0.2% | |
| `tieling/` | 284K | 0.1% | |
| `dandong/` | 276K | 0.1% | |
| `cross_city/` | 232K | 0.1% | |
| `research_catalog.json` | 40K | <0.1% | 由 `publishing` 生成的轻量总索引（产品件） |
| `README.md` | 4.0K | <0.1% | |
| **合计** | **327M** | 100% | `du -sh runtime/research` = 327M |

**最大的三项**：`shenyang/`（320M）、`product/`（3.3M）、`long_horizon/`（940K）。其中 `shenyang/` 的构成如下（`du -sh shenyang/*`）：

| shenyang 一级子路径 | 体积 | 文件数 |
|---|---:|---:|
| `case_studies/` | **261M** | 386 |
| `assets/` | **56M** | 274 |
| `scripts/` | 928K | 43 |
| `v1_reports/` | 248K | 21 |
| `results/` | 156K | 2 |
| `A01`–`A09`（模块目录合计） | 616K | 56 |
| `qa/` | 52K | 3 |
| `plan/` | 48K | 4 |
| `config/` | 32K | 4 |
| `references/` | 28K | 3 |
| `sources/` | 40K | 2 |
| `city_meta/` | 12K | 2 |
| `evidence/` | 8.0K | 1 |
| 根文件（`build_index.py` 等） | ~92K | 9 |
| `literature/` | 0B | 0 |

`case_studies/` 细分（`du -sh shenyang/case_studies/shenbei_2026_rainstorm_corn/*`）：
`02_raw` 129M、`03_clean` 35M、`05_analysis` 33M、`04_marts` 31M、`06_models` 27M、`08_figures` 2.8M、`01_sources` 2.3M、`scripts` 520K、`09_reports` 140K、`logs` 84K。

`assets/` 细分（`du -sh shenyang/assets/*`）：
`models` 23M、`outputs` 20M、`figures` 8.2M、`tables` 4.6M。

## 3. 真正进入产品链路的资产

`publishing` 对每个城市输出的产物固定为：`manifest.json`、`sources.json`、`sync-report.json`、`references.md`，以及 `articles/`、`tables/`、`figures/`。

命令：`du -sh runtime/research/product/*` + 各城市 `find <city> -type f | wc -l`。

| 城市 | `product/<city>` 体积 | 总文件数 | articles | tables | figures | 顶层生成件 |
|---|---:|---:|---:|---:|---:|---|
| shenyang | 512K | 37 | 9 | 22 | 2 | manifest/sources/sync-report/references |
| chaoyang | 732K | 46 | 9 | 24 | 9 | 同上 |
| jinzhou | 700K | 46 | 9 | 24 | 9 | 同上 |
| dalian | 828K | 46 | 9 | 24 | 9 | 同上 |
| dandong | 208K | 20 | 9 | 5 | 2 | 同上 |
| tieling | 232K | 19 | 9 | 4 | 2 | 同上 |
| cross_city | 128K | 12 | 2 | 5 | 1 | 同上 |
| **合计** | **3.3M** | **226** | 56 | 108 | 34 | — |

> 文件数校验：如 shenyang = 9 + 22 + 2 + 4 = 37；cross_city = 2 + 5 + 1 + 4 = 12。

**product 各文件来自源目录的哪些子路径**（依据 `publish_research.py`）：

| product 产物 | 源路径 | 复制方式 |
|---|---|---|
| `articles/<id>.json` | `<city>/A0X/article.json` | 逐字节原样复制（cross_city 另有 `cross_city/article.json` 与 `cross_city/synthesis/article.json`） |
| `tables/<file>` | `<city>/A0X/tables/<file>` | 仅复制 `article.json` 的 `tables[].file` 引用到的表 |
| `figures/<file>` | `<city>/A0X/figures/<file>` | 仅复制 `article.json` 的 `figures[].file` 引用到的图 |
| `sources.json` | `<city>/sources/source_registry.csv` | CSV → 固定键 JSON（**仅此一个 sources 文件被消费**） |
| `references.md` | `<city>/references.md` | 源存在则原样复制；否则据 registry 生成。**仅 shenyang 有源文件**，其余城市为生成 |
| `manifest.json` / `sync-report.json` | 无（脚本生成） | 由 `publish_research.py` 写出 |
| `research_catalog.json` | 无（脚本生成） | 六城 + cross_city 轻量总索引 |

只有 `article.json` 明确引用的 tables/figures 才被复制；`A0X/metrics/`、`A0X/report.md`、`A0X/review.md` 以及未被引用的表/图**不会**进入 `product/`（见 §4 与 `sync-report.json` 的 `tablesPresentButUnreferenced`）。

## 4. 未被产品链路引用的资产（真实 `find`/`du`，按源一级子路径）

### 4.1 shenyang（未引用约 319M，占 `runtime/research` 的 ~97%）

| 源一级子路径 | 体积 | 文件数 | 是否被 publishing 选中 |
|---|---:|---:|---|
| `shenyang/case_studies/` | **261M** | 386 | 否 |
| `shenyang/assets/` | **56M** | 274 | 否 |
| `shenyang/scripts/` | 928K | 43 | 否 |
| `shenyang/v1_reports/` | 248K | 21 | 否 |
| `shenyang/results/` | 156K | 2 | 否 |
| `shenyang/A0X` 未被引用部分 | ~160K | — | 否（含 `metrics/` ×9、`report.md` ×9、`review.md` ×8、未引用表/图） |
| `shenyang/qa/` | 52K | 3 | 否 |
| `shenyang/plan/` | 48K | 4 | 否 |
| `shenyang/config/` | 32K | 4 | 否 |
| `shenyang/references/` | 28K | 3 | 否（`METHOD_BENCHMARK.md` 等） |
| `shenyang/sources/references.bib` | 16K | 1 | 否（publishing 只读 `source_registry.csv`） |
| `shenyang/city_meta/` | 12K | 2 | 否 |
| `shenyang/evidence/` | 8.0K | 1 | 否 |
| 根文件（`build_index.py` 52K、`sources.json` 8K、`README.md` 8K、`00_研究总览.md` 8K、`run_district.py`/`run_all.py`/`requirements.txt`/`manifest.json` 各 4K） | ~92K | 9 | 否 |
| `shenyang/literature/` | 0B | 0 | 否（空目录） |

> A0X 明细：`A01`–`A09` 合计 616K，其中被选中约 456K（9 个 article.json + 22 个引用表 + 2 个引用图），未引用约 **160K**。
> shenyang 未被选中的表（`sync-report.json`）：`A01_trend.csv`、`A04_event_clusters.csv`、`A04_event_responses.csv`；未被选中的图：无。

### 4.2 其他城市（本体小，未引用主要为 A0X 辅助产物）

命令：`du -sh <city>/A0*/metrics`、`find <city> -name report.md`、`du -sh <city>/{city_meta,evidence,sources}`、`cat product/<city>/sync-report.json`。

| 城市 | 未引用合计 ≈ | 主要构成（真实测量） |
|---|---:|---|
| chaoyang | ~112K | `A0X/metrics/` 9 个（约 4K）、`report.md` ×9（44K）、未引用表 3 个（`A04_official_disaster.csv`、`A07_data_quality_note.csv`、`A07_total_area.csv`）、`city_meta/` 8K、`evidence/` 4K |
| jinzhou | ~108K | `metrics/` 9（4K）、`report.md` ×9（40K）、未引用表 3 个、`city_meta/` 8K、`evidence/` 4K |
| dalian | ~100K | `metrics/` 9（4K）、`report.md` ×9（44K）、未引用表 2 个（`A07_data_quality_note.csv`、`A07_total_area.csv`）、`city_meta/` 8K、`evidence/` 4K |
| dandong | ~92K | `metrics/` 9（4K）、`report.md` ×9（36K）、未引用表 2 个、`city_meta/` 8K、`evidence/` 4K |
| tieling | ~92K | `metrics/` 9（4K）、`report.md` ×9（36K）、未引用表 2 个、`city_meta/` 8K、`evidence/` 4K |
| cross_city | ~36K | `metrics/`（4K）、`plan/`（12K）、`report.md` 2 个（20K：`cross_city/report.md`、`cross_city/synthesis/report.md`） |

> 全部六城（除沈阳）共约 540K 未引用，量级可忽略。

### 4.3 整目录未发布

| 路径 | 体积 | 文件数 | 原因 |
|---|---:|---:|---|
| `runtime/research/long_horizon/` | 940K | 3 | 不在 `CITY_ORDER`（`shenyang,chaoyang,jinzhou,dalian,dandong,tieling,cross_city`），`publishing` 不处理 |
| `runtime/research/README.md` | 4.0K | 1 | 目录说明，非产品件（`product/` 未复制） |

### 4.4 汇总

| 口径 | 体积 | 文件数 |
|---|---:|---:|
| `runtime/research` 总计 | 327M | — |
| 被 `publishing` 选中（≈ `product/`） | 3.3M | 226 |
| **未被选中** | **≈ 324M** | — |

## 5. 与前端的关系

### 5.1 前端实际请求的路径模式

后端只读路由（`backend/app/routes/research.py`）与前端仓库（`frontend/src/domain/research/v2/repository.ts`）一致：

| 方法 | 路径 | 服务实现 | 前端调用点 |
|---|---|---|---|
| GET | `/api/research/catalog` | `research_service.catalog()` → `runtime/research/research_catalog.json` | `getCatalog()` |
| GET | `/api/research/cities` | `research_service.cities()` → 同上索引 | `cities()`（首页概览） |
| GET | `/api/research/<city>/manifest.json` | `product/<city>/manifest.json` | `getManifest(cityId)` |
| GET | `/api/research/<city>/sources.json` | `product/<city>/sources.json` | `getSources(cityId)` |
| GET | `/api/research/<city>/sync-report.json` | `product/<city>/sync-report.json` | `getSyncReport(cityId)` |
| GET | `/api/research/<city>/references.md` | `product/<city>/references.md` | `getReferences(cityId)` |
| GET | `/api/research/<city>/articles/<id>.json` | `product/<city>/articles/<id>.json` | `getArticle(cityId, id)` |
| GET | `/api/research/<city>/tables/<file>` | `product/<city>/tables/<file>` | `getTable()` / `assetUrl.table()` |
| GET | `/api/research/<city>/figures/<file>` | `product/<city>/figures/<file>` | `assetUrl.figure()` |

- **城市无关**：路径由 `cityId` 推导，`shenyang` 未被写死；前端不做路径拼接推断（`..`、绝对路径被后端白名单 `CITY_RE/ARTICLE_RE/FILE_RE` + `_inside(PRODUCT_ROOT, …)` 拦截）。
- 推演表走另一入口 `/scenario/<cityId>/<file>`，与 `/api/research/*` 分离（§30）。
- 后端**只读取 `product/`**：`RESEARCH_DIR = RUNTIME_DIR / "research"`、`PRODUCT_ROOT = RESEARCH_DIR / "product"`、`CATALOG_PATH = RESEARCH_DIR / "research_catalog.json"`。**源目录 `runtime/research/<city>/…` 的非 `product` 内容前端完全不会请求。**

### 5.2 legacy 前端载荷

`frontend/public/research/shenyang` 仅作 **legacy compatibility** 保留（`repository.ts` 注释 §4 已注明「不再是正式六城架构」）。

命令：`du -sh frontend/public/research/shenyang`、`find frontend/public/research -type f | wc -l`。

- 体积：**580K**，42 文件。
- 仅被 legacy 代码读取（`frontend/src/legacy/rainstorm-v1/`、`frontend/src/legacy/scenario-v1-ScenarioLabPage.tsx`、`frontend/src/legacy/research-v1/ResearchArticleView.tsx`），路径形如 `/research/shenyang/tables/*.csv`、`/research/shenyang/figures/*`。
- 一个测试引用了 `public/research/shenyang/articles/*.json`（`frontend/src/features/research-v2/markdown.test.tsx`）。
- 正式研究中心（V3）**不**经此路径，改由 `/api/research/*` 提供六城 + 跨城市。

## 6. 瘦身建议（**只写建议，本轮不执行**）

目标：在不损失任何前端功能的前提下，把 `runtime/research` 从 327M 降到约 5M 级。约束：**只改 `pipelines/publishing` 的 release selection，源目录 `data/research` 保持完整**。

### 6.1 最小动作（两选一）

**方案 A（推荐·零删除）**：仅调整 release selection 的「输入根」，让 `runtime/research` 只保留 `product/` 与 `research_catalog.json`，A0X 源与 `case_studies/assets` 等不进 runtime。

- 在 `publish_research.py` 的 `SOURCE_ROOT` 指向 `data/research`（源目录，完整保留），`OUT_ROOT` 仍写 `runtime/research/product`。
- 即：runtime 只落地「产品件 + 索引」，研究源全量保留在根 `data/research`。
- 这样无需删除任何历史文件即可让 runtime 名义体积回落到约 5M。

**方案 B（在 runtime 内裁剪）**：保持 `SOURCE_ROOT=runtime/research`，但把下述「建议不进入 runtime」的路径从 runtime 移出（移动/归档到 `data/research` 或独立归档目录），runtime 仅保留 `product/` + `research_catalog.json` + 各城市 `A0X` 的 `article.json/tables/figures/sources`。

- 本方案会产生移动操作，**需另行批准**；本轮不执行。

### 6.2 建议保留 / 建议不进入 runtime 的路径清单

**建议保留（runtime 必需，约 5M）**：

| 路径 | 体积 | 理由 |
|---|---:|---|
| `product/`（六城 + cross_city） | 3.3M | 后端 `/api/research/*` 唯一读取根 |
| `research_catalog.json` | 40K | `/api/research/catalog`、`/cities` |
| `README.md` | 4.0K | 目录说明（可选） |
| 各城 `A0X/article.json`、被引用的 `A0X/tables|figures/*`、`sources/source_registry.csv`、`shenyang/references.md` | ~3M（源侧） | 供 `publishing` 复算/幂等重建；若不重跑 publishing 可一并省略 |

**建议不进入 runtime（未引用，约 324M）**：

| 路径 | 体积 | 影响面 |
|---|---:|---|
| `shenyang/case_studies/` | 261M | 无前端消费；`A04` 案例研究文章引用的是 `case_studies` 产出的**表**，而这些表已固化在 `A04/tables/`，文章不直读 `case_studies/` 原始数据 |
| `shenyang/assets/` | 56M | 无 `/api/research/*` 消费；非产品件 |
| `shenyang/scripts/`、`v1_reports/`、`results/`、`qa/`、`plan/`、`config/`、`references/`、`city_meta/`、`evidence/`、`literature/`、根脚本与 `sources.json` | ~1.9M | 研发/过程产物 |
| `long_horizon/` | 940K | 未纳入发布城市 |
| 各城 `A0X/metrics/`、`A0X/report.md`、`A0X/review.md`、未引用的 `A0X/tables|figures/*` | ~0.7M | `publishing` 不复制（`sync-report.json` 明确列为 present-but-unreferenced） |
| 各城 `sources/references.bib` | 16K | `publishing` 只读 `source_registry.csv` |
| 各城 `city_meta/`、`evidence/`、`cross_city/{metrics,plan,report.md,synthesis/report.md}` | <100K | 非产品件 |

### 6.3 风险与「不退化」验证

**受影响面（需重点核验）**：

1. **`A04`（极端天气案例）等文章正文**：正文中若以相对路径引用图片，而图片位于被裁掉的 `assets/figures` 或 `case_studies/08_figures`，裁剪后可能 404。→ 需先确认这些图是否已复制进 `product/<city>/figures/`（本轮 `product/shenyang/figures` 只有 2 张：`A01_seasonal_amplitude.png`、`A07_district_structure.png`，说明文章并未引用 `assets` 图）。
2. **`/api/research/<city>/figures/<file>` 与 `/tables/<file>`**：只要 `product/` 不变即不受影响——裁剪源目录不改变 `product/`。
3. **`publish_research.py` 幂等复算**：若改 `SOURCE_ROOT` 指向 `data/research`（方案 A），需确认源目录结构与 runtime 一致（`diff -rq data/research runtime/research` 显示二者**仅差** `product/` 与 `research_catalog.json`，结构一致，改根安全）。
4. **legacy 路径 `/research/shenyang/*`**：由 `frontend/public`（580K）提供，与 `runtime/research` 无关，裁剪 runtime 不动它。

**验证不退化（建议步骤，均只读）**：

```bash
# 1) 发布前后 product 完全一致（内容哈希）
diff -rq <old_product> <new_product>
# 2) 逐接口冒烟：catalog + 七城 manifest/sources/sync-report/references + 任取 article/table/figure
curl -s localhost:<port>/api/research/catalog | head
for c in shenyang chaoyang jinzhou dalian dandong tieling cross_city; do
  curl -s localhost:<port>/api/research/$c/manifest.json >/dev/null && echo "$c OK"
done
# 3) 前端研究中心端到端：首页（catalog/cities）→ 城市 → 文章 → 表/图 → About(references)
# 4) 后端测试：pytest backend（研究只读路由相关用例）
```

## 7. 结论

- 本轮为**只读统计 + 报告**，**未删除任何文件**，`git` 未做任何操作。
- `runtime/research` 实测体积 **327M**（`du -sk` = 334844 KB）；源目录 `data/research` 实测 **324M**，两者仅差 `product/`（3.3M）与 `research_catalog.json`。
- 体积几乎全部（约 324M / 99%）为**未被产品链路引用**的研究过程资产，且 >97% 集中在 `shenyang/case_studies/`（261M）与 `shenyang/assets/`（56M）。
- 真正进入产品链路的仅 `product/` **3.3M**（226 文件）。
- 瘦身可在**只改 `pipelines/publishing` 的 release selection、根 `data/research` 保持完整**的前提下完成（见 §6 方案 A/B），风险可控且可验证。