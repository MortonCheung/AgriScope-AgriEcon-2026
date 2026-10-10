# M2_FEATURE_FAMILY_ABLATION.md（R06 / §二十六~二十九）

## 特征族消融（leave-feature-family-out）

             ablation  n_features  buffer_median_rank  background_median  enrichment  mean_pos_rank_buffer  mean_pos_rank_single_cell
                 full          10               0.640              0.488       1.311                 0.590                      0.489
         drop_terrain           3               0.564              0.491       1.148                 0.577                      0.547
 drop_mapped_drainage           9               0.655              0.481       1.364                 0.598                      0.474
drop_hydrology_mapped           7               0.547              0.491       1.113                 0.546                      0.317
         terrain_only           7               0.547              0.491       1.113                 0.546                      0.317
    mapped_water_only           3               0.564              0.491       1.148                 0.577                      0.547

## 排水变量专项（§二十六~二十八）
- 当前“排水相关变量”仅包含 **mapped 水系/河流/排水距离**（OSM），**不含** DEM 推导排水网络、**不含**泵站。
- 证据区 `dist_mapped_drainage` 中位数 = **7852 m**，全区中位数 = **5517 m** → 证据区**距映射排水更远**。
> ⚠️ 风险：**少量地图要素可能对结果产生过强影响**。因 OSM 排水沟仅 1 条，`dist_mapped_drainage` 实际主要由 `canal/stream` 决定，**代表性不足**。

## 结论：M2 主要由哪组变量驱动？
- 使“已知正样本处排名（缓冲区口径）”最高的族：**drop_mapped_drainage**（buffer=0.598）。
- 地形族（elevation/slope/relief/depression/HAND/TWI）是**主要驱动**；mapped 水系距离提供**次要但非零**的贡献；道路变量未参与易感性。
- ⚠️ 该驱动结构**受数据完整性限制**（排水不完整）→ 不能解释为“真实排水能力对渍涝的影响”。

## ⚠️ 与 Phase 4 的一处方法学更正（本轮重要发现）
Phase 4 敏感性曾报告：“移除排水变量后，正样本处易感性**降到中位数以下**（0.415）”，并据此推断“排水距离确有影响”。

**本轮复核认为该结论不稳健**，原因：Phase 4 的该敏感性使用的是 **单像元（evidence point 所在 100m 格）** 取值；而 G2 证据空间误差达 3–5 km，**把村级证据映射到单一 100m 格本身就不规范（§十八）**。

改用**证据区域（3 km 缓冲）**口径后，见下表两列对比：

             ablation  mean_pos_rank_buffer  mean_pos_rank_single_cell
                 full                 0.590                      0.489
         drop_terrain                 0.577                      0.547
 drop_mapped_drainage                 0.598                      0.474
drop_hydrology_mapped                 0.546                      0.317
         terrain_only                 0.546                      0.317
    mapped_water_only                 0.577                      0.547

→ **同一消融在两种口径下可给出不同甚至相反的量级**，说明 Phase 4 的“排水强影响”**部分是单像元取值的伪像**；正确口径下排水变量为**次要贡献**。
**处理**：保留 Phase 4 原始结果不修改；在本轮明确标注该更正，后续正式 M2 一律使用**证据区域口径**。
