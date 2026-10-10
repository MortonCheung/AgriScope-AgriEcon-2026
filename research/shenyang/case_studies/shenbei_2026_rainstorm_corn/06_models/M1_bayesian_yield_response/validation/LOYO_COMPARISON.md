# LOYO 对比结论

model  MAE_kg_ha  RMSE_kg_ha  mean_log_predictive_density  coverage50  coverage80  coverage95  worst_year
   M0      697.1       749.3                        0.918        12.5        25.0        62.5        2025
M1_S0      707.7       776.5                        0.836        25.0        37.5        62.5        2025
M1_S1      717.0       799.3                        0.814        25.0        37.5        75.0        2025
M1_S2      734.3       809.2                        0.798        25.0        37.5        75.0        2025

## M1 vs M0

- M1_S0: ΔMAE=+10.6；ΔRMSE=+27.2；ΔlogPD=-0.082
- M1_S1: ΔMAE=+19.9；ΔRMSE=+50.0；ΔlogPD=-0.104
- M1_S2: ΔMAE=+37.2；ΔRMSE=+59.9；ΔlogPD=-0.120
