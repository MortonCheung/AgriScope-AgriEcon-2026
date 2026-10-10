# M2_EVIDENCE_REGION_VALIDATION.md（R04 / §十八~二十二）

> 验证单位 = **evidence region（缓冲区）**，**不是**单个 100m 像元（避免空间自相关的假独立，§二十二）。

## 缓冲区敏感性（1/3/5 km）

 buffer_km  n_cells_in_buffer  median_rank_susceptibility  top10pct_coverage  top20pct_coverage  enrichment_ratio
       1.0               1012                       0.533              0.253              0.446             1.066
       3.0               8580                       0.640              0.336              0.472             1.311
       5.0              17645                       0.643              0.378              0.473             1.440

## 空间置换检验（3 km 缓冲，匹配面积随机背景，1000 次）

                   test  n_buffer  observed_median  null_median  p_one_sided  n_perm
spatial_permutation_3km      8580             0.64        0.488          0.0    1000

## 判读
- 观察项：**median rank** / **top10%·top20% coverage** / **enrichment ratio**；**不以 p 值为核心**（§二十）。
- 缓冲区半径 1→5km 时结论若稳定，说明“已知受淹区域相对富集于高易感区”较稳健；否则须报告不确定性。
- ⚠️ 证据点仅 6 个区域、空间误差 3–5km → 结论**只能作方向性一致性**，不能作功效性统计推断。
