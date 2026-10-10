# 数据分发限制与未上传清单

本文件说明本仓库的**数据使用边界**：哪些内容已上传、哪些**因许可/隐私/体积原因未上传**，以及未上传内容在本地工作区的位置。
所有未上传项逐条登记于 [`EXCLUDED_FILES.csv`](EXCLUDED_FILES.csv)（含来源路径、字节数、排除原因），不做隐瞒。

---

## 1. 总量对照

| 指标 | 数量 |
|---|---:|
| 源工作区 `source_snapshot/` 文件总数 | 15,508 |
| 源工作区合计大小 | 852,541,195 字节 ≈ 813 MiB |
| **源自快照的上传文件数** | **1,755** |
| **源自快照的上传大小** | **225,583,896 字节 ≈ 215.1 MiB** |
| 本仓库文件总数（含自动生成文档） | 1,769 |
| 本仓库总大小 | 230,205,703 字节 ≈ 219.5 MiB |
| 未上传文件数 | 13,753 |
| 未上传大小 | 626,957,299 字节 ≈ 598 MiB |

> 上传清单见 [`UPLOAD_MANIFEST.csv`](UPLOAD_MANIFEST.csv)（逐条含 SHA256，可与源文件逐字节比对）。

---

## 2. 未上传原因分类

| 排除原因 | 文件数 | 大小 | 说明 |
|---|---:|---:|---|
| `government_or_news_html_license_unaudited` | 6,359 | 295.0 MB | 政府公文/新闻原始 HTML，**转载与二次分发许可未核实** |
| `raw_third_party_source_local_offline` | 7,188 | 235.6 MB | `data/raw/` 其余原始第三方资料（年鉴原件、批量抓取缓存等） |
| `third_party_pdf_license_unaudited` | 26 | 46.0 MB | 第三方 PDF（期刊/统计年鉴/保险条款等），**版权归属未确认** |
| `casestudy_raw_third_party` | 36 | 8.8 MB | 案例研究 `01_sources/official/`、`02_raw/`、`_pdfpages` 内的第三方原始件 |
| `archive_zip` | 3 | 8.3 MB | 压缩包（体量不适直读） |
| `model_weight_or_binary` | 53 | 3.3 MB | `*.npz`/`*.joblib` 等模型权重或二进制产物 |
| `browser_log/cache/__pycache__` | 34 | 0.5 MB | 浏览器日志、缓存、`__pycache__` |
| `runtime_log_or_snapshot` | 7 | 0.2 MB | 日度运行日志与旧快照 |
| `runtime_log` | 44 | 0.2 MB | 运行日志 |
| `compiled_binary` | 1 | 0.1 MB | 编译产物 |
| `root_level_source_metadata_not_uploaded` | 2 | 0.0 MB | 源根目录非研究性元数据（`README_src_root.md`、`gitignore_src_root.txt`） |

**特别说明（商业数据）**：源工作区内 `data/raw/prices/{ecommerce,b2b,hnwb}` 等**电商/B2B/商户平台价格数据**
属于**付费或商业平台原始资料，无再分发许可**，一律未上传（含于上表 `raw_third_party_source_local_offline`）。
本仓库**不含任何来源不明或受限的第三方原始商业数据**。

---

## 3. 已上传的派生数据说明

以下目录为**研究派生/聚合数据**，随研究结论一并上传以支撑审查与有限复算，但其**原始来源为受限数据**，
故仅用于**本次比赛研究内部**，不得对外再分发：

| 目录 | 内容 | 边界 |
|---|---|---|
| `data/model_ready/` | 正式模型输入的冻结表（19 张 + 特征） | 由上游来源聚合派生；命名含中文城市（如 `regional_朝阳.parquet`） |
| `data/processed/` | 清洗/标准化/集成后的研究数据 | 含价格、生产、成本、气象、灾害、政策等聚合表 |
| `data/metadata/` | 治理、证据、质量、模型清单、库存 | 来源登记与质量审计元数据 |
| `data/source_registry/` | `data/raw/` 的来源登记（`metadata/`）与各目录说明 | **仅登记位置，不含受限原始内容** |
| `research/**/case_studies/**` 结果 | 案例研究的分析结果表与图 | 原始件（`01_sources/`、`02_raw/`）未上传 |

> 由于原始受限数据未上传，**依赖这些原始件的结论无法在本仓库内完整复算**，只能核验其**结果表与程序**。

---

## 4. 对分类体系的修订说明

上游 `GITHUB_UPLOAD_CANDIDATES.csv` 的既有分类（"可公开上传 / 需要人工审核 / 仅供本地研究 / 不应上传"）
**尚未完成逐文件许可审核**。本次**未直接沿用**该分类，而是：

1. 以**逐文件**规则重新判定（见上表排除原因）；
2. 对"需要人工审核"的第三方 PDF / 政府网页 / 商业数据，**一律不默认上传**（保守处理）；
3. 对 `data/processed`、`data/model_ready` 等原"仅供本地研究"的**派生研究数据**，
   依据其**对正式结论的直接支撑作用**与**研究必需性**纳入上传，并在此明确其再分发限制。

---

## 5. 未上传内容的本地位置（供回取）

| 内容 | 本地位置 |
|---|---|
| 原始证据总体 | `source_snapshot/data/raw/`（本地只读） |
| 政府/新闻网页 | `source_snapshot/data/raw/{policy,disaster,city_sources}/` |
| 商业平台价格 | `source_snapshot/data/raw/prices/{ecommerce,b2b,hnwb}/` |
| 统计年鉴原件 PDF | `source_snapshot/data/raw/{production,decision_engine_supplement*}/` |
| 第三方栅格/矢量 | `source_snapshot/data/research/shenyang/case_studies/**/*.{tif,gpkg}`（未复制，仍在上游） |
| 模型权重 | 上游源项目 `models/short_term/`、`models/long_horizon/`（未复制） |
| 大体量抓取缓存 | 上游源项目 `data/raw/web_captures/`、`prices/*_deep`、`dalian_12316`（未复制） |

> 回取方式见 [`audit/MISSING_DEPENDENCIES.csv`](MISSING_DEPENDENCIES.csv) 与
> [`audit/SOURCE_PATHS.csv`](SOURCE_PATHS.csv)。
