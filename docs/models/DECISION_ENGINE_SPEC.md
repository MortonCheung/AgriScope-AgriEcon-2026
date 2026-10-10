# DECISION_ENGINE_SPEC — Decision Engine v1 接口规范

## 1. 调用方式

```python
import sys; sys.path.insert(0, "models/src")
from decision_engine.engine.engine import DecisionEngine

engine = DecisionEngine()                 # 可选 as_of="2025-06-30" 用于历史回放
result = engine.evaluate_plan({ ... })   # 见下方示例
ranking = engine.compare_plans([planA, planB, planC])
```

### 输入

| 字段 | 含义 | 必填 |
|---|---|---|
| city | 城市（沈阳/朝阳/锦州/大连/铁岭/丹东） | 是 |
| crop | 作物 | 是 |
| plant_date / harvest_date | 计划种植 / 上市日期 | 是 |
| area_mu | 面积（亩） | 是 |
| cost_per_mu | 亩均成本（元/亩，**用户输入**，项目无历史蔬菜成本） | 是 |
| expected_yield_per_mu | 预计亩产（kg/亩，**用户输入**） | 是 |
| risk_preference | conservative / balanced / aggressive | 否（默认 balanced） |

### 输出 schema（与任务书 §47 一致）

city / crop / price{low,mid,high,unit,method,is_calibrated_interval} / profit{break_even_price,pessimistic,baseline,optimistic}
/ risk{market,herding,climate,production} / decision{score,grade,risk_preference} / confidence{score,grade}
/ reasons[] / evidence[] / limitations[]

**所有数字来自模型/规则/公式/历史数据，无 LLM 生成。**

## 2. 完整示例


### 示例 1

输入：

```json
{
  "city": "沈阳",
  "crop": "西红柿",
  "plant_date": "2026-10-10",
  "harvest_date": "2027-01-10",
  "area_mu": 80,
  "cost_per_mu": 5200,
  "expected_yield_per_mu": 4500,
  "risk_preference": "balanced"
}
```

输出（节选）：

```json
{
  "status": "ok",
  "city": "沈阳",
  "crop": "西红柿",
  "risk_preference": "balanced",
  "price": {
    "low": 5.182580086580087,
    "mid": 6.142352941176472,
    "high": 8.991818181818182,
    "method": "seasonal_quantile(same_month_history)",
    "is_calibrated_interval": false
  },
  "profit": {
    "break_even_price": 1.1556,
    "pessimistic": 1449728.83,
    "baseline": 1795247.06,
    "optimistic": 2821054.55
  },
  "risk": {
    "market": 54.1,
    "herding": 57.3,
    "climate": 20.24
  },
  "decision": {
    "score": 78.6,
    "grade": "B",
    "risk_preference": "balanced",
    "components": {
      "expected_return": 100.0,
      "downside": 100.0,
      "market_risk": 45.9,
      "herding": 42.7,
      "climate": 79.8
    },
    "weights_used": {
      "expected_return": 0.35,
      "downside": 0.2,
      "market_risk": 0.2,
      "herding": 0.15,
      "climate": 0.1
    },
    "scores_by_preference": {
      "conservative": 77.5,
      "balanced": 78.6,
      "aggressive": 84.1
    },
    "score_stability": 0.934,
    "stability_note": "评分对风险偏好不敏感（稳定）"
  },
  "confidence": {
    "score": 86.2,
    "grade": "A"
  },
  "reasons": [
    "上市窗口（1月）历史同月价格 P10/P50/P90 = 5.18/6.14/8.99 元/kg（6 年 123 个观测，strictly past-only）",
    "盈亏平衡价 1.16 元/kg；历史 P50 比盈亏平衡高 431.5%",
    "基准情景（P50）净收益 1795247 元（盈利），ROI 431.6%",
    "跟风风险 HRI=57.3（medium），主导组件: rise=76.3, volatility=76.1",
    "市场风险=54.1（medium）",
    "历史同期气候暴露=20.24（16 年同窗口概率，非天气预报）",
    "综合决策评分 78.6（B，balanced）；结果置信度 86.2（A）"
  ]
}
```

### 示例 2

输入：

```json
{
  "city": "沈阳",
  "crop": "黄瓜",
  "plant_date": "2027-03-01",
  "harvest_date": "2027-06-10",
  "area_mu": 120,
  "cost_per_mu": 4800,
  "expected_yield_per_mu": 6000,
  "risk_preference": "conservative"
}
```

输出（节选）：

```json
{
  "status": "ok",
  "city": "沈阳",
  "crop": "黄瓜",
  "risk_preference": "conservative",
  "price": {
    "low": 2.4116842105263157,
    "mid": 2.8168421052631576,
    "high": 3.8561531100478468,
    "method": "seasonal_quantile(same_month_history)",
    "is_calibrated_interval": false
  },
  "profit": {
    "break_even_price": 0.8,
    "pessimistic": 1160412.63,
    "baseline": 1452126.32,
    "optimistic": 2200430.24
  },
  "risk": {
    "market": 63.8,
    "herding": 49.6,
    "climate": 24.36
  },
  "decision": {
    "score": 76.1,
    "grade": "B",
    "risk_preference": "conservative",
    "components": {
      "expected_return": 100.0,
      "downside": 100.0,
      "market_risk": 36.2,
      "herding": 50.4,
      "climate": 75.6
    },
    "weights_used": {
      "expected_return": 0.2,
      "downside": 0.3,
      "market_risk": 0.2,
      "herding": 0.15,
      "climate": 0.15
    },
    "scores_by_preference": {
      "conservative": 76.1,
      "balanced": 77.4,
      "aggressive": 83.0
    },
    "score_stability": 0.931,
    "stability_note": "评分对风险偏好不敏感（稳定）"
  },
  "confidence": {
    "score": 84.9,
    "grade": "A"
  },
  "reasons": [
    "上市窗口（6月）历史同月价格 P10/P50/P90 = 2.41/2.82/3.86 元/kg（6 年 122 个观测，strictly past-only）",
    "盈亏平衡价 0.80 元/kg；历史 P50 比盈亏平衡高 252.1%",
    "基准情景（P50）净收益 1452126 元（盈利），ROI 252.1%",
    "跟风风险 HRI=49.6（low），主导组件: price_level=65.0, volatility=63.5",
    "市场风险=63.8（high）",
    "历史同期气候暴露=24.36（17 年同窗口概率，非天气预报）",
    "综合决策评分 76.1（B，conservative）；结果置信度 84.9（A）"
  ]
}
```

### 示例 3

输入：

```json
{
  "city": "朝阳",
  "crop": "西红柿",
  "plant_date": "2027-04-01",
  "harvest_date": "2027-07-01",
  "area_mu": 60,
  "cost_per_mu": 4200,
  "expected_yield_per_mu": 5000,
  "risk_preference": "aggressive"
}
```

输出（节选）：

```json
{
  "status": "ok",
  "city": "朝阳",
  "crop": "西红柿",
  "risk_preference": "aggressive",
  "price": {
    "low": 4.282916666666668,
    "mid": 4.746470588235295,
    "high": 5.993636363636364,
    "method": "seasonal_quantile(same_month_history)",
    "is_calibrated_interval": false
  },
  "profit": {
    "break_even_price": 0.84,
    "pessimistic": 1032875.0,
    "baseline": 1171941.18,
    "optimistic": 1546090.91
  },
  "risk": {
    "market": 29.6,
    "herding": 40.5,
    "climate": 17.21
  },
  "decision": {
    "score": 89.8,
    "grade": "A",
    "risk_preference": "aggressive",
    "components": {
      "expected_return": 100.0,
      "downside": 100.0,
      "market_risk": 70.4,
      "herding": 59.5,
      "climate": 82.8
    },
    "weights_used": {
      "expected_return": 0.5,
      "downside": 0.15,
      "market_risk": 0.15,
      "herding": 0.1,
      "climate": 0.1
    },
    "scores_by_preference": {
      "conservative": 85.4,
      "balanced": 86.3,
      "aggressive": 89.8
    },
    "score_stability": 0.956,
    "stability_note": "评分对风险偏好不敏感（稳定）"
  },
  "confidence": {
    "score": 73.0,
    "grade": "B"
  },
  "reasons": [
    "上市窗口（7月）历史同月价格 P10/P50/P90 = 4.28/4.75/5.99 元/kg（6 年 122 个观测，strictly past-only）",
    "盈亏平衡价 0.84 元/kg；历史 P50 比盈亏平衡高 465.1%",
    "基准情景（P50）净收益 1171941 元（盈利），ROI 465.1%",
    "跟风风险 HRI=40.5（low），主导组件: volatility=54.7, momentum=54.5",
    "市场风险=29.6（low）",
    "历史同期气候暴露=17.21（17 年同窗口概率，非天气预报）",
    "综合决策评分 89.8（A，aggressive）；结果置信度 73.0（B）"
  ]
}
```


## 3. 方案对比

| city | crop | plant_date | harvest_date | area_mu | price_mid | break_even_price | profit_baseline | profit_pessimistic | roi_baseline | market_risk | hri | climate | score | grade | confidence | score_conservative | score_balanced | score_aggressive |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 朝阳 | 西红柿 | 2027-04-01 | 2027-07-01 | 60 | 4.746 | 0.840 | 1171941.180 | 1032875.000 | 4.651 | 29.600 | 40.500 | 17.210 | 89.800 | A | 73.000 | 85.400 | 86.300 | 89.800 |
| 沈阳 | 西红柿 | 2026-10-10 | 2027-01-10 | 80 | 6.142 | 1.156 | 1795247.060 | 1449728.830 | 4.316 | 54.100 | 57.300 | 20.240 | 78.600 | B | 86.200 | 77.500 | 78.600 | 84.100 |
| 沈阳 | 黄瓜 | 2027-03-01 | 2027-06-10 | 120 | 2.817 | 0.800 | 1452126.320 | 1160412.630 | 2.521 | 63.800 | 49.600 | 24.360 | 76.100 | B | 84.900 | 76.100 | 77.400 | 83.000 |

## 4. 科学边界（写死在引擎里）

- 价格区间未校准时标注 `scenario range`，不得称 prediction interval；
- 大连/铁岭/丹东返回 `insufficient_market_data` + 生产背景 + 气候暴露 + 低置信度（不硬造模型）；
- 风险偏好只影响效用权重，不改变客观 HRI/Market/Climate 数值；
- 置信度与决策评分分离（差方案也可以高置信）。
