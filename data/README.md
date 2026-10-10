# AgriScope 数据入口说明（data/README）

> 本文件是**唯一的数据入口说明**。下一轮建模 Agent 只需读本文件 + `data/`，不要再猜 canonical / marts / V1 / V2 / V3 该用哪个。

## 一句话结论

**原始证据在 `data/raw/`；正式结构化数据在 `data/processed/`；模型输入层在 `data/model_ready/`；研究内容在 `data/research/`；治理与元数据在 `data/metadata/`；数据脚本在 `data/scripts/`；数据报告在 `data/reports/`。**

旧概念 `raw_data / data_foundation / city_data / tools` 已在 2026-10-07 结构收口中**并入 `data/`**；旧加工层（marts / curated / staging / supplement 加工副本 / 旧报告）全部在 `archive/`，不再作为数据入口。

## 去哪看

| 需求 | 位置 | 说明 |
|---|---|---|
| 原始证据去哪看？ | `data/raw/` | 下载文件、API 响应、网页、PDF、XLS、遥感证据、官方材料 |
| 正式结构化数据？ | `data/processed/` | 唯一标准化事实层（按主题；含 `integrated/` 跨表整合层） |
| 模型应该读哪？ | `data/model_ready/` | 唯一模型输入层 |
| 研究历史去哪？ | `data/research/<city>/` | 沈阳 A01–A09 等研究内容，**非建模数据源** |
| 治理/质量/需求？ | `data/metadata/` | governance / inventory / quality / requirements / evidence / snapshots |
| 重建脚本？ | `data/scripts/data_foundation/run_all.py` | 一键重建 |
| 数据报告？ | `data/reports/` | Data Foundation 报告 / 缺口 / QC |
| 旧数据去哪？ | `archive/` | 唯一历史区（old_marts / data_legacy / data_reports / audits） |
| 保留源（重建用）？ | `data/raw/retained_source/` | 仅供重建，模型不必读 |

## data/ 目录结构

```text
data/
├── raw/            原始证据层（只读不改）
├── processed/      唯一标准化事实层（主题目录 + integrated/）
├── model_ready/    唯一模型输入层
├── research/       六城研究内容（shenyang / chaoyang / jinzhou / dalian / tieling / dandong）
├── metadata/       governance / inventory / quality / requirements / evidence / snapshots
├── scripts/        全部数据处理脚本（data_foundation / collectors / parsers / transformers / validators / pipeline）
└── reports/        数据层人类可读报告
```

## 建模必读的三张治理文件

1. `data/metadata/governance/CANONICAL_TABLE_REGISTRY.csv` —— **每个指标只推荐一张表**（唯一真源）。
2. `data/metadata/governance/RECOMMENDED_MODEL_INPUTS.csv` —— **下一轮建模严格从这里读**。
3. `data/metadata/governance/DO_NOT_USE_FOR_MODEL.csv` —— 明确禁止使用的路径/字段。

## 数据使用硬规则（摘要）

- `price_level` 的 8 个口径（wholesale / market_average / retail / retail_market / supermarket / farm_gate / purchase / other）**严禁混用**。
- `crop_standard` 已修复历史污染；衍生字段：`variety / specification_norm / grade / package / processing_state`。
- 成本必须看 `cost_source_class`；亩产必须看 `yield_source_class`。
- 遥感 NDVI 为**月度**语义，不得插值为日频真实遥感；只表示植被状态异常，**不等于减产**。
- 缺数据如实标注 `NOT_FOUND / NOT_PUBLIC / USER_INPUT_REQUIRED`，**禁止编造或随机生成**。

## 如何重建

```bash
python3 data/scripts/data_foundation/run_all.py
```

从 `data/raw/` + `data/raw/retained_source/` 一键重建全部 `data/processed/` `data/model_ready/` `data/metadata/`（幂等，可重复运行）。