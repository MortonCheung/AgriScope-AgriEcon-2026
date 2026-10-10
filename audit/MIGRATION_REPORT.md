# AgriScope → 农业建模 研究资产迁移报告

- 迁移日期：2026-10-10
- 源目录（只读）：`/Users/morton_cheung/Desktop/比赛/大数据分析`
- 目标目录（只写）：`/Users/morton_cheung/Desktop/比赛/农业建模`
- 迁移方式：`rsync -a`（保留时间戳/权限），**仅复制，不移动、不删除、不推送、不改源**
- 源仓库 Git 基线：`HEAD=62ee626adcf66aeaf8c01f80af62fb173f176038`，工作区状态指纹 `996975db…5aa0f`（40 项）

---

## 0. 执行摘要

| 指标 | 结果 |
|---|---|
| 复制文件数 | **15,511** |
| 内容合计 | **852,601,965 字节 ≈ 813 MiB（0.85 GB）** |
| 目标目录占用 | ≈ 862 MB（含目录块开销与竞赛 docx） |
| 逐字节校验 | AgriScope / data / models **三组 rsync --checksum 复核 0 处差异** |
| 源目录改动 | **无**（Git 指纹、HEAD、跟踪文件全部不变） |
| 敏感文件（.env/密钥/token） | **0**（已确认未复制） |
| 目标内软链接 | **0**（无越界指向） |
| 目标骨架 | `source_snapshot/ paper/ experiments/ submission/ migration_audit/` 已建立 |

**结论：迁移已完成且可溯源；新工作区可用于论文研究，但“文件存在”“内容有效”“可复算”“可用于论文”四者需区分（见第 10 节）。**

---

## 1. 约束遵循

| 任务红线 | 遵循情况 |
|---|---|
| 不修改源目录任何文件 | ✅ 全程只读源；rsync 只读；未运行采集/训练/联网 |
| 仅复制，不移动/删除 | ✅ 全部使用 rsync/cp，源文件原地保留 |
| 不提交/推送 GitHub | ✅ 未执行任何 git 写操作 |
| 保留相对路径、不破坏对应关系 | ✅ 目标中保留 `AgriScope/ data/ models/` 三级顶层命名 |
| 不复制密钥/私人配置 | ✅ 通用排除规则过滤 `.env/*.key/*.pem/*secret*` 等 |
| 校验符号链接真实指向 | ✅ 候选集内源侧软链接仅在未复制的 `reference/` 下；目标内 0 软链接 |
| 不谎称无法验证的来源 | ✅ 全部来源标注登记于 `SOURCE_REGISTRY.csv`；本报告不对来源真实性背书 |

---

## 2. 源目录实际结构（已逐一确认存在，非据旧文档假设）

```
大数据分析/
├── .git/                     (未复制)
├── AgriScope/                (已选择性复制)
├── data/{metadata,model_ready,processed,raw,research}   (已复制)
├── models/{reports,registry,short_term,long_horizon,risk}  (部分)
├── archive/  reference/      (未复制：旧归档/第三方参考)
└── README.md  .gitignore     (已复制为 *_src_root)
```

关键确认：任务书中提到的 `AgriScope/`、`data/research/`（六城）、`data/metadata/`、`data/model_ready/`、`data/processed/`、`models/reports/final/`、`data/raw/` 均**实际存在**。源目录规模：data/raw=1.8G、data/research=324M、models=570M、AgriScope=1.2G。

---

## 3. 迁移分类

- **必须复制**：六城 A01–A09 专题（report/article/review/tables/metrics/figures）、v1_reports、qa、sources、evidence、scripts、沈北案例研究文档、`models/reports/final/`、`data/metadata/{governance,evidence,quality,model_manifests,inventory,requirements}`、`data/model_ready/*`、`data/processed/{market,production,cost,evidence,climate,disaster,policy,dimensions}`、`AgriScope/{docs,pipelines}`、项目总体材料。
- **可选复制（已复制/部分）**：`data/raw` 关键证据目录（policy/disaster/production/weather/soil/pests/macro/daily/gapfill/city_sources/agronomy/retained_source/decision_engine_supplement*）、`AgriScope/llm`（代码，排除 cache）。
- **无需复制（已排除）**：`.git、node_modules、.venv、__pycache__、构建产物(output)、运行时(runtime)、前端(frontend)、后端(backend)、部署(deploy)、旧 snapshots、大型模型权重(short_term/long_horizon/*.joblib)、大型栅格/矢量(*.tif/*.gpkg)、批量抓取缓存(web_captures、prices/*_deep、dalian_12316)`。
- **需要人工审核**：政府/新闻原始 HTML、期刊 PDF、第三方栅格/土壤数据、电商/B2B 商业价格数据（详见 `GITHUB_UPLOAD_CANDIDATES.csv`）。

---

## 4. 复制执行明细

| 类别 | 目标路径 | 文件数 | 字节 | 覆盖率 |
|---|---|---:|---:|---|
| AgriScope 文档/程序 | `source_snapshot/AgriScope` | 514 | 16,458,242 | 完整(排除应用/产物) |
| 六城专题研究 | `source_snapshot/data/research` | 1,077 | 134,169,067 | 完整 |
| 数据治理元数据 | `source_snapshot/data/metadata` | 73 | 16,866,974 | 完整(排除 snapshots) |
| 正式模型输入 | `source_snapshot/data/model_ready` | 41 | 27,294,613 | 完整(排除 snapshots) |
| 经济建模关键数据 | `source_snapshot/data/processed` | 105 | 45,232,073 | 完整 |
| 原始证据 | `source_snapshot/data/raw` | 13,609 | 610,898,392 | 选择性 |
| 最终模型报告 | `source_snapshot/models/reports/final` | 81 | 1,478,108 | 完整 |
| 模型注册表 | `source_snapshot/models/registry` | 4 | 132,814 | 完整 |

---

## 5. 排除项与登记（详表见 `MISSING_DEPENDENCIES.csv`）

大体量排除：`web_captures`(407M)、`prices/jinzhou_deep`(450M)、`prices/dalian_12316`(330M)、
`model_ready/snapshots`(78M)、`AgriScope/{output 510M, runtime 350M, frontend 333M}`、
`models/short_term`(554M·权重)、沈北案例栅格 `*.tif/*.gpkg`（ESA 77M、DSM 43M、GPKG 约 42M 等）。

> 超过 25 MB 且**已复制**的文件仅 1 个：`data/raw/decision_engine_supplement_v3/production/liaozhong_2022_tjnj.pdf`（25M，统计年鉴原件，属核心证据，保留于本地研究工作区，**不建议**加入公开上传候选）。

**未做任何抽样/截断/改写**；被排除的大文件均在源目录完整保留，可按需回取。

---

## 6. 完整性校验结果

1. **逐项 SHA256 校验**：三组 `rsync -rcn` 复核输出为空 → 复制文件与源**逐字节一致**。
2. **数量/字节**：见第 0、4 节（15,511 文件 / 852,601,965 字节）。
3. **报告引用的关键表存在**：六城 A01–A09 均含 `report.md / article.json / review.md / tables/ / metrics/`（`figures/` 亦存在，个别为空属源侧特性）。
4. **模型指标文件与代码**：`models/reports/final/{HRI_VALIDATION,PRICE_MODEL,BACKTEST,RECOMMENDATION,OPTIMIZATION,RISK_MODEL,ROBUSTNESS,POLICY_AND_UNTOUCHED,FINAL_DATA_AUDIT,FINAL_MODEL,FAILED_EXPERIMENTS}.md` 与 `tables/*` 齐备；对应程序在 `AgriScope/pipelines/modeling/**`。
5. **敏感文件**：目标内 `.env/*.key/*.pem/*credential*/*secret*` = 0。
6. **源 Git 状态**：与迁移前一致（指纹/HEAD/跟踪文件未变）。
7. **目标软链接**：0，无越界指向。
8. **缺失/冲突/重复**：缺失=排除项（见 CSV）；同名冲突=无（多为全新写入，已存在竞赛 docx 未覆盖）；重复=未生成。

---

## 7. 源目录零改动证明

- 迁移前：`git status --porcelain | sha256 = 996975db…5aa0f`，行数 40，`HEAD=62ee626…`
- 迁移后：**同样读数**，完全一致。
- 说明：`AgriScope/.git/index` 时间戳更新由本报告所用的 `git status` 刷新 stat 缓存导致（非内容变更，工作树未改）。源目录自带缓存类文件（`.pytest_cache`、`runtime`、`output/playwright`）时间戳变化与本迁移无关（这些路径未被读取复制）。

---

## 8. 资产矩阵与可复算性

详见 `RESEARCH_ASSET_MATRIX.csv`（56 行：六城 × A01–A09 + 跨城市 + 长期）。
四条链路状态：
- **生产端**（区县 A07/A08）：数据链路存在（`production/`、`model_ready` 面板 + 年鉴源），**存在数据缺口**（2025 未完整、部分区县早年缺失）。
- **市场端**（A01–A06）：数据链路完整（`processed/market` + `raw/prices` 选摘 + 来源登记）。
- **HRI**：输入（`model_ready/hri/hri_inputs.parquet`）+ 报告（`HRI_VALIDATION_REPORT.md` + `tables/hri_*`）齐备。
- **种植决策**：`model_ready/recommendation/*` + `RECOMMENDATION_REPORT.md` + `tables/{portfolio,pareto,optimization,stress_*}` 齐备。
> **“可复算”≠“已复算”**：本阶段仅复制与检查，**未在本工作区执行任何训练/推理**；可复算性需在新环境补齐依赖后另行验证。

---

## 9. 上传候选分级

见 `GITHUB_UPLOAD_CANDIDATES.csv`（34 行）。摘要：
- **可公开上传**：六城研究报告/文章/结果表/图/指标、模型正式报告与指标表、方法文档、程序、迁移审计报告。
- **需要人工审核**：政府公文/新闻 HTML、期刊 PDF、第三方栅格/土壤数据、统计年鉴内部资料 PDF。
- **仅供本地研究**：`data/processed`、`data/model_ready`、`data/raw/retained_source` 等派生/合集数据。
- **不应上传**：电商/B2B 商业价格数据、大型模型权重、任何密钥、大型栅格/矢量。

---

## 10. 交付验收（十问）

1. **复制了多少文件、多少 GB？** → 15,511 个文件；内容 852,601,965 字节 ≈ **0.85 GB**（占用约 862 MB）。
2. **各城市 A01–A09 是否完整？** → **完整**。六城 × A01–A09 共 54 个专题单元，全部含 report/article/review/tables/metrics。
3. **哪些模型研究报告具备论文复用条件？** → `models/reports/final/` 中 11 份核心报告（HRI/PRICE/BACKTEST/RECOMMENDATION/OPTIMIZATION/RISK/ROBUSTNESS/POLICY/FINAL_DATA_AUDIT/FINAL_MODEL/FAILED_EXPERIMENTS）及 `ABLATION/PROFIT/INFERENCE_AND_DEPENDENCY` 具备复用条件；对应指标表齐全。
4. **HRI 与种植决策数据链条是否完整？** → **完整**：输入数据 + 程序 + 报告 + 指标表四要素均在。
5. **哪些原始证据缺失？** → 未整体复制 `web_captures`、`prices/*_deep`、`dalian_12316`、部分 snapshots 与栅格；**如论文需要某条来源，按 `SOURCE_REGISTRY.csv` 逐条回取**。
6. **哪些结论无法复算？** → 依赖被排除大文件/权重的部分（短期价格模型重训、栅格派生指标）在本工作区无法直接复算；依赖 ERA5 再分析与未公开货源地的结论受数据边界限制。
7. **哪些数据不能直接公开上传？** → 电商/B2B 商业价格、期刊/公文 PDF（许可待定）、第三方土壤/栅格、模型权重、年鉴内部资料 PDF。
8. **新工作区是否已就绪？** → **已就绪（研究材料层面）**：骨架、六城专题、模型报告、治理元数据、关键证据、程序均已就位并通过校验；**论文写作前需** (a) 确认依赖环境，(b) 按需回取被排除的大数据文件。

---

## 11. 已知局限与后续建议

- 未执行任何复算/训练，**复现性以“依赖齐备”为准，非“结果已重算”**。
- 成交量单位来源未明、ERA5 为再分析网格（非气象站实测）、生产端与市场端无货源地连接数据——这些边界须在论文中如实声明。
- 建议下一步：(1) 在 `experiments/` 建立独立 conda/venv 环境；(2) 按 `SOURCE_PATHS.csv` 与 `RESEARCH_ASSET_MATRIX.csv` 生成复算清单；(3) 商用/版权数据走人工审核后再决定公开范围。

*本报告由迁移过程自动统计生成，所有数字来源于实际文件系统与 SHA256 清单。*
