# -*- coding: utf-8 -*-
"""Phase 7：Long-Horizon target 构造（严格来自冻结数据，只读）。

针对 horizon N（日历天），对每个 anchor 日 t 生成三类候选目标（均要求 t+N ≤ 数据末日）：

  - `target_lh_end_{N}`        端点：t+N 之前最近一次观测的价格（单点）
  - `target_lh_win_{N}_{w}`    尾窗：区间 (t+N-w, t+N] 内已有观测的均价（w ∈ {7,14,30}）
  - `target_lh_full_{N}`       全程：(t, t+N] 内已有观测的均价（与现有 Final 短期口径一致）

同时记录窗口内实际观测数（暴露 ~32% 日历日缺失），供样本量审计使用。
"""
from __future__ import annotations
from typing import Dict, List

import numpy as np
import pandas as pd

from .common import LONG_HORIZONS, NEAR_WINDOWS


def target_col_name(kind: str, h: int, w: int | None = None) -> str:
    """统一 target 列命名（单一入口，避免字符串散落）。"""
    if kind == "end":
        return f"target_lh_end_{h}"
    if kind == "full":
        return f"target_lh_full_{h}"
    if kind == "win":
        return f"target_lh_win_{h}_{w}"
    raise ValueError(f"unknown kind: {kind}")


def add_long_horizon_targets(df: pd.DataFrame,
                             horizons: List[int] = None,
                             near_windows: List[int] = None) -> pd.DataFrame:
    horizons = list(horizons or LONG_HORIZONS)
    near_windows = list(near_windows or NEAR_WINDOWS)
    d = df.sort_values(["crop", "date"]).reset_index(drop=True).copy()
    last_day = np.datetime64(pd.to_datetime(d["date"]).max().date(), "D")

    cols: Dict[str, np.ndarray] = {}
    for h in horizons:
        cols[target_col_name("end", h)] = np.full(len(d), np.nan)
        cols[target_col_name("full", h)] = np.full(len(d), np.nan)
        cols[f"target_lh_obs_full_{h}"] = np.zeros(len(d), dtype=int)
        for w in near_windows:
            cols[target_col_name("win", h, w)] = np.full(len(d), np.nan)
            cols[f"target_lh_obs_win_{h}_{w}"] = np.zeros(len(d), dtype=int)

    for _crop, sub in d.groupby("crop", sort=False):
        sub = sub.sort_values("date")
        dates = sub["date"].values.astype("datetime64[D]")
        px = sub["price_per_kg"].values.astype(float)
        idx = sub.index.values
        n = len(sub)
        for j in range(n):
            t = dates[j]
            for h in horizons:
                t_end = t + np.timedelta64(h, "D")
                if t_end > last_day:
                    continue                                  # 窗口必须完整落在数据范围内
                # ---- 端点：t+N 之前最近一次观测
                pos = np.searchsorted(dates, t_end, side="right") - 1
                if pos > j:
                    cols[target_col_name("end", h)][idx[j]] = px[pos]
                # ---- 全程 (t, t+N]
                lo = np.searchsorted(dates, t, side="right")
                hi = np.searchsorted(dates, t_end, side="right")
                if hi > lo:
                    v = px[lo:hi]
                    cols[target_col_name("full", h)][idx[j]] = float(v.mean())
                    cols[f"target_lh_obs_full_{h}"][idx[j]] = int(len(v))
                # ---- 尾窗 (t+N-w, t+N]
                for w in near_windows:
                    lo2 = np.searchsorted(dates, t_end - np.timedelta64(w, "D"), side="right")
                    if hi > lo2:
                        vv = px[lo2:hi]
                        cols[target_col_name("win", h, w)][idx[j]] = float(vv.mean())
                        cols[f"target_lh_obs_win_{h}_{w}"][idx[j]] = int(len(vv))

    for k, v in cols.items():
        d[k] = v
    return d


def target_availability(df: pd.DataFrame,
                        horizons: List[int] = None) -> pd.DataFrame:
    """逐 (crop, horizon) 报告三类目标的非空样本量与非重叠样本量。"""
    horizons = list(horizons or LONG_HORIZONS)
    rows = []
    for crop in sorted(df["crop"].unique()):
        sub = df[df["crop"] == crop].sort_values("date")
        for h in horizons:
            end_col = target_col_name("end", h)
            full_col = target_col_name("full", h)
            nonnull = int(sub[full_col].notna().sum())
            # 非重叠（起点间隔 ≥ h 日历天，贪心）
            anchors = sub.loc[sub[full_col].notna(), "date"].sort_values()
            last_taken = None
            non_overlap = 0
            for dt in anchors:
                if last_taken is None or (dt - last_taken).days >= h:
                    non_overlap += 1
                    last_taken = dt
            rows.append({
                "crop": crop, "horizon": h,
                "n_nonnull_end": int(sub[end_col].notna().sum()),
                "n_nonnull_full": nonnull,
                "n_nonoverlap": non_overlap,
                "mean_obs_full": float(sub.loc[sub[full_col].notna(),
                                              f"target_lh_obs_full_{h}"].mean()) if nonnull else np.nan,
            })
    return pd.DataFrame(rows)


if __name__ == "__main__":
    from .common import load_frozen_dataset, write_csv_artifact
    base = load_frozen_dataset()
    ds = add_long_horizon_targets(base)
    av = target_availability(ds)
    write_csv_artifact(av, "long_horizon_target_availability.csv")
    print(av.groupby("horizon")[["n_nonnull_full", "n_nonoverlap"]].mean().round(1).to_string())