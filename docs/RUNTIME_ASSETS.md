# 运行时资产语义（RC2）

`runtime/manifest.json` 是当前清单；真实数量由 `n_assets` 给出，不固定195。源码、模型、Registry、schema、prompt均记录路径、大小、SHA256和asset_type；路径不能越出仓库。大模型/历史数据不进Git，通过部署包恢复。

- `immutable`：Final权重/快照/事实数据、长期权重与index、Registry、schema、prompt、生产配置与运行代码。任何哈希或大小不符即失败，不能用`--refresh`消除。
- `generated`：Daily/Long-Horizon latest、派生特征、日志等。动态更新允许漂移且必须报告；required项缺失仍失败。只有这些资产可显式refresh。
- `external`：外部证据输入，可登记source/version；本地有固定digest时仍强校验，required缺失失败。
- `optional`：可选资产；缺失单独报告，存在时仍按digest校验。

类型由清单显式指定；不能只按目录放宽。即使放在data/processed中的pkl/Registry/schema/prompt仍必须immutable。验证器拒绝不认识/缺失类型、重复路径、目录越界及受保护资产标成generated。

```bash
python3 scripts/verify_assets.py
python3 scripts/verify_assets.py --refresh
# 以下只用于发布时显式重新冻结：不是日常校验，不可放进Daily cron
python3 scripts/freeze_runtime_manifest.py
```

Final冻结身份保持 `final_v1 / b19b187268ee92db`；长期bundle来自显式retrain，与historical evaluated models分开登记。运行推理先加载index校验model/config和每个pkl的SHA256。长期Job不fit，使用冻结历史+同口径Daily追加，版本包括training_data_version/runtime_data_version/method_registry_version/as_of/latest_data_date/generated_at。

长期快照在data/processed/long_horizon/snapshots，latest与按日期文件原子写；history/日期/hash.json保存每份发行预测，供将来核验真正未见结果。后端比较Daily最新日期并暴露LONG_HORIZON_STALE，不能以generated_at冒充最新观测日期。

部署包由scripts/build_deploy_bundle.py生成，包含Git源码、必需运行资产和前端dist，排除.env/LLM调用缓存/node_modules。不可移动rc1，回滚使用完整旧bundle，不能覆盖历史事实。
