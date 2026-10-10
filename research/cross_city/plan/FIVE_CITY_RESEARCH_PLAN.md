# 辽宁六城农业市场与风险研究体系 — 第一阶段计划

> 生成日期：2026-10-08
> 目标：把「沈阳=完整研究，其余五城=只有数据」升级为「沈阳+朝阳+大连+丹东+锦州+铁岭+跨城市研究」
> 本文件 = 研究可行性矩阵 + 问题定义。数据依据见 `archive/audits/city_research_audit_20261008/AUDIT_REPORT.md`。
> 纪律：结论由数据决定；数据不支持则显式写 `NOT_SUPPORTED_BY_CURRENT_DATA`，不为"八篇整齐"强行分析。

---

## 一、统一研究框架（对齐用户定义，沈阳为格式模板）

| 模块 | 定义（本项目采用） | 沈阳对应 |
|---|---|---|
| A01 | 市场价格时间结构与季节性 | A01 |
| A02 | 天气与市场同期关系 | A02 |
| A03 | 滞后、累积与非线性响应 | A03 |
| A04 | 极端事件前后变化 | A04 |
| A05 | 作物异质性与恢复能力 | A05 |
| A06 | 市场可预测性 / 预测增益 | A06（量价+天气增量） |
| A07 | 农业生产与结构变化 | A07 |
| A08 | 稳健性与可信度（横切，依附 A01–A07） | 沈阳 A08 为区县面板，口径不同 |
| A09 | 城市特色专项研究（不复制） | A09（综合篇） |

> 说明：沈阳 A08 实际为"区县单产气象面板"，与用户定义的"稳健性与可信度"不同。本项目采用用户定义；
> 区县面板作为沈阳特有项保留在沈阳，不机械复制到五城。

---

## 二、研究可行性矩阵（A01–A09 × 五城）

状态：`SUPPORTED`=数据充分；`PARTIAL`=可行但受口径/频率限制；`WEAK`=数据稀疏，仅能描述性；`NOT_SUPPORTED_BY_CURRENT_DATA`=不成立。

| 模块 | 朝阳 | 大连 | 丹东 | 锦州 | 铁岭 | 关键约束 |
|---|---|---|---|---|---|---|
| A01 价格时间结构 | **SUPPORTED** | PARTIAL | WEAK | **SUPPORTED** | WEAK | 大连=周度；丹东/铁岭无稳定蔬菜日序列 |
| A02 天气-市场同期 | **SUPPORTED** | PARTIAL | NOT_SUPPORTED | **SUPPORTED** | NOT_SUPPORTED | 需日度价格；锦州层级=超市 |
| A03 滞后/累积/非线性 | **SUPPORTED** | PARTIAL | NOT_SUPPORTED | **SUPPORTED** | NOT_SUPPORTED | 同上 |
| A04 极端事件前后 | **SUPPORTED** | PARTIAL | PARTIAL | PARTIAL | PARTIAL | 事件表稀疏；五城价格多为非 wholesale |
| A05 作物异质性与恢复 | **SUPPORTED** | PARTIAL | WEAK | PARTIAL | WEAK | 恢复观察右删失风险高 |
| A06 天气预测增量 | **SUPPORTED** | PARTIAL | NOT_SUPPORTED | PARTIAL | NOT_SUPPORTED | 量价关系五城全 NOT（无 volume） |
| A06 量价关系 | NOT_SUPPORTED | NOT_SUPPORTED | NOT_SUPPORTED | NOT_SUPPORTED | NOT_SUPPORTED | 仅沈阳有成交量 |
| A07 生产与结构变化 | **SUPPORTED** | **SUPPORTED** | **SUPPORTED** | **SUPPORTED** | **SUPPORTED** | 五城年鉴 2017–2025，城市级 |
| A08 稳健性与可信度 | 横切（随 A01–A07 成立度） | 同 | 同 | 同 | 同 | 少聚类/强自相关下推断有限 |
| A08 区县单产面板 | NOT_SUPPORTED | NOT_SUPPORTED | NOT_SUPPORTED | NOT_SUPPORTED | NOT_SUPPORTED | 五城无区县生产数据（仅沈阳有） |
| A09 城市特色 | 待数据确认 | 待确认 | 待确认 | 待确认 | 待确认 | 见第四节 |

### 六城口径对照（禁止直接比较价格水平）

| 城市 | 价格层级 | 频率 | 主源 |
|---|---|---|---|
| 沈阳 | wholesale | daily | 市发改委菜篮子 |
| 朝阳 | market_average | daily | 市发改委菜篮子每日价情 |
| 锦州 | supermarket | daily | 市菜篮子(OCR) |
| 大连 | farm_gate/retail 混合 | weekly | 市农业农村局周报 |
| 丹东 | farm_gate | 稀疏 | 惠农网 |
| 铁岭 | farm_gate/retail 混合 | 稀疏 | 惠农网 |

---

## 三、统一方法约定（六城一致，保证可比）

1. **作物字段**：一律用 `crop_raw`；建立受控 `crop_map`（crop_raw → crop_std）并留白名单；禁用 `crop_standard` 原字段。
2. **价格分层**：按 `price_level` 分层，主分析只取该城主层级；跨层级记录不混合。
3. **单位**：统一 `price_per_kg`；成交量单位未知（沈阳），禁写"吨"。
4. **去季节化**：采用**严格无未来信息**的历史同期基线（基线仅用严格更早年份，doy±5 环形中位数 + MAD 尺度），与沈阳 v2 一致；"留一年法"仅作稳健性对照。
5. **主模型**：`y_t = α + φ·y_(t-1) + β·weather_t + 日历控制 + ε_t`，Newey-West/HAC 稳健标准误；效应量按"每 +1 SD 暴露"报告。
6. **多重检验**：BH-FDR，按"目标×暴露"家族校正，同时报原始 p 与 q。
7. **少聚类/强自相关**：报告 AR(1) 与 n_eff；必要时 wild cluster bootstrap / block bootstrap。
8. **阴性结果正式报告**；相关性不写因果；效应极小不得称"影响巨大"。

---

## 四、各城研究问题（数据驱动，初定；A09 为候选，须分析后定稿）

### 朝阳（强：日度市场均价 2021-03~2026-09，15 种蔬菜）
- A01：朝阳市主要菜篮子产品价格的时间结构与季节性（季节指数、趋势、HAC）。
- A02/A03：降水/气温/土壤水分与朝阳蔬菜价格的同期、滞后、累积与非线性响应。
- A07：朝阳市农业生产结构（2017–2025 年鉴）与作物集中度。
- **A09 候选**：朝阳市**旱涝暴露**与蔬菜价格季节性（辽西半干旱区，设施/露地结构未知 → 设施农业数据 NOT_FOUND，不作设施分析）。

### 大连（中：周度、层级混合、历史最长 2017–2026，43 种蔬菜）
- A01：大连市农产品价格周度结构与季节性（周度口径）。
- A02/A03：沿海气候（湿度/风/辐射）与周度价格的响应（周度粒度限制）。
- A07：大连农业生产结构。
- **A09 候选**：大连作为**大城市消费市场 + 沿海气候 + 港口/市场可达性**（`logistics_reference` 3 条、`market_accessibility` 10 条）→ 市场可达性与价格关系（探索性，不作真实物流最优）。

### 丹东（弱：无稳定蔬菜日序列，特色作物 + 多灾害）
- A01–A06：蔬菜市场类 → **NOT_SUPPORTED_BY_CURRENT_DATA**；仅对稀疏特色作物作描述性说明。
- A07：丹东农业生产结构（含特色作物）。
- **A09 候选**：丹东**高降水/山地环境与特色农业**（草莓/蓝莓/板栗/中药材/淡水鱼/柞蚕）及极端天气暴露（`disaster_loss` 17 条）。

### 锦州（中：日度但层级=超市，12 种蔬菜，2020-07~2026-09）
- A01：锦州市菜篮子价格时间结构（超市层级口径）。
- A02/A03：辽西干旱/高温暴露与价格响应（超市口径）。
- A07：锦州农业生产结构。
- **A09 候选**：锦州**辽西农业 + 市场供给**结构与价格层级差异。

### 铁岭（弱：无稳定蔬菜序列；粮牧为主）
- A01–A06：蔬菜市场类 → **NOT_SUPPORTED_BY_CURRENT_DATA**。
- A07：铁岭**粮食生产（玉米/水稻/大豆）与种植结构**变化（2017–2025）。
- **A09 候选**：铁岭**粮食与大田农业**的生产结构与气象关系（城市级，弱推断）。

---

## 五、逐城最终交付结构（对齐沈阳模板）

```
data/research/<city>/
├── A01..A09/
│   ├── report.md           # 正式研究文章（中文；文末 ARTICLE_END）
│   ├── article.json        # 前端消费契约（字段同沈阳 A01）
│   ├── tables/*.csv        # 结果表（含 estimate/CI/N/q）
│   ├── figures/*.png       # 科研图
│   └── metrics/*.json      # 关键指标
├── city_meta/
├── plan/                   # 该城研究计划（本文件派生的城市版）
├── config/                 # crops/events/paths
├── evidence/claim_evidence.csv
└── sources/source_registry.csv
```

交互研究版契约（selectors/metrics/series/tables/sources/methodology/limitations）随每篇 `article.json` 的
扩展字段提供；实现前先对齐沈阳现有消费契约（前置任务，见待办 t10）。

---

## 六、工作节奏（不五城齐跑）

```
统一审计(已完成) → 可行性矩阵(本文件) → 问题定义(本文件)
→ 按模块批量：A01 六城 → A02 六城 → A03 六城 → … → A07 六城
→ 各城 A09（探索后定题）
→ cross_city（市场周期/传导/集中度/韧性）
→ 交互版 → 科研 Skill 到位后 → 正式文章润色 + 模拟审稿
```

---

## 七、与冻结架构的一致性

- 研究**数据/产物** → `data/research/<city>/`、`data/research/cross_city/`。
- **审计** → `archive/audits/`；**Agent 报告** → `archive/agent_reports/`；**失败实验** → `archive/experiments/`。
- 不修改 LLM/RC3 相关代码、runtime manifest、正式模型、Git 状态。
- 第三方 Skill 目录规则不得覆盖 AgriScope 冻结架构。

---

## 八、执行状态（2026-10-08 更新）

| 阶段 | 状态 | 产物 |
|---|---|---|
| 统一数据审计 | ✅ 完成 | `archive/audits/city_research_audit_20261008/` |
| 可行性矩阵 + 问题定义 | ✅ 完成 | 本文件 |
| A01–A09 五城批量分析 | ✅ 完成 | `data/research/<city>/A0X/` |
| 跨城市研究 | ✅ 完成 | `data/research/cross_city/` |
| 交互研究版实现 | ⏳ 待前端接入（契约已就绪于各 article.json 的 explorer） | — |
| 正式论文写作 | ⏳ 待科研 Skill 下载完成 | — |

模块状态：朝阳/大连/锦州 A01–A09 全部成立；丹东/铁岭 A07+A09 成立、A01–A06/A08 为 NOT_SUPPORTED_BY_CURRENT_DATA。
施工详情见 `archive/agent_reports/CITY_RESEARCH_PHASE1_REPORT.md`。

*状态：第一阶段（审计 → 可行性矩阵 → 问题定义 → 分析 → 跨城）完成。*