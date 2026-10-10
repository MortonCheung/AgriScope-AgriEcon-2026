# M4_STATE_EQUATION.md（R10 / §四十五~四十九）

## 目标（不是 Intervention→Yield）
```
Intervention → Waterlogging Duration
```

## 状态方程
```
Storage(t+Δt) = Storage(t) + ( Rainfall + Inflow − Infiltration − NaturalDrainage − PumpDrainage − OtherLosses ) · Δt
```

## 每项可观测性标注

           parameter                              role                     note      range
       rain_mm_per_h                  OBSERVED/DERIVED ERA5 事件雨强（注意为单点 forcing）          —
             area_m2                      OBSERVED（个案） 八间房村 8000 余亩 → 5.33e6 m²         量级
          k_inf_mm_h CALIBRATABLE/LITERATURE_PARAMETER          入渗能力（土壤缺失 → 范围）       1~10
         k_nat_per_h                            LATENT           自然排水/沟渠/外排综合速率 0.005~0.08
     init_storage_mm                            LATENT               初始蓄水（前期湿润）     20~200
   pump_capacity_m3h                           DERIVED       12×8寸泵（工程参考区间，非铭牌）  1800~6000
intervention_start_h                          OBSERVED        预警→行动：14.8h（八间房村）          —
      s_threshold_mm                           ASSUMED                视为排净的残余深度      0.1~2

## emergency pumping ≠ 全部排水（§四十八）
真实案例：**12 台 8 寸泵 / ~96h / 8000 余亩**。**不能**推导“所有水都由这 12 台泵抽走”。
还必须考虑：自然下渗、沟渠排水、地表外排、蒸散、其他设备、上下游调度。
→ 该案例只能作为 **weak aggregate constraint**，**不得据此反推真实泵流量**。

### 量级示意（仅换算，非真值）

 pump_capacity_m3h  pump_equivalent_mm_per_h  hours_to_remove_200mm_by_pump_only  hours_to_remove_500mm_by_pump_only
              1800                     0.338                               592.2                              1480.6
              3600                     0.675                               296.1                               740.3
              6000                     1.126                               177.7                               444.2

> 含义：泵当量约 0.34–1.13 mm/h；仅靠泵排 200mm 需 177–590h，**远长于实际 96h** → 说明**自然排水/沟渠贡献不可忽略**，泵只是加速项。

## 所有不确定量以分布/区间表达（§四十九），**禁止固定假数**。
