#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""M1′ 先验定义（S0/S1/S2）+ changelog。所有脚本从此处读取先验，确保口径一致。"""
import numpy as np

# 农业合理性锚点（用于设置 alpha/sigma 的量级）
ANCHOR_LOG_YIELD = float(np.log(8000.0))   # 沈北玉米单产约 8000 kg/ha 附近
ANCHOR_RESID_SD = 0.08                     # log 尺度年际残差量级（Phase2 观测 ~0.06-0.09）

PRIORS = {
    # S0 Skeptical：看到数据前，不假设极端降雨一定有大影响
    "S0": {
        "label": "Skeptical",
        "alpha": (ANCHOR_LOG_YIELD, 0.25),
        "beta_T": (0.0, 0.15),
        "beta_R": (0.0, 0.07),          # 以 0 为中心，允许正负
        "log_sigma": (float(np.log(ANCHOR_RESID_SD)), 0.45),
    },
    # S1 Direction-implied (weakly-informed)：仅来自机制方向（渍涝不利），
    #   明确标注：这不是可映射的数值文献先验（PRIOR_EVIDENCE_AUDIT 结论：无 Class A）
    "S1": {
        "label": "Direction-implied (weakly-informed; NOT a mapped literature prior)",
        "alpha": (ANCHOR_LOG_YIELD, 0.25),
        "beta_T": (0.0, 0.15),
        "beta_R": (-0.05, 0.13),        # 轻微负向，标准差很大（≈ ±13% 每 SD）
        "log_sigma": (float(np.log(ANCHOR_RESID_SD)), 0.45),
    },
    # S2 Wider/Discounted：把 S1 的信息削弱（均值减半、方差放大）
    "S2": {
        "label": "Discounted / Wider",
        "alpha": (ANCHOR_LOG_YIELD, 0.26),
        "beta_T": (0.0, 0.16),
        "beta_R": (-0.025, 0.15),
        "log_sigma": (float(np.log(ANCHOR_RESID_SD)), 0.45),
    },
}

PRIOR_CHANGELOG = """# PRIOR_CHANGELOG.md — 先验修改记录

> 纪律：每次先验修改必须在此登记，防止“看到 posterior 不喜欢再偷偷改 prior”。

| 版本 | 日期 | 旧 prior | 发现问题 | 新 prior | 修改原因 |
|---|---|---|---|---|---|
| v0.1 | 2026-09-22 | — | — | S0/S1/S2 初版（见 `scripts/m1_priors.py`） | 初版：S0 以 0 为中心；S1 仅方向弱信息（文献无 Class A 可映射）；S2 削弱 S1 |
| v0.2 | 2026-09-22 | S0 beta_R(0,0.08)/ls(.,0.5); S1 bR(-0.05,0.15); S2 bR(-0.025,0.28)/ls(.,0.6) | Prior Predictive：S2 在极端暴露情景下生成 **13.6%** 荒谬值 | S0 bR(0,0.07)/ls(.,0.45); S1 bR(-0.05,0.13); S2 bR(-0.025,0.18)/ls(.,0.50) | 收紧最宽先验 |
| v0.3 | 2026-09-22 | S2 bR(-0.025,0.18)/ls(.,0.50) | 极端情景仍有 4.3% 荒谬值 | S2 bR(-0.025,0.15)/ls(.,0.45), alpha(0.26), bT(0,0.16) | 进一步收紧；并明确“极端情景荒谬”主要源于 **2026 强外推(ZR≈+4.25)**，非先验缺陷 |
| （待补） | | | | | 若 Prior Predictive 或诊断要求调整，在此追加 |

## 说明
- `beta_R` 一律**不硬截断为负**（规格 §19）：允许 P(beta_R≥0)>0，因为“降雨≠渍涝”，适度降雨可能有益。
- `alpha / beta_T / log_sigma` 使用弱信息先验，量级以**农业合理单产范围**（≈3000–15000 kg/ha）可解释为准，
  不使用 `Normal(0,10000)` 之类无约束先验。
"""
