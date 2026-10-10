# BLOCKERS — 数据阻断与降级记录

> 规则：数据不支持时宁可记录 BLOCKED，也不补造、不静默失败。
> 单个模块阻断不影响其他模块继续执行。

## 01_build_panel

- 记录时间：2026-09-21 15:26:27
- 原因：1991-2020 气候基线 JSON 不含土壤含水量（soil_moisture_0_to_10cm_mean 全为 null，10958 天 0 个有效值），无法按任务书 §二十 用官方基线标准化 soil_moisture_z
- 详情：降级处理：以 2021-2026 观测期 leave-one-year-out 同期（doy±5 环形）均值自建期望值，目标年不进入自身基线（无泄漏）；尺度用全局稳健尺度 1.4826×MAD（与价格/成交量异常一致）；新增列 soil_moisture_0_7_mean_obs / _anomaly_obs / _scale_obs / soil_moisture_z_baseline 以显式标注口径；该指标证据等级由 A 降为 B（观测期自建基线，非官方 30 年基线）。
- 处理：该模块对应分析标记为 `NOT SUPPORTED BY CURRENT DATA`

## 12_phenology

- 记录时间：2026-09-21 23:17:18
- 原因：crop_calendar 中部分本地行无可用采收/成熟日期，已跳过（不插补）
- 详情：skipped=芸豆|辽宁（大棚早春）|设施
- 处理：该模块对应分析标记为 `NOT SUPPORTED BY CURRENT DATA`

## 12_phenology

- 记录时间：2026-09-21 23:18:25
- 原因：crop_calendar 中部分本地行无可用采收/成熟日期，已跳过（不插补）
- 详情：skipped=芸豆|辽宁（大棚早春）|设施
- 处理：该模块对应分析标记为 `NOT SUPPORTED BY CURRENT DATA`

## 12_phenology

- 记录时间：2026-09-21 23:18:25
- 原因：部分品种在本地日历中为全年窗口（或空窗口），交互项不可识别
- 详情：crops=韭菜；处理=不进入该口径的检验与 FDR 家族
- 处理：该模块对应分析标记为 `NOT SUPPORTED BY CURRENT DATA`

## 13_yearly_production

- 记录时间：2026-09-21 23:20:09
- 原因：沈阳蔬菜年度生产数据存在年份断裂（不插补）
- 详情：已有年份=[2017, 2018, 2019, 2025]；缺失年份=[2020, 2021, 2022, 2023, 2024]；原因：fact_production_yearly_2020_2024.csv 沈阳无蔬菜行
- 处理：该模块对应分析标记为 `NOT SUPPORTED BY CURRENT DATA`

## 13_yearly_production

- 记录时间：2026-09-21 23:20:09
- 原因：年度生产年份缺少对应生长季气象（不插补）
- 详情：无气象年份=[2017, 2018, 2019, 2020]；weather_daily 可得范围 2021-2026
- 处理：该模块对应分析标记为 `NOT SUPPORTED BY CURRENT DATA`

## 13_yearly_production

- 记录时间：2026-09-21 23:20:09
- 原因：水果：年度产量与生长季气象的重叠年份不足 4 年
- 详情：overlap_years=[2025]；处理=不计算相关系数（不插补、不外推）
- 处理：该模块对应分析标记为 `NOT SUPPORTED BY CURRENT DATA`

## 13_yearly_production

- 记录时间：2026-09-21 23:20:09
- 原因：瓜果：年度产量与生长季气象的重叠年份不足 4 年
- 详情：overlap_years=[]；处理=不计算相关系数（不插补、不外推）
- 处理：该模块对应分析标记为 `NOT SUPPORTED BY CURRENT DATA`

## 13_yearly_production

- 记录时间：2026-09-21 23:20:09
- 原因：蔬菜及食用菌：年度产量与生长季气象的重叠年份不足 4 年
- 详情：overlap_years=[2025]；处理=不计算相关系数（不插补、不外推）
- 处理：该模块对应分析标记为 `NOT SUPPORTED BY CURRENT DATA`

