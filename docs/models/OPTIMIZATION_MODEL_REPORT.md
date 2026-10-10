# OPTIMIZATION_MODEL_REPORT — 多目标优化与排序

## 1. 效用函数（透明三套权重）

| preference | ret | down | conf | market | herding | climate |
|---|---|---|---|---|---|---|
| conservative | 0.200 | 0.350 | 0.100 | 0.200 | 0.100 | 0.050 |
| balanced | 0.350 | 0.200 | 0.100 | 0.150 | 0.120 | 0.080 |
| aggressive | 0.500 | 0.100 | 0.050 | 0.150 | 0.120 | 0.080 |

- 标准化：收益/下行用**池内百分位**，风险量用 /100，置信度 /100（不混尺度）；
- `utility = w_ret·ret + w_down·down + w_conf·conf − (w_mr·MR + w_hr·HRI + w_cl·CL)`；
- 风险偏好只改权重（排序），客观量不变（测试 `test_risk_preference.py` 保证）。

## 2. Pareto 前沿（§12）

- 目标：profit_baseline ↑、profit_pessimistic ↑、confidence ↑、HRI ↓、market_risk ↓、climate_risk ↓；
- 示例集规模：23 个前沿方案；风格分布：

| pareto_style | n |
|---|---|
| balanced | 17 |
| best_downside | 2 |
| best_return | 4 |

## 3. 上市窗口优化（§16/§17）

- 显著性阈值来自回测 WAPE × 收入（本示例：241381.85 元）；
- 差异不显著 → **合并为区间**；示例推荐：2027-08-03 ~ 2027-08-12
  （等价窗口数 1）；
- 回避窗口：['2027-07-13', '2027-06-13']

## 4. 面积优化 + 盈亏平衡 v2 + 价格×亩产矩阵（§19/§49/§50）

- 建议面积：100.0 亩（容忍度 {'max_acceptable_loss': 125000.0, 'source': 'user'}）；
- 盈亏平衡：{'至少卖多少钱不亏': 0.1568, '亩产至少多少不亏': 65.7, '成本超过多少就不值得种': 30454.56}；
- 亏损区域占比：0.0（价格/亩产 ±20% 网格）；
- 说明：这是**经营风险约束下的建议面积**，不是生物学最优。

## 5. 排序稳定性（§15/§46）

| preference | n_draws | jitter | spearman_mean | spearman_p05 | topk_overlap_mean | top1_minus_top2_utility | n_within_0.02_of_best | stable |
|---|---|---|---|---|---|---|---|---|
| balanced | 200 | 0.100 | 0.999 | 0.999 | 1.000 | 0.001 | 3 | 是 |

| n_draws | input_jitter | spearman_mean | top1_retention_rate | topk_overlap_mean |
|---|---|---|---|---|
| 100 | 0.100 | 0.991 | 0.000 | 0.827 |

> 若 Top1 与 Top2 效用差 < 0.02 → 引擎输出"并列方案"提示，并在推荐置信度中扣分。
