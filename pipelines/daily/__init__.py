# -*- coding: utf-8 -*-
"""AgriScope Daily · 每日市场脉搏流水线。

独立于 Data Foundation 与 Final Model 训练流程：

    Scheduler → Collector → Raw Archive → Normalizer → QC
        → Daily Feature Builder → Model Adapter → Daily Snapshot → AgriScope

设计原则：真实 / 稳定 / 可追溯 / 可恢复 / 可长期运行。
不依赖 Mac 本地路径（ROOT 由本文件位置推导），纯命令行可运行。
"""
from __future__ import annotations

__all__ = ["config"]