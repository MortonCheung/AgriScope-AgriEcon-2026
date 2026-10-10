#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""P0 最终回归测试：季节策略未来标签泄漏 / 随机基准混合统计量 / 价格模型标签 purge。

用法：
    EXPERIMENTS_DE_SRC=<原始或修复代码 src> PROJECT_ROOT=<experiments>/root python3 tests/p0_final_regression.py
未修复代码应 FAIL，修复后应 PASS。
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
import pandas as pd

RESULTS = []
H = 30


def check(name, fn):
    try:
        ok, note = fn()
    except Exception as e:
        ok, note = False, f"EXCEPTION {type(e).__name__}: {e}"
        traceback.print_exc()
    RESULTS.append((name, bool(ok), note))
    print(f"[{'PASS' if ok else 'FAIL'}] {name} — {note}", flush=True)


# ================================================================ P0-A
def t_a1_synthetic_unmatured():
    """历史样本的标签窗口尚未在决策日闭合时，不得参与季节评分。"""
    from decision_engine.final.backtest import _seasonal_pick
    t = pd.Timestamp("2025-03-10")
    g = pd.DataFrame({"date": [t, t], "crop": ["西红柿", "黄瓜"],
                      "forecast": [1.0, 2.0], "anchor_price": [1.0, 1.0],
                      "predicted_return": [0.1, 0.2]})
    hist = pd.DataFrame({
        # 西红柿：date < t，但标签窗口未闭合（label_avail_date = date+31 > t）→ 泄漏样本
        # 黄瓜  ：标签窗口已闭合（label_avail_date <= t）→ 合法样本
        "date": pd.to_datetime(["2025-03-05", "2025-01-01"]),
        "crop": ["西红柿", "黄瓜"],
        "month": [3, 3],
        "rel_ret": [0.90, 0.10],
        "label_avail_date": pd.to_datetime(["2025-04-05", "2025-02-01"]),
    })
    picked = g.loc[_seasonal_pick(g, hist), "crop"]
    if picked != "黄瓜":
        return False, f"选到「{picked}」＝使用了未成熟标签（应为已闭合窗口的「黄瓜」）"
    return True, "未成熟标签被正确排除，选中窗口已闭合的作物"


def t_a2_future_perturbation_invariance():
    """决定日 t 之后的价格/标签被改动，t 处的季节选择不得改变。

    构造：仅有一个样本 d* 的标签窗口在 t 处尚未闭合（date < t 但 label_avail_date > t），
    且 d* 是该月 argmax 的唯一决定者。扰动 d*（模拟 t 之后价格变化改变的标签）：
      · 未修复（仅用 date<t）→ 选择随扰动改变 → 违反不变性
      · 修复后（label_avail_date<=t）→ 选择不变
    """
    from decision_engine.final.backtest import _seasonal_pick
    t = pd.Timestamp("2025-03-10")
    g = pd.DataFrame({"date": [t, t], "crop": ["西红柿", "黄瓜"],
                      "forecast": [1.0, 2.0], "anchor_price": [1.0, 1.0],
                      "predicted_return": [0.1, 0.2]})

    def make(star_rel_ret):
        return pd.DataFrame({
            "date": pd.to_datetime(["2025-02-20", "2025-01-15"]),
            "crop": ["西红柿", "黄瓜"],
            "month": [3, 3],
            "rel_ret": [star_rel_ret, 0.20],
            "label_avail_date": pd.to_datetime(["2025-03-23", "2025-02-15"]),
        })

    base, pert = make(0.90), make(-0.90)
    p_base = g.loc[_seasonal_pick(g, base), "crop"]
    p_pert = g.loc[_seasonal_pick(g, pert), "crop"]
    if p_base != p_pert:
        return False, f"选择随 t 之后的标签变动而改变（{p_base} → {p_pert}）＝使用了未成熟标签"
    if p_base != "黄瓜":
        return False, f"选中「{p_base}」，应为窗口已闭合且不受扰动影响的「黄瓜」"
    return True, "t 之后标签被扰动时选择保持不变（未成熟样本 d* 被正确排除）"


# ================================================================ P0-B
def t_b_random_high_hri_share():
    """随机策略的高 HRI 命中率应为池内占比（≈10%），不得恒为 100%。"""
    from decision_engine.final.backtest import build_panel, _expectation_rec, _select_cutoffs
    p = build_panel()
    dates = _select_cutoffs(sorted(p["date"].unique()), 30)
    vals = []
    for t in dates:
        g = p[p["date"] == t]
        if len(g) < 4:
            continue
        r = _expectation_rec(t, g)
        hv = r["high_hri"]
        if not isinstance(hv, float):
            return False, f"high_hri 类型为 {type(hv).__name__}（应为 float 占比）"
        vals.append(hv)
    m = float(np.mean(vals))
    if m > 0.5:
        return False, f"随机策略平均高 HRI 命中率 = {m:.3f}（>0.5，疑似仍被布尔化）"
    return True, f"随机策略平均高 HRI 命中率 = {m:.3f}（池内占比口径，符合 90 分位阈值约 10% 的预期）"


# ================================================================ P0-C
def t_c_fold_purge():
    """训练/测试样本的前瞻标签窗口必须落在各自边界之内。"""
    from decision_engine.models.backtest import FOLDS, fold_mask, target_horizon_days
    ds = pd.read_parquet(EXP / "root/models/data/snapshots/final_v1/datasets/decision_dataset_沈阳.parquet",
                         columns=["date", "crop", "target_mean_price_next_30d"])
    ds["date"] = pd.to_datetime(ds["date"])
    h = 30
    bad = []
    for fold in FOLDS:
        tr, te = fold_mask(ds, fold, purge_days=h)
        tr_max = ds.loc[tr, "date"].max()
        te_max = ds.loc[te, "date"].max()
        if tr_max + pd.Timedelta(days=h) > pd.Timestamp(fold["train_end"]):
            bad.append(f"{fold['name']} train_max={tr_max.date()} +{h}d 超过 train_end")
        if te_max + pd.Timedelta(days=h) > pd.Timestamp(fold["test_end"]):
            bad.append(f"{fold['name']} test_max={te_max.date()} +{h}d 超过 test_end")
    if bad:
        return False, "; ".join(bad)
    # 反例：接近 train_end 的样本必须被剔除
    f0 = FOLDS[0]
    tr, _ = fold_mask(ds, f0, purge_days=h)
    near = ds[(ds["date"] > pd.Timestamp(f0["train_end"]) - pd.Timedelta(days=h)) &
              (ds["date"] <= pd.Timestamp(f0["train_end"]))]
    leaked = tr.loc[near.index].sum()
    if leaked:
        return False, f"仍有 {int(leaked)} 条窗口跨越 train_end 的训练样本"
    return True, "三折训练/测试样本的前瞻窗口均被正确 purge"


TESTS = [
    ("P0-A1 季节策略未成熟标签", t_a1_synthetic_unmatured),
    ("P0-A2 未来扰动不变性", t_a2_future_perturbation_invariance),
    ("P0-B  随机高HRI命中率口径", t_b_random_high_hri_share),
    ("P0-C  训练/测试标签 purge", t_c_fold_purge),
]


def main():
    for n, f in TESTS:
        check(n, f)
    n_ok = sum(1 for _, ok, _ in RESULTS if ok)
    print(f"\n== {n_ok}/{len(RESULTS)} PASS ==")
    out = EXP / "results" / "p0_final_regression_result.csv"
    pd.DataFrame(RESULTS, columns=["test", "passed", "note"]).to_csv(out, index=False, encoding="utf-8-sig")
    return 0 if n_ok == len(RESULTS) else 1


if __name__ == "__main__":
    sys.exit(main())
