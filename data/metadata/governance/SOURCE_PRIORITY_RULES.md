# SOURCE_PRIORITY_RULES — 来源优先级与采用规则

## 来源等级（S/A/B/C/P）

| 等级 | 定义 | 示例 |
|---|---|---|
| **S** | 政府官方、统计年鉴、官方监测、官方市场 | 省/市统计局、农业农村局、发改委成本调查、气象局、应急局、水利厅、金融监管局、政府公报/答复 |
| **A** | 权威科研机构、官方公共平台、遥感/气候再分析 | ERA5/ERA5-Land、Sentinel-2/MODIS、Copernicus、CNKI 正式论文、农科院/高校公开研究数据 |
| **B** | 行业协会、大型批发市场、可信行业数据库 | 批发市场官网、寿光指数、卓创公开部分 |
| **C** | 可信新闻、案例、论文二次引用 | 辽宁日报、新华、人民网、地方媒体（须保留原文片段） |
| **P** | Proxy（代理） | 邻市数据、区域代理、总量代理、商户报价 |

## 采用规则（同一 metric 冲突时的裁决顺序）

```
S > A > B > C > P
且：
- 空间口径越贴近目标（city > province > region）越优先
- 时间口径越贴近目标频率越优先（但不得跨频率伪造）
- 观测(observation) > 派生(derived, 有公式) > 代理(proxy)
- 同等级下：更新版本 > 旧版本；样本量/覆盖更大者优先
```

## 硬性禁止

1. 省级数据不得冒充城市数据（必须标 `geo_level=province`）。
2. 邻市数据不得冒充本地（必须标 `is_proxy=true` + `proxy_type=neighboring_city`）。
3. proxy 不得冒充 observation（必须 `is_proxy=true`）。
4. 不同 `price_level`（wholesale / retail / market_average / farm_gate / supermarket / merchant_quote）**禁止直接拼接成一条序列**。
5. 未标注 `source_id` 的记录**不得进入** `02_standardized/` 及之后的任何层。
6. 商户报价（merchant_quote）不得进入正式价格模型。

## source_id 命名

`SRC-<组织缩写>-<主题>-<序号>`，例如 `SRC-LN-NYNC-VEG-WEEKLY`、`SRC-AWS-S2L2A`。
唯一登记于 `SOURCE_REGISTRY.csv`，全库引用。
