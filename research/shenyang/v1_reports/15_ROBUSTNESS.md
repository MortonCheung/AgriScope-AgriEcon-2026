# 15 稳健性（Phase 15，STEP 27）

> §六十三：不做稳健性，平行世界只是漂亮模型。§六十四：不追求所有模型结论完全相同，
> 区分 **Stable / Sensitive / Unsupported**。

## 1 维度 1：不同季节基线（STL vs historical median，§六十三-1）

2026-07 事件窗（2026-07-12~2026-07-17）内异常 z 均值，hist（方法B，主）vs stl（方法A，对照）：

crop response  hist_event_mean  stl_event_mean  sign_agree
  土豆    price           0.6745          0.4699        True
  土豆   volume           0.7307          0.1511        True
  尖椒    price           0.1241          0.0170        True
  尖椒   volume          -1.0679         -0.1283        True
  甘蓝    price           0.2461          0.2832        True
  甘蓝   volume          -0.5621          0.1303       False
  芸豆    price           0.0171         -0.1276       False
  芸豆   volume           0.7757          0.1546        True
  芹菜    price           0.4242          0.0780        True
  芹菜   volume          -0.8375         -0.4679        True
  茄子    price           0.0309         -0.3085       False
  茄子   volume          -0.7783          0.2988       False
 西红柿    price           0.1244          0.1194        True
 西红柿   volume          -0.4770         -0.4114        True
  青椒    price          -0.2177         -0.5236        True
  青椒   volume           0.7419         -0.0588       False
  韭菜    price           1.0206          0.7295        True
  韭菜   volume           0.8263          0.1371        True
  黄瓜    price           0.2952         -1.2499       False
  黄瓜   volume          -0.6070         -0.1060        True

- 主口径与方法对照的跨品种 Spearman 相关与符号一致率见上表（`sign_agree`）。
- 结论只允许引用与两口径**方向一致**的部分；不一致处降级为 Sensitive。

## 2 维度 2：不同事件窗口（-7/+14、-14/+21，§六十三-2）

2026-07-13（峰值）前后两窗口的事件响应（相对各自前 7 日基期）：

crop response    window  event_response_z
  土豆    price  [-7,+14]           -0.0245
  土豆   volume  [-7,+14]           -0.5305
  尖椒    price  [-7,+14]           -0.4081
  尖椒   volume  [-7,+14]           -0.7658
  甘蓝    price  [-7,+14]            0.1632
  甘蓝   volume  [-7,+14]           -0.3091
  芸豆    price  [-7,+14]           -0.3813
  芸豆   volume  [-7,+14]            0.1020
  芹菜    price  [-7,+14]           -0.0339
  芹菜   volume  [-7,+14]           -0.5445
  茄子    price  [-7,+14]            0.0456
  茄子   volume  [-7,+14]           -0.7316
 西红柿    price  [-7,+14]           -0.0867
 西红柿   volume  [-7,+14]            0.5089
  青椒    price  [-7,+14]           -0.3958
  青椒   volume  [-7,+14]            1.3237
  韭菜    price  [-7,+14]            0.7211
  韭菜   volume  [-7,+14]           -0.2234
  黄瓜    price  [-7,+14]            1.8800
  黄瓜   volume  [-7,+14]           -0.4426
  土豆    price [-14,+21]            0.1472
  土豆   volume [-14,+21]           -0.2547
  尖椒    price [-14,+21]           -0.3612
  尖椒   volume [-14,+21]            0.0000
  甘蓝    price [-14,+21]            0.0529
  甘蓝   volume [-14,+21]           -0.0842
  芸豆    price [-14,+21]           -0.2494
  芸豆   volume [-14,+21]           -0.2065
  芹菜    price [-14,+21]           -0.3164
  芹菜   volume [-14,+21]           -0.0324
  茄子    price [-14,+21]           -0.5651
  茄子   volume [-14,+21]           -0.1636
 西红柿    price [-14,+21]           -0.0461
 西红柿   volume [-14,+21]            0.1916
  青椒    price [-14,+21]           -0.2000
  青椒   volume [-14,+21]            0.8474
  韭菜    price [-14,+21]            0.5580
  韭菜   volume [-14,+21]           -0.4144
  黄瓜    price [-14,+21]            1.0664
  黄瓜   volume [-14,+21]           -0.4462

- 符号一致率（10 品种 × 2 响应）：见 `robustness_event_windows.csv`。

## 3 维度 3：不同模型（Linear / GAM / boosting，§六十三-3）

STEP 25-26 的 World1A 反事实缺口（方法A，事件窗均值）在三个模型族下的表现（POOLED）：

   learner  gap_volume_z  gap_price_z
  lightgbm       -0.0795      -0.3563
elasticnet        0.0499      -0.4902
       gam        0.4232      -0.2688

- 三模型族**价格缺口全部为负**（灾害→价格↑的模型口径，方向 Stable）；
- **成交量缺口方向不一致**：LightGBM 为负、ElasticNet/GAM 为正（量级与符号均 Sensitive）。
  故成交量口径的反事实缺口不得作为方向性结论引用。

## 4 维度 4：不同天气指标（daily vs 3d cumulative，§六十三-4）

2026-07 各指标下的「事件日」计数：

                  measure  threshold_mm  days_flagged  max_mm
  precip_1d (daily ≥50mm)          50.0             2   173.9
precip_3d (3d cum ≥100mm)         100.0             3   221.1
precip_7d (7d cum ≥150mm)         150.0             7   283.2

- 三种定义均能识别 7 月中旬暴雨；7/19（precip_1d=61.6mm）仅在 1d/3d 定义下被单独识别。

## 5 维度 5：Placebo（§六十三-5）

真实极端天气事件响应 vs 500 次随机非灾害日虚假事件：

group response  real_post_mean  placebo_p50  real_percentile_in_placebo       verdict
 rain    price          0.0169      -0.0241                       0.564 不可分辨于 placebo
 rain   volume          0.0746      -0.0241                       0.686 不可分辨于 placebo

- **真实响应不可分辨于 placebo**（与 STEP 12 event_study_summary 的 placebo_p 一致）：
  在观测尺度上，极端天气事件对量价的平均影响不显著强于随机波动。

## 6 §六十四 判定表

                         conclusion                    dimension                                                result judgement
           C1 天气→成交量在日度/事件尺度不可分辨于噪声                      placebo                                         不可分辨于 placebo    Stable
   C2 成交量→价格同日系数极小、中介≈0（STEP 15-17）                       跨模型/缓冲                       STEP 26：供应缓冲对价格缺口影响≈0（LightGBM）    Stable
                  C3 2026-07 事件量价响应            基线方法(hist vs stl)        跨品种 Spearman 见 robustness_baseline_methods.csv Sensitive
                  C3 2026-07 事件量价响应       事件窗(-7/+14 vs -14/+21)                 方向一致品种数见 robustness_event_windows.csv    Stable
C4a 反事实缺口方向：价格（灾害→价格↑，模型口径 Level D） 模型族(lightgbm/elasticnet/gam)                    三模型族价格缺口符号：{np.float64(-1.0)}（全同号）    Stable
      C4b 反事实缺口方向：成交量（模型口径 Level D） 模型族(lightgbm/elasticnet/gam) 三模型族成交量缺口符号：{np.float64(1.0), np.float64(-1.0)}（存在异号） Sensitive

- **Stable**：不同设计下方向一致；**Sensitive**：方向稳定但量级/窗口敏感；
  **Unsupported**：结果不稳定，不进入正式结论。

## 7 Bootstrap 不确定性

STEP 25-26 已用配对残差 Bootstrap（B=100，2025 valid 期残差）给出 World1A 缺口的 95%CI，
见 `reports/14_COUNTERFACTUAL.md` 与 `counterfactual_gap_summary.csv`。

## 8 图表

- F50：Placebo 分布 vs 真实事件响应
- F51：跨模型族反事实缺口

## 9 局限

1. STL 基线含目标年（§二十一 泄漏红线），仅作方向对照；
2. 事件窗/基线维度只覆盖 2026-07 单一事件；
3. 跨模型仅覆盖同一特征口径（F_lag），未覆盖 F_wx/F_now；
4. Placebo 来自 STEP 12 的日度均值口径，未按品种分层。

---
生成时间：2026-09-22 01:15:33
