# HRI_REPORT — 跟风种植风险指数 v1

## 1. 定义与边界

> HRI = 「可观测市场信号所形成的扩种诱因强度」（0-100），**不是农民一定会扩种的概率**，也没有监督标签。

组件（全部 past-only 历史分位 → 0-100）：
1. price_level：当前价在同季历史分位（same_season → same_month → expanding 逐级回退）
2. momentum：price_momentum_30 的历史分位
3. rise：continuous_rise_days 历史分位
4. volatility：volatility_30 历史分位（高波动=市场不稳定）
5. volume：volume_percentile（**仅沈阳**，单位未知，仅相对市场活跃度）
6. area：上一年面积增速（仅当城市×作物精确匹配；蔬菜无 → 该组件自动剔除并重新归一化权重）

风险等级阈值来自自身历史分布（expanding P50/P75/P90），不使用人为 30/60/80。

## 2. 权重方案与敏感性

监管原则：缺失组件不填 0，而是 **Σ(w·score)/Σ(available w)** 重新归一化。

| comparison | spearman | level_agreement | n |
|---|---|---|---|
| equal_vs_conceptual | 0.945 | 0.802 | 13830 |
| equal_vs_entropy | 0.948 | 0.763 | 13830 |
| conceptual_vs_entropy | 0.913 | 0.699 | 13830 |
| conceptual_weight_jitter_20pct | 0.997 | NA | 13830 |

> 方案：Equal / Conceptual（价格位置 .30、动能 .25、连涨 .15、波动 .15、量 .10、面积 .05）/ Entropy（训练窗口 2021-2023 计算后固定）。

## 3. 量化验证：高 HRI 之后的真实价格表现（非因果）

| window_days | n_high | n_low | high_mean_fwd_return | low_mean_fwd_return | high_median_fwd_return | low_median_fwd_return | high_p_down | low_p_down | high_mean_worst | low_mean_worst | mannwhitney_p | level | n | level_mean_fwd_return | level_p_down | level_mean_worst |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 30 | 699.0000 | 6827.0000 | -0.0477 | 0.0602 | -0.0860 | 0.0000 | 0.6123 | 0.4964 | -0.1681 | -0.1176 | 0.0000 | nan | NA | NA | NA | NA |
| 30 | NA | NA | NA | NA | NA | NA | NA | NA | NA | NA | NA | low | 6359.0000 | 0.0657 | 0.4795 | -0.1151 |
| 30 | NA | NA | NA | NA | NA | NA | NA | NA | NA | NA | NA | medium | 3182.0000 | 0.0463 | 0.5216 | -0.1354 |
| 30 | NA | NA | NA | NA | NA | NA | NA | NA | NA | NA | NA | high | 1891.0000 | 0.0189 | 0.5464 | -0.1383 |
| 30 | NA | NA | NA | NA | NA | NA | NA | NA | NA | NA | NA | very_high | 1208.0000 | -0.0022 | 0.5614 | -0.1480 |
| 60 | 691.0000 | 6747.0000 | -0.0749 | 0.1199 | -0.1257 | 0.0000 | 0.6440 | 0.4885 | -0.2395 | -0.1784 | 0.0000 | nan | NA | NA | NA | NA |
| 60 | NA | NA | NA | NA | NA | NA | NA | NA | NA | NA | NA | low | 6359.0000 | 0.1225 | 0.4835 | -0.1750 |
| 60 | NA | NA | NA | NA | NA | NA | NA | NA | NA | NA | NA | medium | 3182.0000 | 0.0943 | 0.4979 | -0.1992 |
| 60 | NA | NA | NA | NA | NA | NA | NA | NA | NA | NA | NA | high | 1891.0000 | 0.0516 | 0.5527 | -0.2067 |
| 60 | NA | NA | NA | NA | NA | NA | NA | NA | NA | NA | NA | very_high | 1208.0000 | -0.0082 | 0.5750 | -0.2130 |
| 90 | 686.0000 | 6669.0000 | -0.1506 | 0.1831 | -0.1852 | 0.0216 | 0.7536 | 0.4725 | -0.3086 | -0.2180 | 0.0000 | nan | NA | NA | NA | NA |
| 90 | NA | NA | NA | NA | NA | NA | NA | NA | NA | NA | NA | low | 6359.0000 | 0.1878 | 0.4806 | -0.2159 |
| 90 | NA | NA | NA | NA | NA | NA | NA | NA | NA | NA | NA | medium | 3182.0000 | 0.1229 | 0.4992 | -0.2442 |
| 90 | NA | NA | NA | NA | NA | NA | NA | NA | NA | NA | NA | high | 1891.0000 | 0.0457 | 0.5674 | -0.2604 |
| 90 | NA | NA | NA | NA | NA | NA | NA | NA | NA | NA | NA | very_high | 1208.0000 | -0.0578 | 0.6701 | -0.2735 |

## 4. 真实跟风案例（定性证据，不做准确率宣称）

| event_id | year | city | crop | trigger_price_event | planting_expansion | supply_change | price_outcome | market_outcome | evidence_type | source | source_url | source_text | confidence | access_date |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| HRD-2023-BAICAI | 2023 | 锦州 | 大白菜 | 2022年大白菜等『大路菜』价格处于高位 | 2023年农户种植意愿较强，北方冷凉蔬菜产区有所扩种；11月初全国蔬菜在田面积同比增加1.2% | 秋季天气偏暖，大白菜单产增加约20%，供给总量大 | 2023年11月新发地大白菜批发价低至0.55元/公斤，同比下跌56%；一度较近三年同期低30%以上，个别产区跌破成本 | 局地阶段性卖难/滞销 | 官方市场分析 + 主流媒体 | 农业农村部蔬菜市场分析预警团队 张晶；经济日报/中国经济网 | http://www.ce.cn/cysc/sp/info/202312/11/t20231211_38824047.shtml | 去年大白菜、圆白菜、白萝卜等『大路菜』价格处于高位，今年种植意愿较强…均有所扩种…11月份河北唐山、辽宁锦州和河北廊坊大白菜集中上市，批发价低至每公斤0.55元，同比下跌56% | 高 | 2026-10-04 |
| HRD-2024-TOMATO-LN | 2024 | 辽宁(省域) | 西红柿 | （反向案例）2024年种植面积缩减 | 2024年辽宁省西红柿种植面积有所缩减（收缩而非扩张） | 供给减少、果型品质优势明显 | 2024年第44周辽宁省西红柿批发均价5.31元/公斤，环比上涨9.03%，同比上涨72.96% | 价格显著高于上年 | 省级官方价格监测简讯 | 辽宁省农业农村厅 2024年第44周主要蔬菜产品价格简讯 | https://nync.ln.gov.cn/nync/index/zwgk/zszdgz/ncpxx/lnsnzyscpzjg/2024110614385049055/index.shtml | 今年我省西红柿种植面积有所缩减，农户普遍反映结果后果型表现佳、品质优势明显，因此近期西红柿批发价格持续较高，并且涨幅明显 | 高（省级官方明确表述） | 2026-10-04 |
| HRD-2024-LENGPENG-LN | 2024 | 辽宁(省域) | 设施蔬菜(冷棚) | 近年蔬菜种植收益较高 | 辽宁省内冷棚扩大面积较大，农户对种植蔬菜类经济作物兴趣较高 | 蔬菜整体上货量过饱和，产能相对过剩 | 2024年第25周省内蔬菜批发价格指数45.38，环比下降6.08%，同比下降20.91% | 价格整体下行 | 省级官方价格监测简讯 | 辽宁省农业农村厅 2024年省内第25周主要蔬菜品种市场价格简讯 | https://nync.ln.gov.cn/nync/index/zwgk/zszdgz/ncpxx/lnsnzyscpzjg/2024062816430638005/index.shtml | 近些年来，辽宁省内冷棚扩大面积较大，农户对于种植蔬菜类经济作物兴趣较高，因此整体蔬菜上货量过饱和，产能相对过剩。预计下周价格整体以降为主 | 高（省级官方明确表述） | 2026-10-04 |
| HRD-2022-SY-MECHANISM | 2022 | 沈阳 | 蔬菜(通用) | 市场上出现供不应求时菜价上涨 | 菜农容易盲目扩大种植面积 | 下一季市场过度饱和 | 价格下跌 | 供过于求→价格下跌（机制描述，非单一事件） | 政府调研报告（机制性描述） | 沈阳市价格监测局 和平区蔬菜市场专项调研（省发改委发布） | https://fgw.ln.gov.cn/fgw/xxgk/jgjc/fxyc/BFDE92662276474D98CFE6497CCD2900/index.shtml | 信息不对称，蔬菜种植具有周期短回报快的显著特点，当市场上出现需大于供时，菜农容易盲目扩大种植面积，导致下一季市场过度饱和，价格下跌；当市场上出现供小于需时，菜农减少种植面积会导致下一季市场供应不足，价格上涨 | 中（机制描述，无具体量化事件） | 2026-10-04 |
| HRD-2023-VEG-NATIONAL | 2023 | 全国(含辽宁) | 大棚菜/大路菜 | 2022年大路菜价格高位 | 北方冷凉蔬菜产区以及山东、江苏等地均有所扩种 | 秋季耐储品种供给总量大，露地菜与冷棚菜同时上市 | 2023年11月28种蔬菜全国平均批发价4.58元/公斤，环比下跌5.8%，较近三年同期低5.2%；菠菜-26.6%、大白菜-26.4% | 价格持续探底，局地阶段性卖难 | 农业农村部市场分析 + 主流媒体 | 农业农村部蔬菜市场分析预警团队；经济日报 | https://caijing.chinadaily.com.cn/a/202312/11/WS65767bbba310c2083e4123de.html | 二是蔬菜种植面积增加…去年大白菜、圆白菜、白萝卜等『大路菜』价格处于高位，今年种植意愿较强，北方冷凉蔬菜产区以及山东、江苏等地均有所扩种 | 高（全国口径，辽宁为参与产区之一） | 2026-10-04 |

案例与 HRI 逻辑一致性：见 FINAL_MODEL_REPORT 的历史回放案例与 `evaluation/cases/replay_cases.json`。


## 5. Market Risk（独立模块）验证

| window_days | n_high | n_low | high_mean_worst_drawdown | low_mean_worst_drawdown | mannwhitney_p |
|---|---|---|---|---|---|
| 30 | 659 | 6760 | -0.1654 | -0.1130 | 0.0000 |
| 90 | 659 | 6555 | -0.2528 | -0.2109 | 0.0000 |

> Market Risk = 波动/回撤/区间宽度/下行空间/异常度；与 HRI 分离（详见 metrics/market_risk_validation.csv）。
