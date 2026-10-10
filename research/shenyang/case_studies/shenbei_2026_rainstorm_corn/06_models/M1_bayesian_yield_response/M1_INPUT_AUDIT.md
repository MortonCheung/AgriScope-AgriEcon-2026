# M1_INPUT_AUDIT.md — 输入事实冻结（P3 起始）

## 结果变量
- 沈北新区玉米**单位面积产量** `corn_yield_kg_ha`（kg/ha）

## 有效年份 / 样本量
- **2018–2025**；**n = 8**

## 2026
- **只有天气与事件，没有正式年度玉米单产结果**（`not_available`）

## 天气历史
- **1991–2026 日值特征**（ERA5 再分析，D 级；`corn_year_weather_features.csv`）

## 物候
- 已有 **GDD 年际物候估计**（`corn_phenology_yearly_gdd.csv`；抽雄≈7月中旬、吐丝≈7月中旬）

## 关键事件
- **2026-07-13 左右极端降雨**，位于**抽雄—吐丝窗口**附近。

## 当前不能直接观测
- 全区 **Waterlogging**（隐变量）
- **CropStress**
- **2026 区级实际灾损**

## 模型定位（重要）
> M1′ 当前研究的是 **“天气暴露—年度单产响应”（response / association model）**，
> **不是**完整因果链 `Weather→Waterlogging→CropStress→Yield`。
> 因此结果**不得**表述为 **causal effect**，除非未来获得充分因果证据。

## 训练／使用边界
- 训练年份：2018–2025（n=8）
- 2026 用于**情景推演**，其暴露值是否落在训练范围见 `validation/EXTRAPOLATION_AUDIT.md`
