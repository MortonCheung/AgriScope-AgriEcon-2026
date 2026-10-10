# MODEL_SPECIFICATION.md

## 结构
```
log(Y_t) = alpha + beta_T * Z(T_t) + beta_R * Z(R_t) + eps_t ,  eps_t ~ Normal(0, sigma)
```
- `Y_t` = 沈北玉米单产 (kg/ha)（**log 尺度**：保证正产量、系数≈比例变化、反事实差异易转百分比）
- `Z(T_t)` = 标准化时间趋势（训练样本均值/标准差）
- `Z(R_t)` = 标准化抽雄吐丝期主极端降水 `repro_precip_max_5d`（mm）
- 先验：`alpha,beta_T,beta_R,log sigma` 见 `scripts/m1_priors.py`（S0/S1/S2）

## 对照模型
- **M0**（Baseline，趋势模型）：`log(Y_t)=alpha+beta_T*Z(T_t)+eps_t`
- **M1**（趋势+极端降雨）：上式

## 标准化与数据泄漏防护
- **全样本正式模型**：使用 2018–2025 全样本均值/标准差。
- **LOYO**：**每一折仅用该折训练年份**计算均值/标准差（见 `76_p3_exact_loyo.py`），**绝不使用被留出年份**。

## 量纲与单位
- 单产 kg/ha；降水 mm；`beta_R` 的单位是“每 1 个训练标准差降水”对 `log` 单产的影响。
- 训练样本：`R`均值=78.6 mm，`R`标准差=41.0 mm；`T`均值=4.5，`T`标准差=2.449。
