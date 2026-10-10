#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
周级主表 04_marts/shenbei_weekly_system.csv
事件窗口高频表 04_marts/event_window_2026_high_frequency.csv

【周聚合规则（用户第九条：必须注明实际规则）】
- 降水：**周累计 sum** + 周内最大日降水 max
- 温度/湿度/ET0：**周均值 mean**
- 土壤湿度：**周均值 mean**（仅对有观测的日求均值，不用插值填补）
- 遥感：**周内最近观测 nearest observation**（同日表规则），并记录该观测日期；
         若该周无任何有效场景 → NaN（不插值）
- 玉米价格：**周内观测值**（官方本身为周报，通常一周一条）
- 物候：取该周内出现次数最多的阶段（mode）

【2024–2026 三年同期对照】用于 2026 异常判定（用户第七条）。
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[3]
M = ROOT / "04_marts"
DAILY = M / "shenbei_daily_system.csv"

PHENO_P = ROOT / "03_clean" / "phenology" / "corn_phenology_2026.csv"


def load_daily() -> pd.DataFrame:
    d = pd.read_csv(DAILY)
    d["dt"] = pd.to_datetime(d["date"])
    d["week_start"] = (d["dt"] - pd.to_timedelta(d["dt"].dt.weekday, unit="D")).dt.strftime("%Y-%m-%d")
    return d


def nearest_in_week(g: pd.DataFrame, col: str, datecol: str = "ndvi_obs_date"):
    """周内最近观测：取该周内 ndvi_obs_date 最新的一条所对应的指数值。"""
    sub = g[g[col].notna()]
    if sub.empty:
        return pd.Series({f"{col}": np.nan, f"{col}_obs_date": None})
    last = sub.sort_values(datecol).iloc[-1]
    return pd.Series({f"{col}": last[col], f"{col}_obs_date": last[datecol]})


def main() -> None:
    if not DAILY.exists():
        print("[FAIL] 缺少日级主表，请先运行 113")
        return
    d = load_daily()

    # ---------- 物候 ----------
    pheno = None
    if PHENO_P.exists():
        try:
            ph = pd.read_csv(PHENO_P)
            dc = [c for c in ph.columns if "date" in c.lower()]
            sc = [c for c in ph.columns if "stage" in c.lower() or "period" in c.lower()]
            if dc and sc:
                ph = ph[[dc[0], sc[0]]].rename(columns={dc[0]: "date", sc[0]: "stage"})
                ph["date"] = ph["date"].astype(str)
                pheno = dict(zip(ph["date"], ph["stage"]))
        except Exception as e:
            print(f"  [WARN] 物候读取失败 {e}")

    rows = []
    for wk, g in d.groupby("week_start"):
        g = g.sort_values("date")
        r = {
            "week_start": wk,
            "week_end": (pd.Timestamp(wk) + pd.Timedelta(days=6)).strftime("%Y-%m-%d"),
            "year": int(wk[:4]),
            "precip_sum": g["precipitation_sum"].sum(min_count=1),
            "precip_max": g["precipitation_sum"].max(),
            "temperature_mean": g["temperature_mean"].mean(),
            "relative_humidity_mean": g.get("relative_humidity_2m_mean", pd.Series(dtype=float)).mean(),
            "et0_mean": g.get("et0_fao_evapotranspiration", pd.Series(dtype=float)).mean(),
            "soil_moisture_3_9cm": g["soil_moisture_3_9cm"].mean(),
            "soil_moisture_9_27cm": g["soil_moisture_9_27cm"].mean(),
            "n_days_soil": int(g["soil_moisture_3_9cm"].notna().sum()),
        }
        for col in ["ndvi_nearest", "evi_nearest", "ndwi_nearest", "mndwi_nearest"]:
            if col in g:
                s = nearest_in_week(g, col)
                r[col] = s[col]
                if col == "ndvi_nearest":
                    r["ndvi_obs_date"] = s[f"{col}_obs_date"]
        r["corn_price_farmgate"] = g["corn_price_farmgate"].dropna().iloc[-1] \
            if g["corn_price_farmgate"].notna().any() else np.nan
        # 事件
        evs = [e for e in g["event_flag"].dropna().unique()]
        r["disaster_event"] = ";".join(evs) if evs else ""
        r["intervention_event"] = bool(g["intervention_flag"].any())
        # 物候
        if pheno:
            st = [pheno[x] for x in g["date"] if x in pheno]
            r["phenology_stage"] = max(set(st), key=st.count) if st else None
        else:
            r["phenology_stage"] = None
        # 覆盖度/质量
        r["source_coverage"] = "|".join(sorted({
            "weather" if g["precipitation_sum"].notna().any() else "",
            "soil" if g["soil_moisture_3_9cm"].notna().any() else "",
            "rs" if ("ndvi_nearest" in g and g["ndvi_nearest"].notna().any()) else "",
            "price" if g["corn_price_farmgate"].notna().any() else "",
        } - {""}))
        rows.append(r)

    wk = pd.DataFrame(rows).sort_values("week_start").reset_index(drop=True)
    wk.to_csv(M / "shenbei_weekly_system.csv", index=False, encoding="utf-8-sig")
    print(f"[OK] 周级主表 {len(wk)} 周 -> 04_marts/shenbei_weekly_system.csv")
    print(f"     {wk.week_start.min()} ~ {wk.week_start.max()}")
    print(wk.groupby("year").size().to_string())

    # ---------- 2026 事件窗口高频表 ----------
    ew = d[(d["date"] >= "2026-06-15") & (d["date"] <= "2026-08-31")].copy()
    # 补逐时降水（若有）
    hp = ROOT / "03_clean" / "weather" / "pnb_hourly.parquet"
    if hp.exists():
        try:
            h = pd.read_parquet(hp)
            tc = [c for c in h.columns if "time" in c.lower() or "date" in c.lower()]
            pc = [c for c in h.columns if "precip" in c.lower()]
            if tc and pc:
                h[tc[0]] = pd.to_datetime(h[tc[0]])
                h["date"] = h[tc[0]].dt.strftime("%Y-%m-%d")
                daily_h = h.groupby("date").agg(
                    precip_hourly_max=(pc[0], "max"), n_hours=(pc[0], "size"))
                ew = ew.merge(daily_h.reset_index(), on="date", how="left")
        except Exception as e:
            print(f"  [WARN] 逐时降水合并失败 {e}")
    ew.to_csv(M / "event_window_2026_high_frequency.csv", index=False, encoding="utf-8-sig")
    print(f"\n[OK] 2026 事件窗口表 {len(ew)} 天 -> 04_marts/event_window_2026_high_frequency.csv")
    print(f"     {ew.date.min()} ~ {ew.date.max()}")

    # 2026 异常 vs 2024/2025 同期（周级）
    print("\n=== 2026 周 NDVI vs 2024/2025 同期基线 ===")
    if "ndvi_nearest" in wk:
        wk["doy_week"] = pd.to_datetime(wk["week_start"]).dt.isocalendar().week
        base = wk[wk.year.isin([2024, 2025])].groupby("doy_week")["ndvi_nearest"].mean()
        cur = wk[wk.year == 2026].set_index("doy_week")["ndvi_nearest"]
        comp = pd.DataFrame({"ndvi_2026": cur, "ndvi_baseline_24_25": base})
        comp = comp.dropna()
        if len(comp):
            comp["anomaly"] = comp["ndvi_2026"] - comp["ndvi_baseline_24_25"]
            # ★ 契约对齐：CropState_timeseries 要求 date + spatial_unit 两个字段。
            #   date = 该 ISO 周在事件年(2026)的 week_start（直接取自周表，避免解析歧义）；
            #   spatial_unit = 聚合口径（区级耕地）。
            w26 = (wk[wk.year == 2026].assign(doy_week=wk[wk.year == 2026]["week_start"]
                                              .apply(lambda d: pd.Timestamp(d).isocalendar().week))
                   .drop_duplicates("doy_week").set_index("doy_week")["week_start"])
            comp = comp.reset_index()          # doy_week 转回列
            comp["date"] = comp["doy_week"].map(w26)
            comp["spatial_unit"] = "PNB_cropland_district"
            comp["aggregation_note"] = ("区级耕地聚合；NDVI 取该周最近可用低云 S2 场景；"
                                        "基线为 2024/2025 同 ISO 周均值")
            comp = comp[["date", "doy_week", "spatial_unit", "ndvi_2026",
                         "ndvi_baseline_24_25", "anomaly", "aggregation_note"]]
            comp = comp.sort_values("doy_week")
            print(comp.round(4).head(16).to_string())
            comp.to_csv(M / "ndvi_anomaly_2026_vs_baseline.csv", index=False, encoding="utf-8-sig")


if __name__ == "__main__":
    main()
