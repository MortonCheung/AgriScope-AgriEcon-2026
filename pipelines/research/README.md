# AgriScope 研究流水线（六城农业市场与风险研究）

> 定位：`AgriScope/pipelines/` 下的研究流程。输入为只读数据仓库（`models/`、`data/`），
> 输出为 `data/research/<city>/` 与 `data/research/cross_city/`，最终经 `publishing` 进入
> `AgriScope/runtime/research/` 供前端"研究中心"消费。
>
> 冻结架构约定：本目录只放**研究流程代码**，不放数据、不放报告。

```
AgriScope/pipelines/research/
├── README.md
├── config/
│   ├── cities.yaml      # 六城：主价格来源、层级、时间窗口、核心作物
│   ├── crops.yaml       # crop_raw → crop_std 受控映射 + 分类
│   └── analysis.yaml    # 全局统计参数（seed/alpha/HAC lags/去季节化窗口/覆盖阈值）
├── lib/
│   ├── paths.py         # 唯一路径来源（只读输入 / 研究输出）
│   ├── loaders.py       # 六城统一数据载入 + crop_raw 标准化 + 分层
│   ├── stats.py         # HAC OLS / BH-FDR / bootstrap / STL（与沈阳 v2 方法一致）
│   ├── plotting.py      # 中文字体绘图工具
│   └── contract.py      # article.json / 证据链 契约（对齐沈阳 A01）
└── modules/
    ├── a01_market_time.py
    ├── a02_weather_market.py
    ├── a03_lag_accumulation.py
    ├── a04_extreme_events.py
    ├── a05_crop_heterogeneity.py
    ├── a06_predictability.py
    ├── a07_production_structure.py
    ├── a08_robustness.py
    └── a09_city_special.py
```

## 运行

```
cd /Users/morton_cheung/Desktop/比赛/大数据分析/AgriScope
python3 -m pipelines.research.run_research --module A01 --cities all
python3 -m pipelines.research.run_research --module A01 --cities chaoyang
```

## 纪律（与沈阳 v2 一致）

1. 作物字段一律用 `crop_raw`，经 `crops.yaml` 受控映射；禁用原始 `crop_standard`。
2. 价格按 `price_level` 分层，主分析只取该城主层级；**不跨层级混合**。
3. 成交量单位未知（沈阳），禁写"吨"；五城无成交量。
4. 去季节化用**严格无未来信息**基线（仅用严格更早年份）。
5. 双向检验：BH-FDR 校正家族，同时报原始 p 与 q；报告 AR(1)/n_eff。
6. 阴性结果正式报告；不写因果；不夸大效应量。
7. 数据不支持则显式写 `NOT_SUPPORTED_BY_CURRENT_DATA`。