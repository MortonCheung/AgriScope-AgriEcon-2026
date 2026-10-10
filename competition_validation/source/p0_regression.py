#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""P0 回归测试：每项针对审查报告中的一个 P0 缺陷。

在「未修复」代码上应当 FAIL，在「修复后」代码上应当 PASS。
用法： PROJECT_ROOT=<experiments>/root python3 tests/p0_regression.py
"""
from __future__ import annotations
import os
import sys
import traceback
from pathlib import Path

HERE = Path(__file__).resolve().parent
EXP = HERE.parent
DE_SRC = Path(os.environ.get("EXPERIMENTS_DE_SRC", EXP / "code" / "src"))
os.environ["PROJECT_ROOT"] = str(EXP / "root")
sys.path.insert(0, str(DE_SRC))
print(f"[env] code src = {DE_SRC}", flush=True)

import numpy as np
import pandas as pd  # noqa: E402

RESULTS = []


def check(name, fn):
    try:
        ok, note = fn()
    except Exception as e:
        ok, note = False, f"EXCEPTION {type(e).__name__}: {e}"
        traceback.print_exc()
    RESULTS.append((name, bool(ok), note))
    print(f"[{'PASS' if ok else 'FAIL'}] {name} — {note}", flush=True)


# ------------------------------------------------------------------ P0-1
def p0_1_prefix_invariance():
    """HRI 必须满足前缀不变性：用 <=cutoff 的历史算出的 HRI 应与全量历史算出的 cutoff 行逐值相等。"""
    from decision_engine.final.risk import weekly_prices, hri_components, combine
    w = weekly_prices("沈阳")
    w["wk"] = w["iso_year"] * 100 + w["iso_week"]
    full = combine(hri_components(w))
    # 注意：wk = iso_year*100 + iso_week（如 202640），cutoff 必须用同一口径
    cutoffs = [202330, 202426, 202526]
    bad = []
    for cut in cutoffs:
        wt = w[w["wk"] <= cut].copy()
        trunc = combine(hri_components(wt))
        a = full[full["wk"] <= cut][["crop", "wk", "c_consecutive_rise", "HRI"]]
        b = trunc[["crop", "wk", "c_consecutive_rise", "HRI"]]
        m = a.merge(b, on=["crop", "wk"], suffixes=("_full", "_trunc"))
        if not len(m):
            continue
        for col in ["c_consecutive_rise", "HRI"]:
            d = (m[f"{col}_full"].fillna(-1) - m[f"{col}_trunc"].fillna(-1)).abs()
            mx = float(np.nanmax(d.values)) if len(d) else 0.0
            if mx > 1e-6:
                bad.append(f"{col}@cut{cut}: max|Δ|={mx:.6g} (n={int((d > 1e-6).sum())})")
    if bad:
        return False, "前缀不变性被破坏 → " + "; ".join(bad[:4])
    return True, f"三个 cutoff 下 c_consecutive_rise 与 HRI 均逐值相等（n={len(full)}）"


# ------------------------------------------------------------------ P0-2
def p0_2_fwd_right_censored():
    """前瞻标签必须右删失：不足完整 h 周的尾部不得产生 fwd_hw。"""
    from decision_engine.final.risk import weekly_prices, hri_components, combine, _fwd
    w = weekly_prices("沈阳")
    w["wk"] = w["iso_year"] * 100 + w["iso_week"]
    h = combine(hri_components(w))
    h = _fwd(h, "wk", "price_mean", hs=(4, 8, 12))
    viol = []
    for crop, sub in h.groupby("crop", sort=False):
        sub = sub.sort_values("wk").reset_index(drop=True)
        n = len(sub)
        for hh in (4, 8, 12):
            tail = sub.iloc[max(0, n - hh + 1):]          # 尾部不足 hh 步的行
            nz = tail[f"fwd_{hh}w"].notna().sum()
            if nz:
                viol.append(f"{crop} h={hh}: tail {nz} 行有值")
    has_flag = "label_matured_12w" in h.columns
    if viol:
        return False, "尾部未右删失 → " + "; ".join(viol[:4])
    if not has_flag:
        return False, "缺少 LABEL_NOT_MATURED 成熟度标记列 label_matured_12w"
    return True, "尾部 fwd_* 全部为 NaN 且存在 label_matured_* 标记"


# ------------------------------------------------------------------ P0-3
def p0_3_seasonal_argmax():
    """季节基线必须真正选取同月历史指标最优的作物（而非字典序第一个匹配作物）。"""
    from decision_engine.final.backtest import _seasonal_pick
    t = pd.Timestamp("2025-07-10")
    g = pd.DataFrame({
        "date": [t, t, t],
        "crop": ["土豆", "西红柿", "黄瓜"],       # 字典序最靠前 = 土豆
        "forecast": [1.0, 2.0, 3.0],
        "anchor_price": [1.0, 1.0, 1.0],
    })
    # 同月历史：绝对价与相对收益最优者均为「西红柿」，而非字典序第一的「土豆」
    hist = pd.DataFrame({
        "date": pd.to_datetime(["2024-07-01", "2024-07-02", "2024-07-03",
                                "2024-07-04", "2024-07-05", "2024-07-06"]),
        "crop": ["土豆", "土豆", "西红柿", "西红柿", "黄瓜", "黄瓜"],
        "price_per_kg": [10.0, 10.0, 12.0, 13.0, 11.0, 11.0],
        "rel_ret": [-0.20, -0.18, 0.30, 0.32, 0.00, 0.01],
        "month": [7] * 6,
    })
    idx = _seasonal_pick(g, hist)
    picked = g.loc[idx, "crop"]
    if picked != "西红柿":
        return False, f"选到「{picked}」，应为同月历史相对收益最优的「西红柿」（字典序陷阱：土豆）"
    return True, "季节基线选取同月历史相对收益最优作物（西红柿）"


# ------------------------------------------------------------------ P0-4
def p0_4_relative_return_ranking():
    """Profit/Chase 基线必须基于预测相对收益（forecast/anchor-1），不得用跨作物绝对价格。"""
    from decision_engine.final import backtest as BT
    t = pd.Timestamp("2025-07-10")
    # 价格水平差异大：绝对价高者与相对涨幅高者是不同作物
    g = pd.DataFrame({
        "date": [t, t, t], "crop": ["A", "B", "C"],
        "forecast": [10.0, 3.0, 2.0],       # 绝对价最高 = A
        "anchor_price": [9.0, 1.0, 2.5],    # A:+11%, B:+200%, C:-20% → 相对最优 = B
        "fc_low": [9.5, 2.0, 1.0], "HRI": [50.0, 50.0, 50.0], "market_risk": [50.0, 50.0, 50.0],
    })
    sc = BT.strategy_scores(g)
    if "s_profit" not in sc or "s_chase" not in sc:
        return False, "缺少 s_profit / s_chase"
    pick_profit = g.loc[sc["s_profit"].idxmax(), "crop"]
    pick_chase = g.loc[sc["s_chase"].idxmax(), "crop"]
    if pick_profit != "B":
        return False, f"Profit 基线选到「{pick_profit}」（绝对价最高），应为相对收益最高「B」"
    if pick_chase != "B":
        return False, f"Chase 基线选到「{pick_chase}」，应为相对涨幅最高「B」"
    return True, "Profit/Chase 基线均按预测相对收益（forecast/anchor-1）排序"


# ------------------------------------------------------------------ P0-5a
def p0_5_cutoff_step_applied():
    """cutoff_step_days 必须真正生效（切点应按步长抽稀）。"""
    from decision_engine.final import backtest as BT
    src = (DE_SRC / "decision_engine" / "final" / "backtest.py").read_text(encoding="utf-8")
    if "step = pd.Timedelta" not in src:
        return False, "backtest.py 中 `step = pd.Timedelta(...)` 从未被使用（参数未实现）"
    import decision_engine.final.backtest as M
    if not hasattr(M, "_select_cutoffs"):
        return False, "缺少 _select_cutoffs 抽稀函数 → cutoff_step_days 未生效"
    p = M.build_panel()
    d7 = M._select_cutoffs(sorted(p["date"].unique()), 7)
    d30 = M._select_cutoffs(sorted(p["date"].unique()), 30)
    if not (len(d30) < len(d7)):
        return False, f"step=30 切点数({len(d30)}) 未少于 step=7({len(d7)})"
    return True, f"切点抽稀生效：step7={len(d7)} > step30={len(d30)}（原始实现两者都等于全部交易日）"


# ------------------------------------------------------------------ P0-5b
def p0_5_random_reproducible():
    """Random 基线必须可跨进程复现，不得依赖 Python hash()。"""
    src = (DE_SRC / "decision_engine" / "final" / "backtest.py").read_text(encoding="utf-8")
    if "abs(hash(" in src:
        return False, "仍使用 abs(hash(str(t)))（受 PYTHONHASHSEED 影响，不可跨进程复现）"
    from decision_engine.final import backtest as M
    if not hasattr(M, "_cutoff_seed"):
        return False, "缺少 _cutoff_seed 确定性种子函数"
    import subprocess
    code = (
        "import os,sys;sys.path.insert(0,os.environ['DSRC']);"
        "import pandas as pd;from decision_engine.final.backtest import _cutoff_seed;"
        "print(_cutoff_seed(pd.Timestamp('2025-07-10')))"
    )
    outs = []
    for seed in ("0", "12345"):
        env = dict(os.environ, PYTHONHASHSEED=seed, DSRC=str(DE_SRC))
        outs.append(subprocess.run([sys.executable, "-c", code], env=env,
                                   capture_output=True, text=True).stdout.strip())
    if len(set(outs)) != 1 or not outs[0]:
        return False, f"跨 PYTHONHASHSEED 结果不一致: {outs}"
    return True, f"确定性种子跨进程一致 ({outs[0]})"


# ------------------------------------------------------------------ P0-6
def p0_6_strategy_naming():
    """策略命名不得把「绝对价格水平最高」冒充「利润最优」（P0-4/P0-6 报告一致性）。"""
    from decision_engine.final import backtest as M
    strs = set(M.STRATS.keys())
    if "Profit_only" in strs:
        return False, "仍存在 Profit_only（实际为跨作物绝对价格排序，命名不准确）"
    need = {"Highest_forecast_return", "Highest_price_level", "Chase_price_momentum"}
    missing = need - strs
    if missing:
        return False, f"策略集合缺少明确定义的基线 {sorted(missing)}"
    return True, f"策略集合口径明确：{sorted(strs)}"


TESTS = [
    ("P0-1 HRI 前缀不变性", p0_1_prefix_invariance),
    ("P0-2 前瞻标签右删失", p0_2_fwd_right_censored),
    ("P0-3 季节基线 argmax", p0_3_seasonal_argmax),
    ("P0-4 相对收益基线", p0_4_relative_return_ranking),
    ("P0-5a 切点步长生效", p0_5_cutoff_step_applied),
    ("P0-5b 随机基线可复现", p0_5_random_reproducible),
    ("P0-6 策略命名一致性", p0_6_strategy_naming),
]


def main():
    for name, fn in TESTS:
        check(name, fn)
    n_ok = sum(1 for _, ok, _ in RESULTS if ok)
    print(f"\n== {n_ok}/{len(RESULTS)} PASS ==")
    # 写结果
    out = EXP / "results" / "p0_regression_result.csv"
    out.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(RESULTS, columns=["test", "passed", "note"]).to_csv(
        out, index=False, encoding="utf-8-sig")
    return 0 if n_ok == len(RESULTS) else 1


if __name__ == "__main__":
    sys.exit(main())
