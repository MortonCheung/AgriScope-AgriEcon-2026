# M2_SENSITIVITY.md（P4-66）

           factor   level  mean_pct_at_pos  frac_above_median  sar_anomaly_frac  overlap_with_top_quartile_susc
      grid_size_m      50            0.499                0.5               NaN                             NaN
      grid_size_m     100            0.547                0.5               NaN                             NaN
      grid_size_m     250            0.546                0.5               NaN                             NaN
sar_threshold_pct       5              NaN                NaN            0.0501                          0.0104
sar_threshold_pct      10              NaN                NaN            0.1000                          0.0221
sar_threshold_pct      20              NaN                NaN            0.2000                          0.0451
    drainage_vars    with            0.547                NaN               NaN                             NaN
    drainage_vars without            0.415                NaN               NaN                             NaN
        dem_res_m      30            0.536                NaN               NaN                             NaN
        dem_res_m      90            0.574                NaN               NaN                             NaN

## 结论
- 主分辨率选 **100 m**（与 DEM 30m、SAR~10m、soil 缺失相称；§39 不假精细）。
- 报告各因素下“已知正样本处易感性百分位”是否稳定；若随尺度/阈值大幅漂移，须在结论中标注。
