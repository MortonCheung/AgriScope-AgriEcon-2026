# LIT-WANG2023-NE-CWSDI

- **题目**：Drought and Waterlogging Status and Dominant Meteorological Factors Affecting
  Maize (Zea mays L.) in Different Growth and Development Stages in Northeast China
- **作者**：Xiaowei Wang, Xiaoyu Li, Jiatong Gu, Wenqi Shi, Haigen Zhao, Chen Sun, Songcai You*
- **单位**：中国农科院农业环境与可持续发展研究所 / **沈阳农业大学农学院** / 东北农业大学资源与环境学院
- **出处**：*Agronomy* **2023**, *13*(2), 374
- **DOI**：10.3390/agronomy13020374（开放获取 CC BY）
- **数据**：246 个气象站 1981–2015 日数据 + 192 个点位的玉米物候数据

## ★★★ 对本专题最核心的一句（直接可用）

> "Waterlogging occurred predominantly in the **flowering to the silking stages** and the
> **silking to the maturity stages** in **southeast Liaoning** and parts of Jilin."

**辽宁东南部（含沈阳所在的中部平原南缘）玉米渍涝主要发生在开花—吐丝期与吐丝—成熟期。**

沈北 2026 事件发生在 **7 月 13—18 日**，正是辽宁春玉米的**抽雄—吐丝期**。
→ 这不是偶然，而是**该区域渍涝的气候易发期**与本年度极端降雨的叠加。

## 关键定量结果

### 逐日需水量排序（mm/d）
| 序 | 生育阶段 | 需水量 |
|---|---|---|
| 1 | 开花—吐丝 FR-R1 | **6.9** |
| 2 | 抽雄—开花 VT-FR | 6.1 |
| 3 | 拔节—抽雄 JT-VT | 4.9 |
| 4 | 七叶—拔节 V7-JT | 3.4 |
| 5 | 吐丝—收获 R1-R6 | 2.0 |
| 6 | 出苗—三叶 VE-V3 | 1.4 |
| 7 | 三叶—七叶 V3-V7 | 1.3 |
| 8 | 播种—出苗 SW-VE | 1.2 |

**抽雄—开花期需水量 6.1 mm/d，为全生育期第 2 高** → 该阶段水分供需矛盾最尖锐，既怕旱也怕涝。

### 各阶段总需水量（mm）
19.2 / 10.1 / 18.9 / 67.6 / 98.9 / 18.2 / 13.8 / 113.6

### 阶段时长（d）
SW-VE 16 / VE-V3 7 / V3-V7 14 / V7-JT 20 / **JT-VT 20** / **VT-FR 3** / **FR-R1 2** / R1-R6 58

### 水分盈亏指数趋势
- 生育期平均有效降水 **359.8 mm**；最低 265.2 mm（1999）、最高 493.8 mm（1994）
- 有效降水显著下降趋势：**−11.4 mm/10a（p<0.001）**（1981–2015）

## 使用的国家标准

**QX/T 259-2015**（中国气象标准化网络，北方春玉米干旱等级）→ 据此建立 CWSDI 分级的
干旱与渍涝阈值（该文 Table 3 给出 8 个生长阶段各自的分级区间）。

⚠️ **该表对 M3/M2 有直接价值：提供了"逐阶段不同阈值"的官方分级框架**，
说明作物对水分盈亏的敏感度是**阶段相关**的，不能用单一阈值概括全生育期。

## ★ 该文自述的两个局限（正是本专题要补的空白）

1. "We did not cover stored water, particularly contributions from the winter fallow period"
2. ★★ **"The model does not consider drainage of excess water through the soil or down a
   slope in assessing the flooding risk."**

→ 该文**明确承认其渍涝评估没有考虑排水**。沈北专题的 M2/M4 恰恰要做**排水工程能力**
与渍涝历时的耦合 —— 这正是本专题相对该文的**方法增量**。

## 其他可用论断

- 辽宁的水分条件在全东北**最好**（"The moisture conditions were the best in the Liaoning region"）
- 玉米可种植区界定：活动积温（>10 °C）> 2300 °C
- 主导气象因子排序：降水 > 风速（负效应）> 最低温 > 相对湿度 > 日照时数 > 最高温；
  **平均气温无影响**
- 抽雄—成熟期连阴雨风险："Rainfall was approximately equal to crop requirements during
  ripening, which has the potential to delay drying of the crop and harvest"

## 适用性

`REGIONAL_CLIMATOLOGY_BASELINE` —— **不提供减产率**，但提供：
① 辽宁渍涝的**气候易发期**（=开花—吐丝期，与沈北事件吻合）；
② 春玉米**逐阶段需水量**（可用于 M3 水分平衡）；
③ **QX/T 259-2015 官方分级框架**；
④ "考虑排水"的方法学缺口（本专题的增量定位依据）。
