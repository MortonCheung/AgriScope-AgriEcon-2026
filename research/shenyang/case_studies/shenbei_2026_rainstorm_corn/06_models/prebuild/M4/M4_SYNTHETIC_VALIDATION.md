# M4_SYNTHETIC_VALIDATION.md（R11 / §五十~五十二）

> 全部为 **SYNTHETIC** 场景：参数来自范围，不代表沈北真值。

## 不变量测试（必须全部通过）

                    test                       values  passed                note
     T1_pump_capacity_up     [76.2, 67.8, 62.0, 56.5]    True    end_h 非随泵能力上升而增加
        T2_earlier_start     [57.2, 59.0, 62.0, 66.8]    True      越早启动 end_h 不更晚
       T3_no_pump_slower                 [62.0, 76.2]    True 无泵 world 排净时间 >= 现实
T4_more_rain_higher_peak [120.0, 131.6, 208.0, 360.8]    True             峰值随降雨不减
       T5_wetter_initial     [45.2, 56.5, 62.0, 70.2]    True       初始更湿 end_h 不减

**总判定：全部通过**

## 合成世界情景（SYNTHETIC，不可作为结论）

     scenario  peak_mm  end_h
       A_real    120.0   62.0
B_normal_rain    120.0   53.2
    C_no_pump    120.0   76.2
 D_start_-24h    120.0   58.0
 D_start_-48h    120.0   57.2

## 说明
- A_real 与 B/C/D 的差值在合成参数下呈现**方向正确**的排序，但这只检验**模型逻辑**，**不构成任何沈北数字**。
