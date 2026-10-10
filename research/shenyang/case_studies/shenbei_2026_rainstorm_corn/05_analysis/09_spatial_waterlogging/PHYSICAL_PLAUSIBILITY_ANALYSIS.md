# PHYSICAL_PLAUSIBILITY_ANALYSIS.md（P4-15/42）

对每个“明确受淹”证据点取 **3 km 邻域**的耕地网格均值，与全区耕地背景比较。

            variable expected_direction  mean_near_flooded  mean_background        diff  z_diff  direction_consistent
           elevation                  −             51.817           55.111   -3.293764  -0.189                  True
               slope                  −              0.628            0.927   -0.298951  -0.221                  True
        local_relief                  −              2.306            3.309   -1.003695  -0.217                  True
    depression_depth                  +              0.283            0.248    0.035223   0.080                  True
   flow_accumulation                  +              3.468            5.680   -2.212702  -0.126                 False
                hand                  −              0.018            0.101   -0.083022  -0.223                  True
                 twi                  +              9.491            9.303    0.188391   0.206                  True
   dist_mapped_water                  +           4991.736         4036.262  955.473552   0.310                  True
   dist_mapped_river                  +           7493.370         6262.446 1230.923424   0.406                  True
dist_mapped_drainage                  +           7969.513         6678.240 1291.272313   0.255                  True

## 结论
- 方向与机制一致的地形/水文变量：**9/10**。
- 需注意：证据点空间误差 3–5 km，与邻域半径同量级 → 该比较**只能看方向，不能作显著性结论**。
- 若多数变量方向一致，说明“地形—水文易感性”思路与真实受淹地点**方向相符**；否则需谨慎。
