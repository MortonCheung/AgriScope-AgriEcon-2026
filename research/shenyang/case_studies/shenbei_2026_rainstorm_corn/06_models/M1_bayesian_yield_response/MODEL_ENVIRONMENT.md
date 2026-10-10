# MODEL_ENVIRONMENT.md

| 项 | 值 |
|---|---|
| Python | 3.9.6 |
| platform | macOS-15.7.4-arm64-arm-64bit |
| numpy | 2.0.2 |
| pandas | 2.3.3 |
| scipy | 1.13.1 |
| random_seed | 20260922 |
| sampler | 自实现自适应随机游走 Metropolis（Haario 协方差自适应），4 链 |
| chains / warmup / draws | 4 / 5000 / 5000 |
| target_accept（等价） | 通过自适应步长使接受率落在 ~0.234 附近（见 sampler_diagnostics.csv） |

## 为什么不用 PyMC
当前环境 **Python 3.9.6**，PyMC 5.x 要求 Python ≥3.10；PyMC 4.x 与 numpy 2.0 不兼容。
故按规格“**优先复用/局部安装**”的原则，**在同一进程内自实现贝叶斯采样器**，
并提供 **split-R-hat / bulk ESS / tail ESS / 接受率** 全套诊断，保证**可复现**。
本偏离已在 `PHASE_3_RESEARCH_REPORT.md` 中明确说明。
