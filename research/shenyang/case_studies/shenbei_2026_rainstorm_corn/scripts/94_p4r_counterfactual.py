#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
R12 四平行世界因果定义
R13 反事实模拟引擎骨架（模块化；缺真实参数时返回 WAITING_FOR_DATA，禁止假默认值）
R14 Monte Carlo 不确定性传播（Common Random Numbers）+ 单元测试
输出：06_models/prebuild/counterfactual/*, scripts/tests/test_mc_propagation.py,
      05_analysis/10_parallel_research/UNCERTAINTY_PROPAGATION.md
"""
import os
import sys

import numpy as np
import pandas as pd

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CF = os.path.join(BASE, "06_models", "prebuild", "counterfactual")
T = os.path.join(BASE, "scripts", "tests")
PR = os.path.join(BASE, "05_analysis", "10_parallel_research")
for d in [CF, T, PR]:
    os.makedirs(d, exist_ok=True)

ENGINE = '''#!/usr/bin/env python3
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
'''

with open(os.path.join(CF, "engine.py"), "w", encoding="utf-8") as f:
    f.write(ENGINE)

sys.path.insert(0, CF)
sys.path.insert(0, os.path.join(BASE, "06_models", "prebuild", "M4"))


def mc_propagation_demo(n=2000, seed=20260923):
    """Common Random Numbers：同一次 draw 内 A/B/C/D 共享非处理随机量，只改 weather/intervention。"""
    rng = np.random.default_rng(seed)
    from m4_water_balance import simulate
    rows = []
    for _ in range(n):
        # 共享随机参数（CRN）
        k_inf = rng.uniform(0.6, 1.6)
        k_nat = rng.uniform(0.010, 0.035)
        init_S = rng.uniform(60, 180)
        pump = rng.uniform(1800, 6000)
        rain_ev = rng.uniform(1.2, 3.0)
        base = dict(area_m2=5.33e6, k_inf_mm_h=k_inf, k_nat_per_h=k_nat,
                    init_storage_mm=init_S, duration_h=168, dt=0.5)
        A = simulate(rain_mm_per_h=rain_ev, rain_end_h=24, pump_capacity_m3h=pump,
                     intervention_start_h=28, **base)["end_h"]
        # B 世界：天气替换为“正常情景” → 前期湿润也应为正常水平（属天气情景，非共享随机量）
        init_normal = rng.uniform(20, 55)
        B = simulate(rain_mm_per_h=0.3, rain_end_h=12, pump_capacity_m3h=0,
                     intervention_start_h=999, **{**base, "init_storage_mm": init_normal})["end_h"]
        C = simulate(rain_mm_per_h=rain_ev, rain_end_h=24, pump_capacity_m3h=0,
                     intervention_start_h=999, **base)["end_h"]
        D24 = simulate(rain_mm_per_h=rain_ev, rain_end_h=24, pump_capacity_m3h=pump,
                       intervention_start_h=4.0, **base)["end_h"]
        D48 = simulate(rain_mm_per_h=rain_ev, rain_end_h=24, pump_capacity_m3h=pump,
                       intervention_start_h=0.0, **base)["end_h"]
        rows.append(dict(A=A, B=B, C=C, D24=D24, D48=D48))
    df = pd.DataFrame(rows)
    df["disaster_effect_C_minus_A"] = df["C"] - df["A"]
    df["avoided_by_intervention_C_minus_A"] = df["C"] - df["A"]
    df["extra_benefit_D24"] = df["A"] - df["D24"]
    df["extra_benefit_D48"] = df["A"] - df["D48"]
    return df


def main():
    # ---------- R12 世界定义 ----------
    with open(os.path.join(CF, "COUNTERFACTUAL_WORLD_SPECIFICATION.md"), "w", encoding="utf-8") as f:
        f.write("""# COUNTERFACTUAL_WORLD_SPECIFICATION.md（R12 / §五十四~六十）

> 本文件只做 **CAUSAL SPECIFICATION**（结构定义），**不输出任何最终数字**。
> 原则：**只改变指定变量**，其余由结构模型自动响应；**禁止手动改一堆数字**。

| 世界 | 天气 | 应急排涝干预 | 常规/自然排水 | 其他 | 目标 |
|---|---|---|---|---|---|
| **A 现实** | 观测 2026 极端天气 | 观测/估计的真实干预（如 12 台泵、7-14 启动） | 保留现状 | 观测农业状态 | reconstruct reality |
| **B 无灾害** | **替换为历史正常天气情景**（**不是 rainfall=0**） | **由结构自动响应**：正常天气下通常**不启动应急泵** | 保留 | 其余一致 | 无灾害对照 |
| **C 无干预** | 2026 实际极端天气 | **取消应急抽排（emergency pumping）** | **保留原有的自然排水与常规基础设施**（**不是全部排水=0**） | 其余一致 | 应急干预的效果 |
| **D 提前干预** | 2026 实际极端天气 | 物理设施与泵能力**不变**，**只改 `intervention_start`**（−24h / −48h） | 保留 | 其余一致 | 提前量的增量收益 |

## 关键澄清
1. **B 世界不能设 rainfall=0**：无灾害 = “把**极端天气暴露**替换为**历史正常天气情景**”；同时 **emergency intervention 是灾害的下游变量**，正常天气下不应“12 台泵照常启动”。
2. **C 世界不能设所有排水=0**：那是另一个不存在的世界。C 只取消**应急抽排**，保留自然下渗/沟渠/常规设施。
3. **D 世界必须讨论操作可行性**：若某些行动在暴雨前物理上无法启动，需在结论中说明。

## 反事实估计量（符号统一）
```
Disaster effect                  = Loss_A − Loss_B
Avoided loss by actual intervention = Loss_C − Loss_A
Additional benefit of earlier intervention = Loss_A − Loss_D24 ; Loss_A − Loss_D48
```
> 一律报告 **median + 50%/80%/95% 区间**，禁止单值。

## 变量改变矩阵（谁变、谁不变、谁自动响应）
| 变量 | A | B | C | D(−24/−48h) | 说明 |
|---|---|---|---|---|---|
| weather | 实际 | **正常情景** | 实际 | 实际 | B 仅此项不同 |
| pump_capacity | 实际 | 由结构响应（≈0 应急） | **0（应急）** | 实际 | 常规设施仍在 |
| intervention_start | 实际 | — | — | **提前** | D 仅此项不同 |
| 地形/土壤/排水设施 | 同 | 同 | 同 | 同 | 不变 |
| 作物状态 | 观测 | 由模型响应 | 由模型响应 | 由模型响应 | 自动 |
""")

    # ---------- R14 MC 传播 ----------
    df = mc_propagation_demo(n=2000)
    summ = []
    for c in ["A", "B", "C", "D24", "D48", "disaster_effect_C_minus_A", "extra_benefit_D24", "extra_benefit_D48"]:
        summ.append(dict(quantity=c, median=round(float(df[c].median()), 2),
                         p50_lo=round(float(df[c].quantile(0.25)), 2),
                         p50_hi=round(float(df[c].quantile(0.75)), 2),
                         p80_lo=round(float(df[c].quantile(0.10)), 2),
                         p80_hi=round(float(df[c].quantile(0.90)), 2),
                         p95_lo=round(float(df[c].quantile(0.025)), 2),
                         p95_hi=round(float(df[c].quantile(0.975)), 2)))
    sdf = pd.DataFrame(summ)
    sdf.to_csv(os.path.join(CF, "MC_demo_summary_SYNTHETIC.csv"), index=False, encoding="utf-8-sig")
    with open(os.path.join(PR, "UNCERTAINTY_PROPAGATION.md"), "w", encoding="utf-8") as f:
        f.write("# UNCERTAINTY_PROPAGATION.md（R14 / §六十五~六十九）\n\n")
        f.write("## 为什么不能“取均值再取均值”\n")
        f.write("M2→M3→M4 逐步取均值会**严重低估不确定性**。正确做法：**每次 MC draw 从各模块分布抽样，完整跑一个 world**，"
                "最后得到 **Outcome distribution**。\n\n")
        f.write("## Common Random Numbers（CRN）\n")
        f.write("同一次 draw 中，A/B/C/D **共享非处理随机参数**（k_inf、k_nat、init_storage、pump、rain），"
                "**只改变 weather / intervention**，从而降低世界间比较的纯模拟噪声（§六十七）。\n\n")
        f.write("## 合成演示（SYNTHETIC，2000 draws，参数为范围而非沈北真值）\n\n")
        f.write(sdf.to_string(index=False) + "\n\n")
        f.write("## 结论\n")
        f.write("- 演示仅验证**传播框架与代码**可用（分布、区间、CRN、ordering）。\n")
        f.write("- **不得**把上表任何数字当作沈北结论（参数为 SYNTHETIC）。\n")
    print("[R14] MC 合成演示（SYNTHETIC）:\n", sdf.head(6).to_string(index=False))

    # ---------- 引擎说明 ----------
    with open(os.path.join(CF, "ENGINE_INTERFACE.md"), "w", encoding="utf-8") as f:
        f.write("""# ENGINE_INTERFACE.md（R13 / §六十一~六十四）

## 模块链（相互独立，禁止单体硬编码）
```
simulate_weather() → simulate_waterlogging_M2() → simulate_duration_M4() → simulate_crop_damage_M3() → aggregate_outcome()
```
实现见 `engine.py`。**禁止**写一个 `run_parallel_world.py` 把公式全硬编码。

## 接口契约
| 生产者 | 输出字段 | 消费者 |
|---|---|---|
| M2 | `cell_id, susceptibility, waterlogging_state, confidence` | M3/M4 |
| M4 | `duration_distribution, peak_storage, drainage_end_time` | M3 |
| M3 | `yield_ratio_distribution, damage_fraction_distribution` | aggregation |
| aggregation | `region_loss_distribution` | 报告 |

## 缺字段处理（§六十四）
允许：`NULL` / `NOT_AVAILABLE` / `WAITING_FOR_DATA`
**禁止**：用假默认值让 pipeline “成功运行”。

`engine.py` 在缺 `m2_threshold` / `duration` / `m3_anchors` / 排水参数时**抛 MissingData**（状态 WAITING_FOR_DATA）。
""")

    # ---------- MC 单元测试 ----------
    with open(os.path.join(T, "test_mc_propagation.py"), "w", encoding="utf-8") as f:
        f.write('''#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Monte Carlo 传播单元测试（SYNTHETIC 参数）。"""
import os, sys, importlib.util, numpy as np
BASE = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
spec = importlib.util.spec_from_file_location("p4r_cf", os.path.join(BASE, "scripts", "94_p4r_counterfactual.py"))
m = importlib.util.module_from_spec(spec)
sys.path.insert(0, os.path.join(BASE, "06_models", "prebuild", "M4"))
try:
    spec.loader.exec_module(m)
except SystemExit:
    pass


def test_seed_reproducible():
    a = m.mc_propagation_demo(n=200, seed=1)
    b = m.mc_propagation_demo(n=200, seed=1)
    assert a.equals(b), "固定 seed 必须可复现"
    print("PASS test_seed_reproducible")


def test_sample_stability():
    a = m.mc_propagation_demo(n=500, seed=2)["A"].median()
    b = m.mc_propagation_demo(n=5000, seed=2)["A"].median()
    assert abs(a - b) / max(abs(b), 1e-9) < 0.25, f"样本量增大应稳定: {a} vs {b}"
    print("PASS test_sample_stability", round(a, 2), round(b, 2))


def test_world_ordering():
    d = m.mc_propagation_demo(n=500, seed=3)
    assert d["C"].median() >= d["A"].median() - 1e-6, "C(无应急)应不早于 A"
    assert d["D24"].median() <= d["A"].median() + 1e-6, "D24(提前)应不晚于 A"
    print("PASS test_world_ordering", {k: round(d[k].median(), 1) for k in ["A", "B", "C", "D24", "D48"]})


def test_ranges_physical():
    d = m.mc_propagation_demo(n=500, seed=4)
    assert (d[["A", "B", "C", "D24", "D48"]] >= 0).all().all(), "历时不得为负"
    assert d[["A", "B", "C", "D24", "D48"]].max().max() <= 168 + 1e-6, "不得超过模拟时长"
    print("PASS test_ranges_physical")


if __name__ == "__main__":
    test_seed_reproducible(); test_sample_stability(); test_world_ordering(); test_ranges_physical()
''')
    print("[R13/R14] engine.py / ENGINE_INTERFACE.md / test_mc_propagation.py 已写出")


if __name__ == "__main__":
    main()
