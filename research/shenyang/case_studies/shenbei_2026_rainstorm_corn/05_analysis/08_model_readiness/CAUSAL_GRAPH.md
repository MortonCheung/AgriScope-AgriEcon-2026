# CAUSAL_GRAPH.md — 因果结构图（P2-14）

> 每条边标注证据状态：`DATA_SUPPORTED / LITERATURE_SUPPORTED / ASSUMED / UNKNOWN`。
> 这是后续反事实模拟的骨架。

## 1. 主链（现实世界）

```
Weather ──▶ Waterlogging ──▶ CropStress ──▶ Yield ──▶ Production ──▶ EconomicImpact
   ▲            ▲
   │            │
AntecedentSoilMoisture ──┘
```

### 变量与节点定义

| 节点 | 定义 | 本案例数据状态 |
|---|---|---|
| Weather | 生育期降水/温度/极端（含事件日） | ✅ 有（ERA5，D 级） |
| AntecedentSoilMoisture | 暴雨前土壤含水量/前期累计降水 | 🟡 前期累计降水有；ERA5-Land 土壤含水量待并入 |
| Waterlogging | 农田积水范围/深度/历时 | 🔴 仅定性/个案（无全区场） |
| CropStress | 生育阶段胁迫（抽雄-吐丝期渍涝） | 🟡 物候暴露可判（模型估计） |
| Yield | 玉米单产 | ✅ 有（2018–2025，A/B） |
| Production | 总产 = 面积 × 单产 | ✅ 关系确定 |
| EconomicImpact | 农业经济影响 | 🔴 无价格/产值数据 |

## 2. 干预支链

```
Intervention ──▶ WaterloggingDuration ──▶ CropStress（减弱）
(warning/pumps/drainage)
```

| 节点 | 数据状态 |
|---|---|
| Intervention | ✅ 时间线 + 个案泵数（E/M 级） |
| WaterloggingDuration | 🔴 仅个案（八间房村 ~4 天）；全区缺 |
| CropStress 减弱 | 🔴 无定量 |

## 3. 边与证据状态

| 边 | 状态 | 依据 |
|---|---|---|
| Weather → Waterlogging | **DATA_SUPPORTED（定性强）/ 定量 UNKNOWN** | 官方确认低洼农田渍涝；缺积水范围观测 |
| AntecedentSoilMoisture → Waterlogging | **ASSUMED** | 官方“土壤含水率趋于饱和”定性；无逐日饱和指数 |
| Waterlogging → CropStress | **LITERATURE_SUPPORTED** | 玉米抽雄-吐丝期渍涝敏感（作物农学 + 夏玉米淹水文献） |
| CropStress → Yield | **LITERATURE_SUPPORTED（仅先验）** | 夏玉米淹水-减产参数（黄淮海，非东北春玉米） |
| Yield → Production | **DATA_SUPPORTED** | 恒等式，且面积/单产/总产内部自洽（相对差<0.01%） |
| Production → EconomicImpact | **UNKNOWN** | 无价格/产值 |
| Intervention → WaterloggingDuration | **DATA_SUPPORTED（个案）** | 八间房村 7-14→7-18 排净 8000 亩 |
| Weather 直接 → Yield（不经积水） | **ASSUMED** | 需在模型中显式考虑，避免遗漏路径 |

## 4. 识别的核心障碍（写进骨架供 Phase 3 用）

1. **Waterlogging 无全区可观测量** → 主链中间节点是“隐变量”，只能由降雨+地形代理。
2. **Yield→天气的混杂**：时间趋势（技术）、生育期气候、灌溉/管理均未观测。
3. **干预无对照** → Intervention→Duration→损失 的反事实不可识别。
4. **样本**：单区 8 年，无法用数据估计结构参数 → 必须走 **机理 + 文献先验 + 遥感 + Bayesian/Monte Carlo** 混合路线。

## 5. 建议的 Phase 3 结构式因果模型（SCM）

```text
Waterlogging_extent_t = f(precip_t, antecedent_soilmoisture_t, DEM, drainage_capacity)   [B 模型]
Yield = f(time, repro_precip_extreme, Waterlogging_duration)                             [A 模型，小样本→GAM/岭]
Intervention → Waterlogging_duration 缩短系数                                             [C 模型，Monte Carlo 参数范围]
Counterfactual: 固定模型，替换 Weather/Intervention 变量 → Y_do(...)                       [D 模型]
```
每条边在 Phase 3 必须重新标注其**识别假设是否满足**。
