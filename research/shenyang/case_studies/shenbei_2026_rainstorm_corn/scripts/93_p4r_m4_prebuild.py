#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
R10/R11：M4 排涝干预模型（Intervention → Waterlogging Duration）。
- 建立简化水量平衡模块（06_models/prebuild/M4/m4_water_balance.py）
- 合成场景 + 5 个不变量测试
- 全部标记 SYNTHETIC；仅提供参数范围，不反推“真实泵流量”
输出：06_models/prebuild/M4/{M4_STATE_EQUATION.md, M4_SYNTHETIC_VALIDATION.md, M4_PARAMETER_RANGES.csv}
      scripts/tests/test_m4_*.py
"""
import os
import sys

import numpy as np
import pandas as pd

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
P = os.path.join(BASE, "06_models", "prebuild", "M4")
T = os.path.join(BASE, "scripts", "tests")
os.makedirs(P, exist_ok=True); os.makedirs(T, exist_ok=True)

MODULE = '''#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""M4 简化水量平衡（PREBUILD / SYNTHETIC）。State(t+dt)=State(t)+(P+Inflow-Inf-NatDrain-Pump)*dt"""
import numpy as np


def pump_rate_mm_per_h(pump_capacity_m3h, area_m2):
    """泵排水能力折算为面雨量当量 (mm/h)。"""
    return pump_capacity_m3h / area_m2 * 1000.0


def simulate(rain_mm_per_h=2.0, rain_end_h=24.0, duration_h=168, dt=0.25, area_m2=5.33e6,
             k_inf_mm_h=1.0, k_nat_per_h=0.02, init_storage_mm=120.0,
             pump_capacity_m3h=3600.0, intervention_start_h=28.0, intervention_end_h=None,
             s_threshold_mm=0.5, wetness_factor=1.0):
    """返回 dict(peak_mm, end_h, series_mm)。SYNTHETIC 参数必须外部给定。"""
    k_inf = k_inf_mm_h * (1.0 / wetness_factor)      # 前期越湿，入渗越慢
    pump = pump_rate_mm_per_h(pump_capacity_m3h, area_m2) if pump_capacity_m3h else 0.0
    n = int(duration_h / dt)
    S = init_storage_mm
    peak = S
    series = []
    for i in range(n):
        t = i * dt
        rain = rain_mm_per_h if t < rain_end_h else 0.0
        inf = k_inf * (1.0 if S > 0 else 0.0)
        nat = k_nat_per_h * max(0.0, S - s_threshold_mm) * dt * 60.0 / 60.0  # ≈ k*(S-thr)
        nat = k_nat_per_h * max(0.0, S - s_threshold_mm)
        p = 0.0
        if pump > 0 and t >= intervention_start_h and (intervention_end_h is None or t <= intervention_end_h):
            p = min(pump, max(0.0, S) / dt)              # 不抽成负
        dS = (rain - inf - nat - p) * dt
        S = max(0.0, S + dS)
        peak = max(peak, S)
        series.append(S)
    # 排净时间：S 首次 <= 阈值且此后保持
    end_h = None
    for i in range(len(series) - 1, -1, -1):
        if series[i] > s_threshold_mm:
            end_h = (i + 1) * dt
            break
    if end_h is None:
        end_h = 0.0
    return dict(peak_mm=float(peak), end_h=float(end_h), series=np.array(series))
'''

with open(os.path.join(P, "m4_water_balance.py"), "w", encoding="utf-8") as f:
    f.write(MODULE)
sys.path.insert(0, P)
from m4_water_balance import simulate, pump_rate_mm_per_h  # noqa

# 参数范围（全部标记来源等级）
PARAMS = pd.DataFrame([
    ("rain_mm_per_h", "OBSERVED/DERIVED", "ERA5 事件雨强（注意为单点 forcing）", "—"),
    ("area_m2", "OBSERVED（个案）", "八间房村 8000 余亩 → 5.33e6 m²", "量级"),
    ("k_inf_mm_h", "CALIBRATABLE/LITERATURE_PARAMETER", "入渗能力（土壤缺失 → 范围）", "1~10"),
    ("k_nat_per_h", "LATENT", "自然排水/沟渠/外排综合速率", "0.005~0.08"),
    ("init_storage_mm", "LATENT", "初始蓄水（前期湿润）", "20~200"),
    ("pump_capacity_m3h", "DERIVED", "12×8寸泵（工程参考区间，非铭牌）", "1800~6000"),
    ("intervention_start_h", "OBSERVED", "预警→行动：14.8h（八间房村）", "—"),
    ("s_threshold_mm", "ASSUMED", "视为排净的残余深度", "0.1~2"),
], columns=["parameter", "role", "note", "range"])
PARAMS.to_csv(os.path.join(P, "M4_PARAMETER_RANGES.csv"), index=False, encoding="utf-8-sig")

rng = np.random.default_rng(20260923)


def scen(seed=None):
    return dict(rain_mm_per_h=2.0, rain_end_h=24.0, duration_h=168, area_m2=5.33e6,
                k_inf_mm_h=1.0, k_nat_per_h=0.02, init_storage_mm=120.0,
                pump_capacity_m3h=3600.0, intervention_start_h=28.0)


def test_invariants():
    res = []
    # Test1: 泵能力↑ 不应使历时系统性增加
    d = [simulate(**{**scen(), "pump_capacity_m3h": c})["end_h"] for c in [0, 1800, 3600, 6000]]
    res.append(dict(test="T1_pump_capacity_up", values=[round(x, 1) for x in d],
                    passed=bool(all(np.diff(d) <= 1e-6)), note="end_h 非随泵能力上升而增加"))
    # Test2: 提前启动 → 不应更晚排净
    d = [simulate(**{**scen(), "intervention_start_h": s})["end_h"] for s in [0, 12, 28, 48]]
    res.append(dict(test="T2_earlier_start", values=[round(x, 1) for x in d],
                    passed=bool(all(np.diff(d) >= -1e-6)), note="越早启动 end_h 不更晚"))
    # Test3: 无主动排涝 不应比 现实排涝 更快排净
    real = simulate(**scen())["end_h"]; none = simulate(**{**scen(), "pump_capacity_m3h": 0})["end_h"]
    res.append(dict(test="T3_no_pump_slower", values=[round(real, 1), round(none, 1)],
                    passed=bool(none >= real - 1e-6), note="无泵 world 排净时间 >= 现实"))
    # Test4: 降雨↑ → 峰值不应系统性下降
    d = [simulate(**{**scen(), "rain_mm_per_h": r})["peak_mm"] for r in [1.0, 4.0, 8.0, 16.0]]
    res.append(dict(test="T4_more_rain_higher_peak", values=[round(x, 1) for x in d],
                    passed=bool(all(np.diff(d) >= -1e-6)), note="峰值随降雨不减"))
    # Test5: 初始更湿 → 渍涝负荷不应降低
    d = [simulate(**{**scen(), "init_storage_mm": s, "wetness_factor": f})["end_h"]
         for s, f in [(20, 1.3), (80, 1.1), (120, 1.0), (200, 0.85)]]
    res.append(dict(test="T5_wetter_initial", values=[round(x, 1) for x in d],
                    passed=bool(all(np.diff(d) >= -1e-6)), note="初始更湿 end_h 不减"))
    return pd.DataFrame(res)


def aggregate_constraint():
    """8000亩/96h 案例能约束什么、不能约束什么（§四十八）。"""
    area = 5.33e6
    rows = []
    for cap in [1800, 3600, 6000]:
        pr = pump_rate_mm_per_h(cap, area)
        rows.append(dict(pump_capacity_m3h=cap, pump_equivalent_mm_per_h=round(pr, 3),
                         hours_to_remove_200mm_by_pump_only=round(200 / pr, 1),
                         hours_to_remove_500mm_by_pump_only=round(500 / pr, 1)))
    return pd.DataFrame(rows)


def main():
    inv = test_invariants()
    agg = aggregate_constraint()
    # 情景表（SYNTHETIC）
    scen_rows = []
    for name, over in [("A_real", {}),
                       ("B_normal_rain", {"rain_mm_per_h": 0.5}),
                       ("C_no_pump", {"pump_capacity_m3h": 0}),
                       ("D_start_-24h", {"intervention_start_h": 4.8}),
                       ("D_start_-48h", {"intervention_start_h": 0.0})]:
        r = simulate(**{**scen(), **over})
        scen_rows.append(dict(scenario=name, peak_mm=round(r["peak_mm"], 1), end_h=round(r["end_h"], 1)))
    scen_df = pd.DataFrame(scen_rows)

    with open(os.path.join(P, "M4_STATE_EQUATION.md"), "w", encoding="utf-8") as f:
        f.write("# M4_STATE_EQUATION.md（R10 / §四十五~四十九）\n\n")
        f.write("## 目标（不是 Intervention→Yield）\n```\nIntervention → Waterlogging Duration\n```\n\n")
        f.write("## 状态方程\n```\nStorage(t+Δt) = Storage(t) + ( Rainfall + Inflow − Infiltration − NaturalDrainage − PumpDrainage − OtherLosses ) · Δt\n```\n\n")
        f.write("## 每项可观测性标注\n\n" + PARAMS.to_string(index=False) + "\n\n")
        f.write("## emergency pumping ≠ 全部排水（§四十八）\n")
        f.write("真实案例：**12 台 8 寸泵 / ~96h / 8000 余亩**。**不能**推导“所有水都由这 12 台泵抽走”。\n")
        f.write("还必须考虑：自然下渗、沟渠排水、地表外排、蒸散、其他设备、上下游调度。\n")
        f.write("→ 该案例只能作为 **weak aggregate constraint**，**不得据此反推真实泵流量**。\n\n")
        f.write("### 量级示意（仅换算，非真值）\n\n" + agg.to_string(index=False) + "\n\n")
        f.write("> 含义：泵当量约 0.34–1.13 mm/h；仅靠泵排 200mm 需 177–590h，"
                "**远长于实际 96h** → 说明**自然排水/沟渠贡献不可忽略**，泵只是加速项。\n")
        f.write("\n## 所有不确定量以分布/区间表达（§四十九），**禁止固定假数**。\n")
    print("[R10] M4_STATE_EQUATION 已写出；不变量:\n", inv.to_string(index=False))

    with open(os.path.join(P, "M4_SYNTHETIC_VALIDATION.md"), "w", encoding="utf-8") as f:
        f.write("# M4_SYNTHETIC_VALIDATION.md（R11 / §五十~五十二）\n\n")
        f.write("> 全部为 **SYNTHETIC** 场景：参数来自范围，不代表沈北真值。\n\n")
        f.write("## 不变量测试（必须全部通过）\n\n" + inv.to_string(index=False) + "\n\n")
        f.write(f"**总判定：{'全部通过' if inv.passed.all() else '存在失败，须先修模型'}**\n\n")
        f.write("## 合成世界情景（SYNTHETIC，不可作为结论）\n\n" + scen_df.to_string(index=False) + "\n\n")
        f.write("## 说明\n- A_real 与 B/C/D 的差值在合成参数下呈现**方向正确**的排序，"
                "但这只检验**模型逻辑**，**不构成任何沈北数字**。\n")
    print("[R11] 情景:\n", scen_df.to_string(index=False))

    # ---------- 可重复测试脚本 ----------
    with open(os.path.join(T, "test_m4_mass_balance.py"), "w", encoding="utf-8") as f:
        f.write('''#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""M4 质量平衡单元测试（可独立运行）。"""
import os, sys, numpy as np
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "06_models", "prebuild", "M4"))
from m4_water_balance import simulate

def test_non_negative_storage():
    r = simulate(rain_mm_per_h=0.1, duration_h=48, pump_capacity_m3h=6000, init_storage_mm=5)
    assert (r["series"] >= -1e-9).all(), "storage 不得为负"
    print("PASS test_non_negative_storage")

def test_zero_pump_equals_no_pump_term():
    r0 = simulate(rain_mm_per_h=1.0, pump_capacity_m3h=0)
    r1 = simulate(rain_mm_per_h=1.0, pump_capacity_m3h=0, intervention_start_h=1000)
    assert abs(r0["end_h"] - r1["end_h"]) < 1e-9
    print("PASS test_zero_pump_equals_no_pump_term")

if __name__ == "__main__":
    test_non_negative_storage(); test_zero_pump_equals_no_pump_term()
''')
    with open(os.path.join(T, "test_m4_monotonicity.py"), "w", encoding="utf-8") as f:
        f.write('''#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""M4 单调性测试（可独立运行）。"""
import os, sys, numpy as np
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "06_models", "prebuild", "M4"))
from m4_water_balance import simulate

def test_pump_capacity_monotone():
    d = [simulate(pump_capacity_m3h=c)["end_h"] for c in [0, 1800, 3600, 6000]]
    assert all(np.diff(d) <= 1e-6), f"泵能力↑不应使历时增加: {d}"
    print("PASS test_pump_capacity_monotone", d)

def test_rain_monotone_peak():
    d = [simulate(rain_mm_per_h=r)["peak_mm"] for r in [1, 4, 8, 16]]
    assert all(np.diff(d) >= -1e-6), f"降雨↑不应降低峰值: {d}"
    print("PASS test_rain_monotone_peak", d)

if __name__ == "__main__":
    test_pump_capacity_monotone(); test_rain_monotone_peak()
''')
    with open(os.path.join(T, "test_m4_scenario_ordering.py"), "w", encoding="utf-8") as f:
        f.write('''#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""M4 世界排序测试：无泵 >= 现实 >= 提前（排净时间）。"""
import os, sys
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "06_models", "prebuild", "M4"))
from m4_water_balance import simulate

def test_world_ordering():
    real = simulate(pump_capacity_m3h=3600, intervention_start_h=28)["end_h"]
    none = simulate(pump_capacity_m3h=0, intervention_start_h=28)["end_h"]
    d24 = simulate(pump_capacity_m3h=3600, intervention_start_h=4.8)["end_h"]
    assert none >= real - 1e-6, (none, real)
    assert d24 <= real + 1e-6, (d24, real)
    print("PASS test_world_ordering", {"C_none": none, "A_real": real, "D_early": d24})

if __name__ == "__main__":
    test_world_ordering()
''')
    print("[R11] 测试脚本已写出 scripts/tests/test_m4_*.py")


if __name__ == "__main__":
    main()
