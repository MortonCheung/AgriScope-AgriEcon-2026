# ENGINE_INTERFACE.md（R13 / §六十一~六十四）

## 模块链（相互独立，禁止单体硬编码）
```
simulate_weather() → simulate_waterlogging_M2() → simulate_duration_M4() → simulate_crop_damage_M3() → aggregate_outcome()
```
实现见 `engine.py`。**禁止**写一个 `run_parallel_world.py` 把公式全硬编码。

## 接口契约
| 生产者 | 输出字段 | 消费者 |
|---|---|---|
| M2 | `cell_id, susceptibility, waterlogging_state, confidence` | M3/M4 |
| M4 | `duration_distribution, peak_storage, drainage_end_time` | M3 |
| M3 | `yield_ratio_distribution, damage_fraction_distribution` | aggregation |
| aggregation | `region_loss_distribution` | 报告 |

## 缺字段处理（§六十四）
允许：`NULL` / `NOT_AVAILABLE` / `WAITING_FOR_DATA`
**禁止**：用假默认值让 pipeline “成功运行”。

`engine.py` 在缺 `m2_threshold` / `duration` / `m3_anchors` / 排水参数时**抛 MissingData**（状态 WAITING_FOR_DATA）。
