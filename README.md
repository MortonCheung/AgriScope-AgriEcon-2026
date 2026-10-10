# AgriScope · 辽宁省农业经济建模研究资产（2026 第七届）

本仓库是 **2026 年第七届辽宁省大学生农业经济建模大赛** 相关研究资产的**只读归档与研究索引库**。
它由 `农业建模` 本地工作区经许可与敏感信息审核后，自动导出并发布为**私有（Private）仓库**，
供后续通过 GitHub 连接器进行选题论证、研究结论审查、建模验证与论文写作。

- 上游原始工作区：`/Users/morton_cheung/Desktop/比赛/农业建模`（`source_snapshot/`，只读）
- 源项目目录：`/Users/morton_cheung/Desktop/比赛/大数据分析`
- 本仓库**不是**原公开仓库 `MortonCheung/AgriScope`，二者相互独立、互不影响。

> ⚠️ **重要声明**
> 1. 本仓库中的研究报告为**阶段性研究成果**，其中部分结论在源项目内部已被**部分推翻或降级**（见
>    `models/reports/final/FINAL_ANSWERS.md` 第 25 条）。请勿把任何报告默认标注为"已复现"或"科学结论已验证"。
> 2. **复现状态**：数据链路与依赖齐备，但**本工作区未执行任何重训/重算**，因此一律登记为
>    `依赖齐备·未复算（NOT RE-RUN）`，不得声称"已复现"。
> 3. 本仓库含**数据分发限制**，详见 [`DATA_DISTRIBUTION_LIMITATIONS.md`](DATA_DISTRIBUTION_LIMITATIONS.md)。
>    受限第三方原始数据（政府/新闻网页、商业平台价格、统计年鉴原件 PDF、第三方栅格）**未上传**，
>    仅在本地保留并通过来源登记清单索引其位置。

---

## 1. 从这里开始

| 入口 | 用途 |
|---|---|
| [`RESEARCH_INDEX.md`](RESEARCH_INDEX.md) | **完整研究索引**：六城 × A01–A09、模型、程序、数据、来源逐项登记 |
| [`DATA_DISTRIBUTION_LIMITATIONS.md`](DATA_DISTRIBUTION_LIMITATIONS.md) | 数据分发限制、未上传清单与原因 |
| [`audit/MIGRATION_REPORT.md`](audit/MIGRATION_REPORT.md) | 源工作区迁移与校验报告（上游事实基线） |
| [`audit/UPLOAD_MANIFEST.csv`](audit/UPLOAD_MANIFEST.csv) | 本次上传文件逐条清单（含 SHA256 与源路径） |
| [`audit/EXCLUDED_FILES.csv`](audit/EXCLUDED_FILES.csv) | 未上传文件清单与排除原因 |
| [`models/reports/final/`](models/reports/final/) | 正式模型研究报告（HRI/价格/风险/优化/回测/稳健性/失败实验） |
| [`research/`](research/) | 六城专题研究与沈北暴雨玉米案例研究 |
| [`data/SCHEMA/PARQUET_SCHEMA.md`](data/SCHEMA/PARQUET_SCHEMA.md) | Parquet 结构登记（字段、类型、行数） |

---

## 2. 目录结构

```text
.
├── README.md                      # 本文件
├── RESEARCH_INDEX.md              # 研究总索引（核心检索入口）
├── DATA_DISTRIBUTION_LIMITATIONS.md
├── audit/                         # 迁移审计 + 上传/排除清单
├── research/                      # 六城 A01–A09 + cross_city + 沈北案例
├── models/                        # 正式模型报告、指标表、模型注册表
├── pipelines/                     # 研究/建模/数据基础/长周期/日度 计算程序
├── docs/                          # AgriScope 项目文档与总报告
├── code/                          # LLM 评测、脚本与测试代码
└── data/
    ├── model_ready/               # 正式模型输入（19 张冻结表 + 特征）
    ├── processed/                 # 清洗/标准化后的研究数据
    ├── metadata/                  # 治理、证据、质量、模型清单、库存
    ├── source_registry/           # 原始来源登记（data/raw 元数据与说明）
    └── SCHEMA/                    # 自动生成的 Parquet 结构登记
```

---

## 3. 研究版图（速览）

- **六城专题研究**：沈阳、朝阳、锦州、大连、丹东、铁岭 × **A01–A09** = **54 个专题单元**，
  每个单元含 `report.md`、`article.json`、`tables/`、`metrics/`、`figures/`（部分城市含 `review.md`）。
- **跨城市综合**：`research/cross_city/`（含 `synthesis/`）。
- **沈阳 v1 历史专题**：`research/shenyang/v1_reports/`（01–17 + 里程碑/局限/阻断项）。
- **案例研究**：`research/shenyang/case_studies/shenbei_2026_rainstorm_corn/`
  （沈北 2026 暴雨玉米，M1–M4 模型、反事实、稳定性制图、四阶段研究报告，05_analysis 结果表与图）。
- **正式模型研究**：`models/reports/final/`（HRI 验证、价格模型、风险模型、推荐与优化、利润、回测、
  稳健性、消融、失败实验、政策与未触碰期），`models/registry/` 注册表。
- **计算程序**：`pipelines/research/`（A01–A09 模块）、`pipelines/modeling/`（决策引擎源码与测试）、
  `pipelines/data_foundation/`（采集/解析/标准化/治理）、`pipelines/daily/`、`pipelines/long_horizon/`。

---

## 4. 如何使用（面向 ChatGPT 研究审查）

1. 先读 [`RESEARCH_INDEX.md`](RESEARCH_INDEX.md) 建立全局定位。
2. 读 [`models/reports/final/FINAL_ANSWERS.md`](models/reports/final/FINAL_ANSWERS.md) 了解模型层最终口径与**已知被推翻的结论**。
3. 做选题论证时，读对应城市 `research/<city>/A0x/report.md` 与其 `tables/`、`metrics/`。
4. 做建模验证时，对照 `models/reports/final/` 报告 + `data/model_ready/` 输入 + `pipelines/modeling/` 源码。
5. 需要核验来源时，读 `research/<city>/sources/source_registry.csv`、
   `data/source_registry/metadata/source_registry.csv`、`data/metadata/evidence/`。
6. 遇到 Parquet 不便直读时，先查 [`data/SCHEMA/PARQUET_SCHEMA.md`](data/SCHEMA/PARQUET_SCHEMA.md)。

## 5. 边界与诚信约束

- 全仓库为**只读研究归档**：不训练、不抓取、不重构、不改写原始数据。
- 已剔除：`.env`/密钥/Token/凭据、浏览器日志与缓存、大型模型权重、受限第三方 PDF/网页/商业价格数据。
- 所有"未上传"项均登记于 [`audit/EXCLUDED_FILES.csv`](audit/EXCLUDED_FILES.csv)，不做隐瞒。
