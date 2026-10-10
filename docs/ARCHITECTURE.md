# AgriScope 架构与运行时

本文说明 AgriScope 的**产品结构**、**研发态 → 发布态的数据流**，以及 `runtime/` 与 `pipelines/publishing/` 的约定。
（运行命令见根 `README.md`；端点清单见 `docs/API.md`。）

## 1. 产品结构（前端）

产品面向辽宁农业市场与种植决策，一级导航收敛为三条主线（`frontend/src/app/navItems.ts`）：

| 模块 | 入口 | 主要特性目录 |
|---|---|---|
| 辽宁农业态势（看现在） | `/liaoning` | `features/liaoning`（3D 沙盘、省域主题） |
| 决策中心（帮判断） | `/decision`、`/cities/:cityId/decision`、`/scenario-lab` | `features/decision`、`features/scenario`、`features/longHorizon`、`features/evidence` |
| 研究中心（证明依据） | `/research`、`/reports`、`/cities/:cityId/research/:researchId`、`/about` | `features/research-center`、`features/research-v2`、`features/cross-city`、`features/report`、`features/evidence` |

前端分层：`app/`（路由、外壳、全局上下文）、`features/`（业务特性）、`domain/`（领域模型与目录）、
`providers/`（决策数据源：正式 HTTP / fixture / mock）、`design/`（设计令牌）、`services/`（IO 与缓存）、
`performance/`（DPR / 画质档）。讲解模式在 `features/presentation`，证据抽屉在 `features/evidence`。

> `src/legacy/` 已在 V3 收口时整体删除（`frontend/docs/ITEACH_MIGRATION_MATRIX.md` 记录依据）。

## 2. 三层与运行时边界

```
frontend/  (React 19 + Vite)  ──/api──▶  backend/  (FastAPI, 单 worker, :8787)
                                              │  只读
                                              ▼
                                          runtime/    ◀── pipelines/publishing/  ◀── monorepo 根 data/ + models/
                                          (产品运行时快照)
```

- `backend/` 是唯一后端。启动时（lifespan）**一次性绑定**运行时快照，之后请求级只读；推理有锁，保持单 worker。
  因此 Daily 更新数据后需重启后端以重新绑定。
- 产品只读 `runtime/`。研发态的完整数据/模型仓库在 **monorepo 根**（`AgriScope/` 的上一级）的 `data/` 与 `models/`，
  产品仓不直接依赖，使 `AgriScope` 可脱离外层开发仓运行。

## 3. 研发态 → 发布态数据流

- **研发态**：monorepo 根 `data/`、`models/` 是唯一完整仓库；`data/research/` 保存六城与跨城市研究的完整原始产物。
- **发布态**：`pipelines/publishing/` 挑选产品运行真正需要的最小集合写入 `AgriScope/runtime/`，并生成
  `runtime/manifest.json`。两条脚本职责不同、**互不覆盖**，**先 research 后 runtime**：

  1. `publish_research.py` —— 从根 `data/research` 按选择发布到 `runtime/research/product/<city>/`
     （`manifest.json`、`articles/*.json`、`sources.json`、`tables/`、`figures/`、`sync-report.json`、
     `references.md`）与轻量总索引 `runtime/research/research_catalog.json`。只保留「产品件」，不留原始副本。
  2. `publish_runtime.py` —— 从根 `data/`、`models/` 发布模型、Daily、长期快照与 LLM 评估证据到 `runtime/`，
     并写出 `runtime/manifest.json`（含对第 1 步研究发布项的登记）。

  两条脚本都幂等、只复制不删除源。`publish_runtime.py` 会依据 `runtime/research/product/` 与
  `research_catalog.json` 是否存在，把研究项状态标为 `PUBLISHED(research-product)`，否则标
  `SKIP(missing-research-product)` —— 所以第 1 步必须先跑。

## 4. `runtime/manifest.json` 的 20 个发布项

结构：`{ generated_at, publisher, note, assets: [{ source, destination, description, status }] }`，
`source` 以 monorepo 根为基准，`destination` 以 `AgriScope/` 为基准。

| # | source → destination | 说明 |
|---|---|---|
| 1 | `pipelines/modeling/src` → `runtime/models/src` | decision_engine 推理库源码 |
| 2 | `pipelines/modeling/config` → `runtime/models/config` | 模型配置 yaml |
| 3 | `models/short_term/final` → `runtime/models/models/final` | 短期冻结模型 pkl |
| 4 | `data/model_ready/snapshots/final_v1` → `runtime/models/data/snapshots/final_v1` | 冻结算法的输入快照 |
| 5 | `data/model_ready/snapshots/v1` → `runtime/models/data/snapshots/v1` | 开发期城市数据快照 v1 |
| 6 | `data/model_ready/snapshots/v2` → `runtime/models/data/snapshots/v2` | 开发期城市数据快照 v2 |
| 7 | `data/processed/decision_dataset` → `runtime/models/data/processed` | 决策数据集（模型层输入） |
| 8 | `data/model_ready/features` → `runtime/models/data/features` | 模型特征 |
| 9 | `data/metadata/model_manifests/final` → `runtime/models/data/manifests/final` | 模型输入清单 |
| 10 | `models/reports/final` → `runtime/models/reports/final` | 冻结模型身份报告 |
| 11 | `models/registry` → `runtime/models/models/registry` | 模型注册表 |
| 12 | `data/model_ready` → `runtime/data/model_ready` | model_ready 运行时子集 |
| 13 | `data/metadata` → `runtime/data/metadata` | 治理元数据（含 governance） |
| 14 | `data/processed/daily` → `runtime/data/processed/daily` | Daily 冻结产物 |
| 15 | `data/processed/long_horizon` → `runtime/data/processed/long_horizon` | 长期预测只读快照 |
| 16 | `models/registry/LONG_HORIZON_V2_REGISTRY.csv` → `runtime/LONG_HORIZON_V2_REGISTRY.csv` | 长期模型注册表 |
| 17 | `llm/artifacts/v2/real_evaluation_status.json` → `runtime/llm/artifacts/v2/…` | LLM 回溯评估状态（机器可读） |
| 18 | `llm/artifacts/v2/outcome_labels.json` → `runtime/llm/artifacts/v2/…` | LLM / Hybrid 结论标签 |
| 19 | `llm/artifacts/v2/fair_comparison.csv` → `runtime/llm/artifacts/v2/…` | 公平对比表（逐组 WAPE 与增益） |
| 20 | `data/research` → `runtime/research` | 六城与跨城市研究产品载荷（由 `publish_research.py` 落地） |

第 1–19 项 source 中的 `pipelines/…`、`llm/…` 位于 `AgriScope/` 内，其余位于 monorepo 根。
`runtime/models/evaluation/final/` 由发布脚本确保存在（推理库 `ensure_final_dirs` 要求该目录存在）。

## 5. 研究资产如何进入产品

1. 研究侧在根 `data/research/<city>/` 产出模块 `article.json`、`sources/`、表与图；
2. `publish_research.py` 转成前端契约（`runtime/research/product/` + `research_catalog.json`）；
3. 后端 `backend/app/routes/research.py` 以**路径白名单**方式只读暴露（`/api/research/*`）；
4. 前端 `features/research-center`、`features/research-v2`、`features/cross-city` 消费这些只读产物；
   研究点状态 `ready` / `pending` / `unsupported` 由研究侧导出，前端不推测、不软化。

## 6. 科学边界落点

`RESEARCH_ONLY`（LLM / Hybrid）、`final_effective_n=0`（reused retrospective）、`EXPLORATORY_SCENARIO_ONLY`
（150 / 180 天）、`NOT_SUPPORTED`（最优销售路径）、HRI（跟风风险环境，非农户行为概率）、
`WAPE ≠ 准确率` —— 这些边界声明贯穿研究契约、后端响应字段与前端文案，**不得弱化**。详见根 `README.md`
「科学边界」一节与 `docs/models/MODEL_LIMITATIONS.md`。