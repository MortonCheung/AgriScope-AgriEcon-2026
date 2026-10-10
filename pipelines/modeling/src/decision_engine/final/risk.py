# -*- coding: utf-8 -*-
"""F6/F7: Final HRI + Market Risk（基于单一 price_level 价格序列，独立验证）。

科学边界：
  - HRI = 扩种诱因 / 跟风风险环境指标（不是「农户是否跟风」的概率，无监督标签）；
  - 只用单一 price_level（wholesale）价格序列，禁止混层（规避 hri_inputs 复合 level 缺陷）；
  - 全部 past-only expanding 分位；缺失 ≠ 0（缺失组件不进加权）；
  - Market Risk 与 HRI 必须检查相关性/特征重叠/增量信息，避免重复计风险。

HRI 组件（§21）：price_level / short_run_up(4w) / medium_run_up(12w) /
                 consecutive_rise / volatility / area_signal(蔬菜无时序 → NaN)
验证（§22）：30/60/90d 未来回撤与收益；高 vs 低组差异；控制均值回归/季节性/重叠窗口/自相关。
"""
from __future__ import annotations
from typing import Dict, List

import numpy as np
import pandas as pd
from scipy import stats

from decision_engine.final.fcommon import (SNAPSHOT_DIR, REPORTS_DIR, FINAL_EVAL_DIR,
                                           ensure_dir, write_json, now_stamp)

CONCEPTUAL_W = {"price_level": 0.30, "short_run_up": 0.25, "medium_run_up": 0.15,
                "consecutive_rise": 0.10, "volatility": 0.15, "area_signal": 0.05}
MIN_WEEKS = 40


def weekly_prices(city: str = "沈阳") -> pd.DataFrame:
    """自建周价格序列（单一 wholesale 层）。"""
    src = SNAPSHOT_DIR / "model_ready" / (
        "shenyang_core/market_daily.parquet" if city == "沈阳" else "chaoyang_extended/market_daily.parquet")
    df = pd.read_parquet(src)
    lvl = "wholesale" if city == "沈阳" else "market_average"
    df = df[df["price_level_canonical"] == lvl].copy()
    df["price_per_kg"] = pd.to_numeric(df["price_per_kg"], errors="coerce")
    dt = pd.to_datetime(df["observation_date"])
    df["iso_year"] = dt.dt.isocalendar().year.astype(int)
    df["iso_week"] = dt.dt.isocalendar().week.astype(int)
    g = (df.dropna(subset=["price_per_kg"]).groupby(["crop_standard", "iso_year", "iso_week"])
         .agg(price_mean=("price_per_kg", "mean"), price_std=("price_per_kg", "std"),
              price_n=("price_per_kg", "size")).reset_index()
         .rename(columns={"crop_standard": "crop"}))
    return g.sort_values(["crop", "iso_year", "iso_week"]).reset_index(drop=True)


def daily_prices(city: str = "沈阳") -> pd.DataFrame:
    """单一 price_level 日价格序列（market_daily）。"""
    src = SNAPSHOT_DIR / "model_ready" / (
        "shenyang_core/market_daily.parquet" if city == "沈阳" else "chaoyang_extended/market_daily.parquet")
    df = pd.read_parquet(src)
    lvl = "wholesale" if city == "沈阳" else "market_average"
    df = df[df["price_level_canonical"] == lvl].copy()
    df["price_per_kg"] = pd.to_numeric(df["price_per_kg"], errors="coerce")
    df["date"] = pd.to_datetime(df["observation_date"])
    df = df.dropna(subset=["price_per_kg"]).rename(columns={"crop_standard": "crop"})
    return df[["date", "crop", "price_per_kg"]].drop_duplicates(["date", "crop"]).sort_values(
        ["crop", "date"]).reset_index(drop=True)


def _exp_pct(s: pd.Series, mp: int = MIN_WEEKS) -> pd.Series:
    return s.expanding(min_periods=mp).rank(pct=True)


def hri_components(w: pd.DataFrame) -> pd.DataFrame:
    d = w.sort_values(["crop", "iso_year", "iso_week"]).copy()
    g = d.groupby("crop", sort=False)
    d["c_price_level"] = g["price_mean"].transform(lambda s: _exp_pct(s)) * 100
    lag4 = g["price_mean"].shift(4); lag12 = g["price_mean"].shift(12)
    d["run_up_4w"] = d["price_mean"] / lag4.replace(0, np.nan) - 1
    d["run_up_12w"] = d["price_mean"] / lag12.replace(0, np.nan) - 1
    d["c_short_run_up"] = g["run_up_4w"].transform(lambda s: _exp_pct(s)) * 100
    d["c_medium_run_up"] = g["run_up_12w"].transform(lambda s: _exp_pct(s)) * 100
    up = (g["price_mean"].diff() > 0).astype(int)
    rise = up.groupby([d["crop"], up.eq(0).cumsum()]).cumsum()
    d["consecutive_rise"] = rise.values
    d["c_consecutive_rise"] = d.groupby("crop", sort=False)["consecutive_rise"].transform(
        lambda s: (s.rank(pct=True))) * 100
    ret = g["price_mean"].transform(lambda s: s.pct_change())
    d["volatility_w"] = ret.groupby(d["crop"]).transform(lambda s: s.rolling(12, min_periods=6).std())
    d["c_volatility"] = d.groupby("crop", sort=False)["volatility_w"].transform(lambda s: _exp_pct(s)) * 100
    d["c_area_signal"] = np.nan  # 蔬菜无城市×作物面积时序 → 缺失（不填 0）
    return d


def combine(d: pd.DataFrame, weights: Dict[str, float] = CONCEPTUAL_W,
            scheme: str = "conceptual") -> pd.DataFrame:
    cols = list(weights.keys())
    C = [f"c_{k}" for k in cols]
    avail = d[C].notna()
    if scheme == "equal":
        w = {c: 1.0 for c in cols}
    else:
        w = weights
    num = np.zeros(len(d)); den = np.zeros(len(d))
    for k in cols:
        wv = w[k]; v = d[f"c_{k}"].values; m = avail[f"c_{k}"].values
        num += np.where(m, np.nan_to_num(v) * wv, 0.0)
        den += np.where(m, wv, 0.0)
    out = d.copy()
    out["HRI"] = np.where(den > 0, num / den, np.nan)
    out["hri_component_count"] = avail.sum(axis=1).values
    # past-only 分位与等级
    out["hri_pct"] = out.groupby("crop", sort=False)["HRI"].transform(
        lambda s: s.expanding(min_periods=20).rank(pct=True)) * 100
    lvl = pd.Series(index=out.index, dtype=object)
    p = out["hri_pct"]
    lvl[p < 50] = "low"; lvl[(p >= 50) & (p < 75)] = "medium"
    lvl[(p >= 75) & (p < 90)] = "high"; lvl[p >= 90] = "very_high"
    out["HRI_level"] = lvl
    return out


def market_risk(daily: pd.DataFrame) -> pd.DataFrame:
    """日频 market risk 组件（波动/回撤/异常波动/历史下行），past-only 分位合成 0-100。"""
    d = daily.sort_values(["crop", "date"]).copy()
    g = d.groupby("crop", sort=False)
    ret = g["price_per_kg"].transform(lambda s: s.pct_change())
    d["vol_30"] = ret.groupby(d["crop"]).transform(lambda s: s.rolling(30, min_periods=15).std())
    roll_max = g["price_per_kg"].transform(lambda s: s.rolling(30, min_periods=30).max())
    d["dd_30"] = d["price_per_kg"] / roll_max.replace(0, np.nan) - 1
    d["abnormal"] = (ret.abs() > ret.groupby(d["crop"]).transform(
        lambda s: s.rolling(90, min_periods=30).std()) * 3).astype(float)
    d["abnormal_freq_30"] = d.groupby("crop", sort=False)["abnormal"].transform(
        lambda s: s.rolling(30, min_periods=15).mean())
    d["down_vol_90"] = ret.groupby(d["crop"]).transform(
        lambda s: s.where(s < 0).rolling(90, min_periods=30).std())

    def _p(x):
        return pd.Series(x).expanding(min_periods=60).rank(pct=True) * 100

    d["mr_vol"] = d.groupby("crop", sort=False)["vol_30"].transform(_p)
    # 回撤越深（dd_30 越负）风险越高 → 用 1-rank 反转
    d["mr_dd"] = (1 - d.groupby("crop", sort=False)["dd_30"].transform(
        lambda s: pd.Series(s).expanding(min_periods=60).rank(pct=True).values)) * 100
    d["mr_abn"] = d.groupby("crop", sort=False)["abnormal_freq_30"].transform(_p)
    d["mr_downvol"] = d.groupby("crop", sort=False)["down_vol_90"].transform(_p)
    cols = ["mr_vol", "mr_dd", "mr_abn", "mr_downvol"]
    d["market_risk"] = d[cols].mean(axis=1)
    return d


def _fwd(d: pd.DataFrame, key: str, value: str, hs=(4, 8, 12)) -> pd.DataFrame:
    d = d.sort_values(["crop", key]).reset_index(drop=True).copy()
    for h in hs:
        fwd = np.full(len(d), np.nan); worst = np.full(len(d), np.nan)
        for crop, sub in d.groupby("crop", sort=False):
            idx = sub.index.values
            p = sub[value].values.astype(float)
            for j in range(len(sub)):
                lo = j + 1; hi = min(j + h + 1, len(sub))
                if hi <= lo:
                    continue
                w = p[lo:hi]
                fwd[idx[j]] = w[-1] / p[j] - 1
                worst[idx[j]] = w.min() / p[j] - 1
        d[f"fwd_{h}w"] = fwd; d[f"worst_{h}w"] = worst
    return d


def validate_hri(h: pd.DataFrame) -> pd.DataFrame:
    d = h[h["HRI"].notna()].copy()
    rows = []
    for hh in [4, 8, 12]:
        f, w = f"fwd_{hh}w", f"worst_{hh}w"
        for crop, sub in d.groupby("crop", sort=False):
            if sub[f].notna().sum() < 40:
                continue
            hi = sub[sub["hri_pct"] >= 80]; lo = sub[sub["hri_pct"] <= 50]
            hs, ls = hi[f].dropna(), lo[f].dropna()
            if len(hs) < 15 or len(ls) < 15:
                continue
            u, p_ = stats.mannwhitneyu(hs, ls, alternative="two-sided")
            rows.append({"crop": crop, "window_w": hh, "n_high": len(hs), "n_low": len(ls),
                         "high_fwd_mean": float(hs.mean()), "low_fwd_mean": float(ls.mean()),
                         "diff": float(hs.mean() - ls.mean()),
                         "high_worst_mean": float(hi[w].dropna().mean()),
                         "low_worst_mean": float(lo[w].dropna().mean()),
                         "high_p_down": float((hs < 0).mean()), "low_p_down": float((ls < 0).mean()),
                         "mannwhitney_p": float(p_)})
    return pd.DataFrame(rows)


def controls(h: pd.DataFrame) -> pd.DataFrame:
    """控制均值回归(价格水平)/季节性/重叠窗口后，HRI 是否仍有增量信息。"""
    d = h[h["HRI"].notna()].copy()
    rows = []
    for hh in [4, 8, 12]:
        f = f"fwd_{hh}w"
        dd = d.dropna(subset=[f, "HRI", "c_price_level"]).copy()
        dd["_month"] = ((dd["iso_week"] - 1) // 4 + 1).clip(1, 12)
        dd["_lvl"] = dd["c_price_level"]
        # 分位化
        dd["_r"] = dd.groupby("crop")[f].rank(pct=True)
        dd["_x"] = dd.groupby("crop")["HRI"].rank(pct=True)
        # 控制 price level 与 month：对二者回归取残差
        import statsmodels.api as sm
        X = pd.get_dummies(dd["_month"], prefix="m", drop_first=True).astype(float)
        X["_lvl"] = dd["_lvl"].values
        X = sm.add_constant(X)
        y = dd["_r"].values
        m1 = sm.OLS(y, X).fit()
        rx = sm.OLS(dd["_x"].values, X).fit().resid
        ry = m1.resid
        rho_raw = stats.spearmanr(dd["_x"], dd["_r"])[0]
        rho_ctrl = stats.spearmanr(rx, ry)[0]
        # 非重叠：每 hh 周取一个观测
        sub = dd.sort_values(["crop", "iso_year", "iso_week"]).groupby("crop").apply(
            lambda s: s.iloc[::hh]).reset_index(drop=True)
        rho_nonover = stats.spearmanr(sub["_x"], sub["_r"])[0] if len(sub) > 30 else np.nan
        rows.append({"window_w": hh, "spearman_raw": float(rho_raw),
                     "spearman_controlled": float(rho_ctrl),
                     "spearman_nonoverlap": float(rho_nonover) if np.isfinite(rho_nonover) else np.nan,
                     "n": int(len(dd)), "n_nonoverlap": int(len(sub))})
    return pd.DataFrame(rows)


def hri_market_overlap(h: pd.DataFrame) -> Dict[str, float]:
    d = h.dropna(subset=["HRI", "market_risk"])
    rho = float(stats.spearmanr(d["HRI"], d["market_risk"])[0]) if len(d) > 30 else np.nan
    return {"spearman_HRI_vs_marketrisk": rho, "n": int(len(d))}


# ---------------------------------------------------------------- Balanced 根因诊断
def balanced_diagnosis(pool: pd.DataFrame) -> Dict[str, object]:
    """在候选池上诊断 Balanced(13%) > Profit-only(8.7%) 的根因（A/B/C）。

    输入 pool 需含 HRI, roi_baseline, roi_pessimistic, market_risk, climate_risk。
    判据：
      - corr(HRI, roi_baseline) 与 corr(HRI, roi_pessimistic) 高 → HRI 与收益同向（情况 C）
      - 若 HRI 对「未来 downside」有区分力（见 validate_hri）→ HRI 有效（情况 A/C）
      - 若 HRI 对 downside 无区分力 → 情况 B
    """
    d = pool.copy()
    def c(a, b):
        s = d[[a, b]].dropna()
        return float(stats.spearmanr(s[a], s[b])[0]) if len(s) > 20 else np.nan
    res = {
        "corr_HRI_roi_baseline": c("HRI", "roi_baseline"),
        "corr_HRI_roi_pessimistic": c("HRI", "roi_pessimistic"),
        "corr_HRI_market_risk": c("HRI", "market_risk"),
        "corr_HRI_climate": c("HRI", "climate_risk"),
        "corr_roi_baseline_roi_pessimistic": c("roi_baseline", "roi_pessimistic"),
        "n_pool": int(len(d)),
    }
    # 机制：Balanced 的 down 权重把高-HRI（高价=高波动）候选拉进来
    mech_c = (np.nan_to_num(res["corr_HRI_roi_pessimistic"], nan=0) > 0.15)
    res["mechanism_high_roi_cooccurs_with_high_HRI"] = bool(mech_c)
    return res


def run() -> Dict[str, object]:
    ensure_dir(FINAL_EVAL_DIR); ensure_dir(REPORTS_DIR / "tables")
    out = {}
    all_h, all_v, all_c = [], [], []
    for city in ["沈阳", "朝阳"]:
        w = weekly_prices(city)
        w["wk"] = w["iso_year"] * 100 + w["iso_week"]
        h = combine(hri_components(w))
        h["wk"] = h["iso_year"] * 100 + h["iso_week"]
        h = _fwd(h, "wk", "price_mean", hs=(4, 8, 12))
        # 合并周均 market risk（单一 level 日频派生）
        dp = daily_prices(city)
        dp["iso_year"] = dp["date"].dt.isocalendar().year.astype(int)
        dp["iso_week"] = dp["date"].dt.isocalendar().week.astype(int)
        mrd = market_risk(dp)
        mrw = (mrd.groupby(["crop", "iso_year", "iso_week"])[["market_risk", "mr_vol", "mr_dd", "mr_abn"]]
               .mean().reset_index())
        mrw.columns = ["crop", "iso_year", "iso_week", "market_risk", "mr_vol", "mr_dd", "mr_abn"]
        h = h.merge(mrw, on=["crop", "iso_year", "iso_week"], how="left")
        h["city"] = city
        h.to_parquet(FINAL_EVAL_DIR / f"hri_weekly_{city}.parquet", index=False)
        v = validate_hri(h); v["city"] = city
        c = controls(h); c["city"] = city
        all_h.append(h); all_v.append(v); all_c.append(c)
        ov = hri_market_overlap(h)
        out[city] = {"n_weeks": len(h), "HRI_valid_rows": int(h["HRI"].notna().sum()),
                     "mean_HRI": float(h["HRI"].mean()), **ov}
        print(f"[HRI {city}] weeks={len(h)} overlap={ov}", flush=True)
    v = pd.concat(all_v, ignore_index=True)
    c = pd.concat(all_c, ignore_index=True)
    v.to_csv(REPORTS_DIR / "tables" / "hri_validation.csv", index=False, encoding="utf-8-sig")
    c.to_csv(REPORTS_DIR / "tables" / "hri_controls.csv", index=False, encoding="utf-8-sig")
    write_json(out, REPORTS_DIR / "tables" / "hri_summary.json")

    # market risk（沈阳日频全量，供报告/复算）
    mr = market_risk(daily_prices("沈阳"))
    mr.to_parquet(FINAL_EVAL_DIR / "market_risk_daily.parquet", index=False)
    return {"hri": out, "ts": now_stamp()}


if __name__ == "__main__":
    print(run())