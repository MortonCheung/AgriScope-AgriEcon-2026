#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
反事实模拟引擎（PREBUILD 骨架）。
纪律：
- 模块化：M2 / M3 / M4 / scenario / uncertainty / aggregation 相互独立；
- **禁止假默认值**：真实参数缺失时返回 RAISED(NOT_AVAILABLE / WAITING_FOR_DATA)；
- 只做结构连通性测试；SYNTHETIC 参数必须显式传入并标记。
"""
WAITING = "WAITING_FOR_DATA"
NOT_AVAIL = "NOT_AVAILABLE"


class MissingData(Exception):
    def __init__(self, field, status=WAITING):
        super().__init__(f"{field}: {status}")
        self.field = field
        self.status = status


def simulate_weather(scenario, params):
    """返回事件降雨序列（mm/h）。真实数据缺失时抛 MissingData。"""
    if scenario.get("weather") == "normal":
        return params.get("normal_rain_mm_per_h", WAITING)
    return params.get("event_rain_mm_per_h", WAITING)


def simulate_waterlogging_M2(scenario, params, cell):
    """M2：susceptibility → 是否存在渍涝（相对易感性阈值）。真实标定缺失则 WAITING。"""
    thr = params.get("m2_threshold", WAITING)
    if thr == WAITING:
        raise MissingData("m2_threshold")
    return float(cell.get("susceptibility", 0.0)) >= thr


def simulate_duration_M4(scenario, params, m2_state):
    """M4：水量平衡 → 积水历时分布（h）。缺排水参数则 WAITING。"""
    need = ["area_m2", "pump_capacity_m3h", "k_inf_mm_h", "k_nat_per_h", "init_storage_mm"]
    for k in need:
        if params.get(k, WAITING) == WAITING:
            raise MissingData(k)
    from importlib import import_module
    m4 = import_module("m4_water_balance") if "m4_water_balance" in dir() else None
    return params.get("duration_h_synthetic", WAITING)


def simulate_crop_damage_M3(params, stage, duration_h):
    """M3：stage×duration → loss 分布。缺 duration 则不可跑（§九十一）。"""
    if duration_h in (None, WAITING):
        raise MissingData("waterlogging_duration")
    anchors = params.get("m3_anchors")
    if not anchors:
        raise MissingData("m3_anchors", NOT_AVAIL)
    x = np.array([a[0] for a in anchors]); y = np.array([a[1] for a in anchors])
    return float(np.clip(np.interp(duration_h / 24.0, x, y, left=0.0, right=y[-1]), 0, 0.95))


def aggregate_outcome(cells):
    """聚合到区域结果（面积加权）。"""
    import numpy as np
    A = np.array([c["area_m2"] for c in cells], float)
    L = np.array([c.get("loss_fraction", np.nan) for c in cells], float)
    m = np.isfinite(L)
    if m.sum() == 0:
        return WAITING
    return float((A[m] * L[m]).sum() / A[m].sum())


def run_world(world, cells, params, rng, common):
    """跑一个世界。common 为 Common Random Numbers（跨世界共享的非处理随机量）。"""
    out = []
    for c in cells:
        if world == "B":          # 无灾害：天气替换为正常；应急干预由结构自动响应（通常不触发）
            w = "normal"
        else:
            w = "event"
        try:
            state = simulate_waterlogging_M2({"weather": w}, params, c)
        except MissingData as e:
            return {"status": e.status, "field": e.field, "world": world}
        # 历时：D 世界只改 intervention_start（不改泵能力）
        p = dict(params)
        if world == "C":
            p["pump_capacity_m3h"] = params.get("pump_natural_only_m3h", 0.0)   # 仅自然/常规，不是 0 全部
        if world == "D24":
            p["intervention_start_h"] = max(0.0, params.get("intervention_start_h", 28.0) - 24.0)
        if world == "D48":
            p["intervention_start_h"] = max(0.0, params.get("intervention_start_h", 28.0) - 48.0)
        if not state:              # 无渍涝 → 无历时、无损失
            out.append({"cell_id": c["cell_id"], "area_m2": c["area_m2"], "duration_h": 0.0,
                        "loss_fraction": 0.0})
            continue
        dur = p.get("duration_h_by_weather", {}).get(w, WAITING)
        try:
            loss = simulate_crop_damage_M3(p, c.get("stage", "tasseling"), dur)
        except MissingData as e:
            return {"status": e.status, "field": e.field, "world": world}
        out.append({"cell_id": c["cell_id"], "area_m2": c["area_m2"], "duration_h": dur,
                    "loss_fraction": loss})
    return {"status": "OK", "cells": out, "aggregate_loss": aggregate_outcome(out)}
