# -*- coding: utf-8 -*-
"""C6: HRI 最终统计审计 —— 时间序列依赖下的稳健验证（§24/§25/§26）。

禁止把高度重叠窗口当独立样本做普通 p-value。
这里同时使用三种适配时间序列的方法：
  1) 非重叠窗口（每 w 周抽 1 个样本）
  2) 循环块 bootstrap（circular block bootstrap，块长 = 窗口长度）→ 高/低组差的经验零分布
  3) HAC / Newey-West 回归（fwd_return ~ HRI_percentile，robust t 统计量）
并给出最终可宣称的边界（raw strong / conditional weak）。
"""
from __future__ import annotations
import json
from typing import Dict, List

import numpy as np
import pandas as pd

from decision_engine.final.fcommon import (FINAL_EVAL_DIR, REPORTS_DIR, ensure_dir,
                                           write_json, now_stamp)

WINDOWS = [4, 8, 12]
N_BOOT = 2000
SEED = 42


def _circ_block_sample(x: np.ndarray, n: int, block: int, rng) -> np.ndarray:
    """循环块重采样（circular block bootstrap）：保持块内时间依赖。"""
    m = len(x)
    n_blocks = int(np.ceil(n / block))
    starts = rng.randint(0, m, size=n_blocks)
    idx = np.concatenate([(np.arange(s, s + block) % m) for s in starts])[:n]
    return x[idx]


def _block_bootstrap_p(x_hi: np.ndarray, x_lo: np.ndarray, block: int, n_boot=N_BOOT, seed=SEED) -> float:
    """两组独立循环块 bootstrap 的零分布检验（保持块内自相关与组结构）。

    [P0-5 FIX] 原实现把高/低两组直接拼接后循环块重采样，再 `rng.shuffle` 打散、
    再按固定位置 len(x_hi) 切分 → 等价于一次**普通置换检验**，
    **破坏了块结构与组内时间依赖**，与「循环块 bootstrap」的声明不符。
    现改为标准两样本分块 bootstrap：在**各组的中心化序列**上分别做循环块重采样
    （H0：两组均值相等），以重采样均值差的分布构造双侧经验 p 值。
    """
    x_hi = np.asarray(x_hi, dtype=float)
    x_lo = np.asarray(x_lo, dtype=float)
    n_hi, n_lo = len(x_hi), len(x_lo)
    if n_hi < 2 * block or n_lo < 2 * block:
        return np.nan
    obs = float(np.mean(x_hi) - np.mean(x_lo))
    ch = x_hi - np.mean(x_hi)      # 中心化：构造 H0 下的零分布
    cl = x_lo - np.mean(x_lo)
    rng = np.random.RandomState(seed)
    diffs = np.empty(n_boot)
    for b in range(n_boot):
        bh = _circ_block_sample(ch, n_hi, block, rng)
        bl = _circ_block_sample(cl, n_lo, block, rng)
        diffs[b] = np.mean(bh) - np.mean(bl)
    p = float(np.mean(np.abs(diffs) >= abs(obs)))
    return max(p, 1.0 / n_boot)


def run(city: str = "沈阳") -> Dict[str, object]:
    ensure_dir(REPORTS_DIR / "tables")
    h = pd.read_parquet(FINAL_EVAL_DIR / f"hri_weekly_{city}.parquet")
    h = h[h["HRI"].notna()].copy()
    rows = []
    import statsmodels.api as sm
    for w in WINDOWS:
        f = f"fwd_{w}w"
        if f not in h.columns:
            continue
        for crop, sub in h.groupby("crop", sort=False):
            sub = sub.sort_values(["iso_year", "iso_week"]).reset_index(drop=True)
            s = sub.dropna(subset=[f, "hri_pct"])
            if len(s) < 60:
                continue
            hi = s[s["hri_pct"] >= 80][f].values
            lo = s[s["hri_pct"] <= 50][f].values
            if len(hi) < 15 or len(lo) < 15:
                continue
            # 1) [P0-5 FIX] 真·非重叠：每 w 周抽 1 个观测（stride = w）。
            #    原 stride = max(2, w // 2) 在 w=12 时为 6，相邻样本的前瞻窗口仍重叠 50%，
            #    「非重叠窗口」称谓不成立，会把高度相关的样本当独立样本做普通 p 值。
            stride = int(w)
            nonover = s.iloc[::stride]
            hi_n = nonover[nonover["hri_pct"] >= 80][f].values
            lo_n = nonover[nonover["hri_pct"] <= 50][f].values
            p_non = np.nan
            if len(hi_n) >= 8 and len(lo_n) >= 8:
                from scipy import stats
                p_non = float(stats.mannwhitneyu(hi_n, lo_n, alternative="two-sided")[1])
            # 2) block bootstrap
            p_boot = _block_bootstrap_p(hi, lo, block=w)
            # 3) HAC / Newey-West
            X = sm.add_constant(s["hri_pct"].values.astype(float))
            y = s[f].values.astype(float)
            try:
                ols = sm.OLS(y, X).fit(cov_type="HAC", cov_kwds={"maxlags": w})
                beta = float(ols.params[1]); t = float(ols.tvalues[1]); p_hac = float(ols.pvalues[1])
            except Exception:
                beta = t = p_hac = np.nan
            from scipy import stats as st2
            p_raw = float(st2.mannwhitneyu(hi, lo, alternative="two-sided")[1])
            rows.append({
                "city": city, "crop": crop, "window_w": w,
                "n_high": len(hi), "n_low": len(lo),
                "mean_diff": float(np.mean(hi) - np.mean(lo)),
                "p_raw_overlapping": p_raw,
                "p_nonoverlap": p_non,
                "p_block_bootstrap": p_boot,
                "hac_beta_per_pct": beta, "hac_t": t, "hac_p": p_hac,
                "nonoverlap_stride": stride,
                # 时间序列稳健显著性 = 块 bootstrap 与 HAC 双双通过（两个独立的时间序列适配检验）
                "robust_significant": bool((p_boot < 0.05) and np.isfinite(p_hac) and (p_hac < 0.05)),
                "raw_significant": bool(p_raw < 0.05),
            })
    own = pd.DataFrame(rows)
    d = own.copy()
    # 合并多城市结果（避免覆盖）
    fp = REPORTS_DIR / "tables" / "hri_timeseries_validation.csv"
    if fp.exists():
        try:
            old = pd.read_csv(fp)
            old = old[old["city"] != city]
            d = pd.concat([old, d], ignore_index=True)
        except Exception:
            pass
    d.to_csv(fp, index=False, encoding="utf-8-sig")

    out = {"city": city, "n_tests": int(len(own)), "ts": now_stamp()}
    if len(own):
        out["n_robust_sig_12w"] = int(((own["window_w"] == 12) & own["robust_significant"]).sum())
        out["n_raw_sig_12w"] = int(((own["window_w"] == 12) & own["raw_significant"]).sum())
        out["n_12w"] = int((own["window_w"] == 12).sum())
        out["mean_hac_beta_12w"] = float(own[own["window_w"] == 12]["hac_beta_per_pct"].mean())
        out["mean_p_raw_12w"] = float(own[own["window_w"] == 12]["p_raw_overlapping"].mean())
        out["mean_p_boot_12w"] = float(own[own["window_w"] == 12]["p_block_bootstrap"].mean())
    jp = REPORTS_DIR / "tables" / "hri_timeseries_summary.json"
    merged = {}
    if jp.exists():
        try:
            merged = json.loads(jp.read_text())
        except Exception:
            merged = {}
    merged[city] = out
    write_json(merged, jp)
    return out


if __name__ == "__main__":
    print(run("沈阳"))
    print(run("朝阳"))