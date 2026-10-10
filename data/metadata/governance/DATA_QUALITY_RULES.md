# DATA_QUALITY_RULES — 数据质量评分规则（明确、可计算）

## 一、单元格/表级质量等级（不再随意打 A/B/C/D）

每张标准表按 5 维打分，每维 0–5 分，权重如下：

| 维度 | 权重 | 5 分 | 3 分 | 1 分 |
|---|---|---|---|---|
| source_quality | 0.30 | S | B/C | P/未知 |
| temporal_coverage | 0.25 | ≥5 年连续 | 2–5 年 | <1 年 / 稀疏 |
| granularity | 0.20 | city×crop×time | city×time 或 province×crop | province 聚合 |
| missingness | 0.15 | <5% | 5–30% | >30% |
| semantic_match | 0.10 | 字段语义完全对应需求 | 部分对应 | 语义偏离 |

`QUALITY_SCORE = Σ(维度分 × 权重)`（0–5）。
`QUALITY_GRADE`：≥4.2 → **A**；3.4–4.2 → **B**；2.4–3.4 → **C**；<2.4 → **D**。

## 二、模块 readiness（0–100%）

模块由若干 requirement 组成，每条 requirement 有 `priority`（P0/P1/P2）与 `coverage（0–1）`：

```
module_readiness = 100 × Σ(priority_weight × coverage) / Σ(priority_weight)
priority_weight: P0=3, P1=2, P2=1
```

输出到 `06_requirements/READINESS_FINAL.csv`。**必须由脚本计算，不得手填。**

## 三、QC 必检项（写入 05_quality/）

- 重复主键 / 空主键
- 日期非法、超出声明的 date_range
- 单位非法（不在 UNIT_REGISTRY）
- 负价格 / 负面积 / 负产量
- 极端异常值（3×IQR，仅标记不删）
- 作物映射失败 / 城市映射失败
- 来源缺失（`source_id` 为空）
- `is_proxy=true` 但未标 `proxy_type`
- `is_derived=true` 但未给 `conversion_rule` / 公式
- NDVI 范围检查（−1 ≤ NDVI ≤ 1）
- 产量校验：`yield ≈ production / area`（容差 ±10%，超差 flag）
- 粮食合计 ≈ 分项之和（年鉴校验）

## 四、失败记录保留

任何 FAIL/WARNING 一律保留并登记，禁止为"报告漂亮"删除。
