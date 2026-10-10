# M2_RESOLUTION_SENSITIVITY_REAUDIT.md（R05 / §二十三）

对 Phase 4 曾报告的 网格 50/100/250 m 与 DEM 30/90 m 敏感性**重新审计**，并补齐规范要求的四项比较：**rank correlation / High·VeryHigh overlap / known-positive enrichment / spatial pattern agreement**。

## 设定间 Spearman 秩相关（各设定秩，采样到同一 42,473 个 100m 单元）

                 w_equal  w_terrain_emph  w_drainage_emph  w_dep_hand_emph  grid_50m  grid_100m  grid_250m  dem_90m
w_equal            1.000           0.938            0.963            0.938     0.928      1.000      0.894    0.970
w_terrain_emph     0.938           1.000            0.847            0.951     0.882      0.938      0.814    0.904
w_drainage_emph    0.963           0.847            1.000            0.859     0.909      0.963      0.915    0.950
w_dep_hand_emph    0.938           0.951            0.859            1.000     0.868      0.938      0.809    0.893
grid_50m           0.928           0.882            0.909            0.868     1.000      0.928      0.855    0.910
grid_100m          1.000           0.938            0.963            0.938     0.928      1.000      0.894    0.970
grid_250m          0.894           0.814            0.915            0.809     0.855      0.894      1.000    0.913
dem_90m            0.970           0.904            0.950            0.893     0.910      0.970      0.913    1.000

## High·VeryHigh（top 20%）重叠 —— Jaccard

                 w_equal  w_terrain_emph  w_drainage_emph  w_dep_hand_emph  grid_50m  grid_100m  grid_250m  dem_90m
w_equal            1.000           0.703            0.840            0.674     0.780      1.000      0.772    0.861
w_terrain_emph     0.703           1.000            0.621            0.754     0.654      0.703      0.589    0.662
w_drainage_emph    0.840           0.621            1.000            0.598     0.761      0.840      0.825    0.833
w_dep_hand_emph    0.674           0.754            0.598            1.000     0.622      0.674      0.584    0.638
grid_50m           0.780           0.654            0.761            0.622     1.000      0.780      0.708    0.764
grid_100m          1.000           0.703            0.840            0.674     0.780      1.000      0.772    0.861
grid_250m          0.772           0.589            0.825            0.584     0.708      0.772      1.000    0.792
dem_90m            0.861           0.662            0.833            0.638     0.764      0.861      0.792    1.000

## 各设定的“已知正样本富集”与相对基准一致度

        setting  buffer_median_rank  enrichment_vs_background  top20_coverage  spearman_vs_equal  top20_jaccard_vs_equal
        w_equal               0.674                     1.387           0.425              1.000                   1.000
 w_terrain_emph               0.651                     1.343           0.390              0.938                   0.703
w_drainage_emph               0.579                     1.174           0.441              0.963                   0.840
w_dep_hand_emph               0.717                     1.493           0.384              0.938                   0.674
       grid_50m               0.679                     1.401           0.416              0.928                   0.780
      grid_100m               0.674                     1.387           0.425              1.000                   1.000
      grid_250m               0.670                     1.368           0.432              0.894                   0.772
        dem_90m               0.694                     1.424           0.432              0.970                   0.861

## 空间格局一致性
- 在多设定下秩极差 <0.20 的单元占比 = **0.616**（口径：格局稳定比例）。

## 判读
- 与 Phase 4 的一致性：Phase 4 只报告了“正样本处百分位 0.50–0.57”，**未给秩相关/重叠/格局一致性**；本轮补齐后发现：**同一分辨率家族内（50/100/250m、DEM30/90m）一致度较高**，而**权重族之间**（terrain vs drainage 强调）差异更明显。
- ⚠️ 结论：M2 对**分辨率**较稳健，对**权重族**更敏感 —— 这正是 §二十五 稳定性地图要表达的内容。
