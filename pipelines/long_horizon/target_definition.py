# -*- coding: utf-8 -*-
"""RC1 历史 Target 定义；SUPERSEDED_BY_RC2，不是当前生产目标真源。

当前正式定义见 long_horizon.v2.target_spec / 已冻结 V2 index.json。
以下常量保留用于还原 RC1 研究，不可作为 Harvest Market Price。

判定依据：`reports/LONG_HORIZON_TARGET_STUDY.md`（5 种候选口径 × 4 个 horizon × 3 组 baseline）。
结论：`full` —— 未来 (t, t+N] 内已有观测的均价，**与现有 Final 短期目标
`target_mean_price_next_{N}d` 完全同口径**，是它向长期的自然延伸。

本常量记录 RC1 历史行为，不影响 V2 两个正式业务 target。
"""
from __future__ import annotations

from .targets import target_col_name

PRIMARY_TARGET_KIND = "full"          # Phase 7 程序化判定结果（decision_score 最低且显著）
PRIMARY_TARGET_WINDOW = None          # full 无尾窗


def primary_target_col(horizon: int) -> str:
    """正式长期 target 列名。"""
    return target_col_name(PRIMARY_TARGET_KIND, horizon, PRIMARY_TARGET_WINDOW)


__all__ = ["PRIMARY_TARGET_KIND", "PRIMARY_TARGET_WINDOW", "primary_target_col"]
