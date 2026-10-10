# -*- coding: utf-8 -*-
"""Phase 11 前置：逐作物统计画像 + **程序化** pilot 作物选择（§47 禁止凭印象）。

指标（全部由冻结价格序列程序计算）：
  - cv              价格变异系数 std/mean
  - logret_sigma    日对数收益标准差（波动强度）
  - eta2_month      月份方差解释比 eta²（季节强度，1 - 组内方差/总方差）
  - acf_365         日历重采样后 lag-365 自相关（年周期强度）

选择：低波动 = min logret_sigma；高波动 = max logret_sigma；季节强 = max eta2_month。
去重后最多 3 个。
"""
from __future__ import annotations
from typing import Dict, List

import numpy as np
import pandas as pd

from .common import load_frozen_dataset, write_csv_artifact


def crop_profiles(df: pd.DataFrame | None = None) -> pd.DataFrame:
    ds = df if df is not None else load_frozen_dataset()
    rows: List[Dict] = []
    for crop, sub in ds.groupby("crop"):
        sub = sub.sort_values("date")
        p = sub["price_per_kg"].astype(float).values
        lp = np.log(p)
        lr = np.diff(lp)
        # eta²（月份）
        tmp = pd.DataFrame({"m": pd.to_datetime(sub["date"]).dt.month.values, "p": p})
        grand = tmp["p"].mean()
        ss_total = float(((tmp["p"] - grand) ** 2).sum())
        ss_within = float(tmp.groupby("m")["p"].transform(lambda x: (x - x.mean()) ** 2).sum())
        eta2 = 1 - ss_within / ss_total if ss_total > 0 else np.nan
        # lag-365 自相关（日历重采样 + 线性插值）
        s = pd.Series(p, index=pd.to_datetime(sub["date"]))
        cal = s.resample("D").interpolate(limit_direction="both")
        acf365 = float(cal.autocorr(lag=365)) if len(cal) > 400 else np.nan
        rows.append({
            "crop": crop, "n_obs": int(len(p)),
            "mean_price": round(float(np.mean(p)), 4),
            "cv": round(float(np.std(p) / np.mean(p)), 4) if np.mean(p) else np.nan,
            "logret_sigma": round(float(np.std(lr)), 4) if len(lr) else np.nan,
            "eta2_month": round(float(eta2), 4) if np.isfinite(eta2) else np.nan,
            "acf_365": round(acf365, 4) if np.isfinite(acf365) else np.nan,
        })
    return pd.DataFrame(rows).sort_values("crop").reset_index(drop=True)


def select_pilot_crops(prof: pd.DataFrame) -> Dict[str, str]:
    lo = prof.sort_values("logret_sigma").iloc[0]
    hi = prof.sort_values("logret_sigma", ascending=False).iloc[0]
    se = prof.sort_values("eta2_month", ascending=False).iloc[0]
    out = {"low_volatility": lo["crop"], "high_volatility": hi["crop"],
           "strong_seasonality": se["crop"]}
    return out


def pilot_crop_list(prof: pd.DataFrame) -> List[str]:
    sel = select_pilot_crops(prof)
    seen, out = set(), []
    for v in sel.values():
        if v not in seen:
            seen.add(v); out.append(v)
    return out


if __name__ == "__main__":
    prof = crop_profiles()
    write_csv_artifact(prof, "crop_profiles.csv")
    print(prof.to_string(index=False))
    print("pilot:", select_pilot_crops(prof), pilot_crop_list(prof))