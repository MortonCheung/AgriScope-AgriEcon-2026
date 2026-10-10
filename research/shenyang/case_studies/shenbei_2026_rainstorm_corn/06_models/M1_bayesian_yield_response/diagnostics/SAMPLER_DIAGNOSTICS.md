# SAMPLER_DIAGNOSTICS.md（P3-07）

- 最大 R-hat = **1.0067**（判据 ≤1.01）
- 最小 bulk ESS = **573**
- 接受率：M0=0.280；M1_S0=0.277；M1_S1=0.261；M1_S2=0.307

model        param   rhat  ess_bulk  ess_tail
   M0        alpha 1.0009  1028.800    1980.8
   M0       beta_T 1.0029  1063.900    1593.8
   M0       beta_R 1.0013   833.400    1865.0
   M0    log_sigma 1.0030  1151.700    2927.4
   M0 _accept_rate    NaN     0.280       NaN
M1_S0        alpha 1.0000  1810.800    2458.0
M1_S0       beta_T 1.0000   923.900    1797.9
M1_S0       beta_R 1.0037   976.100    1506.6
M1_S0    log_sigma 1.0015   900.500    1925.1
M1_S0 _accept_rate    NaN     0.277       NaN
M1_S1        alpha 1.0009  1745.000    2256.3
M1_S1       beta_T 1.0013   901.200    1593.0
M1_S1       beta_R 1.0021  1012.400    1887.5
M1_S1    log_sigma 1.0018   969.200    1848.0
M1_S1 _accept_rate    NaN     0.261       NaN
M1_S2        alpha 1.0000  1558.700    2182.3
M1_S2       beta_T 1.0019   795.400    1714.4
M1_S2       beta_R 1.0036   573.400     938.0
M1_S2    log_sigma 1.0067   973.700    2121.6
M1_S2 _accept_rate    NaN     0.307       NaN

## 判据
- R-hat ≤ 1.01；bulk/tail ESS 合理；无 divergence（本采样器无 HMC divergence，以接受率与 R-hat/ESS 作为收敛证据）。

**结论：收敛合格**
