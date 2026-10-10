# UNCERTAINTY_PROPAGATION.md（R14 / §六十五~六十九）

## 为什么不能“取均值再取均值”
M2→M3→M4 逐步取均值会**严重低估不确定性**。正确做法：**每次 MC draw 从各模块分布抽样，完整跑一个 world**，最后得到 **Outcome distribution**。

## Common Random Numbers（CRN）
同一次 draw 中，A/B/C/D **共享非处理随机参数**（k_inf、k_nat、init_storage、pump、rain），**只改变 weather / intervention**，从而降低世界间比较的纯模拟噪声（§六十七）。

## 合成演示（SYNTHETIC，2000 draws，参数为范围而非沈北真值）

                 quantity  median  p50_lo  p50_hi  p80_lo  p80_hi  p95_lo  p95_hi
                        A    56.5    50.5    65.0    45.5    74.0   41.49   85.50
                        B    26.5    22.0    32.5    18.0    39.0   15.50   45.50
                        C    69.0    59.5    81.5    53.0    97.0   47.00  114.01
                      D24    52.5    46.0    61.5    41.0    70.5   36.50   81.01
                      D48    52.0    45.0    61.0    40.0    70.0   36.00   80.51
disaster_effect_C_minus_A    12.0     8.5    17.0     6.0    24.0    4.00   32.50
        extra_benefit_D24     4.0     3.0     5.0     2.5     6.0    2.00    7.00
        extra_benefit_D48     4.5     3.5     6.0     3.0     7.0    2.00    8.00

## 结论
- 演示仅验证**传播框架与代码**可用（分布、区间、CRN、ordering）。
- **不得**把上表任何数字当作沈北结论（参数为 SYNTHETIC）。
