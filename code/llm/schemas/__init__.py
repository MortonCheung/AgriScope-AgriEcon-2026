# -*- coding: utf-8 -*-
"""结构化输出 Schema 与数字安全校验。"""
from __future__ import annotations

from .forecast import (FORECAST_SCHEMA, RESIDUAL_SCHEMA, CRITIC_SCHEMA,
                       validate_forecast, validate_residual, validate_critic,
                       hard_bounds)

__all__ = ["FORECAST_SCHEMA", "RESIDUAL_SCHEMA", "CRITIC_SCHEMA",
           "validate_forecast", "validate_residual", "validate_critic", "hard_bounds"]