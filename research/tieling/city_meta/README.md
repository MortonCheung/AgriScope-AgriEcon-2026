# 铁岭城市数据包

本目录只整理数据，不包含研究结论。

## 数据分层

- `raw/`：城市相关原始数据副本/克隆
- `interim/`：从统一事实表中按城市过滤的数据
- `processed/`：已有城市级 marts / parquet 产物

## 当前正式数据

| 数据 | 行数 | 唯一日期 | 作物数 | 来源数 |
|---|---:|---:|---:|---:|
| disaster_algorithm | 11 | 10 | 0 | 1 |
| disaster_observed | 5 | 4 | 0 | 0 |
| input_cost | 842 | 281 | 0 | 1 |
| phenology | 4 | 4 | 2 | 2 |
| policy | 4 | 1 | 0 | 2 |
| price | 6,226 | 272 | 343 | 7 |
| production | 65 | 3 | 29 | 1 |
| soil | 2,083 | 2083 | 0 | 1 |
| weather | 2,083 | 2083 | 0 | 0 |
| weather_extra | 2,083 | 2083 | 0 | 0 |