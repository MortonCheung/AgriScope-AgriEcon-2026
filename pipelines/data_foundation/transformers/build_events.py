"""极端天气事件识别与事件研究面板。

事件来源说明（诚实标注）：
公开灾情报道（水利厅汛情快报等）大多为异步加载或仅为新闻稿，可结构化提取的
事件数量有限。因此这里采用**气象观测数据驱动的极端事件识别**：
基于六城市逐日再分析数据识别暴雨/高温/干旱/寒潮过程，
判定阈值固定、可复现、可回溯到具体日期，不依赖主观描述。

公开报道另存为 fact_disaster_reports（辅助证据），不混入本表。
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

ROOT = next(p for p in Path(__file__).resolve().parents if (p / "AgriScope").is_dir() and (p / "data").is_dir())
MARTS = ROOT / "city_data/reference/marts"
CURATED = ROOT / "city_data/reference/curated"
for d in (MARTS, CURATED):
    d.mkdir(parents=True, exist_ok=True)

TARGET_CITIES = ["沈阳", "铁岭", "朝阳", "锦州", "丹东", "大连"]


def identify_events(daily: pd.DataFrame) -> pd.DataFrame:
    """按固定阈值从日值识别极端天气过程。"""
    out = []
    for city, g in daily.groupby("city"):
        g = g.sort_values("date").reset_index(drop=True)
        n = len(g)

        # 1) 暴雨过程：单日 >=50mm，或连续窗口 3 日累计 >=100mm
        i = 0
        while i < n:
            if g.loc[i, "precip"] >= 50:
                j = i
                while j + 1 < n and g.loc[j + 1, "precip"] >= 25:
                    j += 1
                seg = g.loc[i:j]
                out.append({
                    "city": city, "event_type": "rainstorm",
                    "start_date": seg["date"].iloc[0], "end_date": seg["date"].iloc[-1],
                    "max_daily_rain": float(seg["precip"].max()),
                    "accumulated_rain": float(seg["precip"].sum()),
                    "severity": 3 if seg["precip"].max() >= 100 else (2 if seg["precip"].max() >= 50 else 1),
                })
                i = j + 1
            else:
                i += 1

        # 2) 连续强降水：3 日滑动累计 >=100mm
        roll3 = g["precip"].rolling(3, min_periods=3).sum()
        for idx in np.where(roll3.values >= 100)[0]:
            out.append({
                "city": city, "event_type": "heavy_rain",
                "start_date": g.loc[max(0, idx - 2), "date"], "end_date": g.loc[idx, "date"],
                "max_daily_rain": float(g.loc[max(0, idx - 2):idx, "precip"].max()),
                "accumulated_rain": float(roll3.iloc[idx]),
                "severity": 2,
            })

        # 3) 高温过程：连续 >=2 日最高温 >=35℃
        hot = (g["temp_max"] >= 35).astype(int)
        grp = (hot != hot.shift()).cumsum()
        for _, seg in g[hot == 1].groupby(grp[hot == 1]):
            if len(seg) >= 2:
                out.append({
                    "city": city, "event_type": "heat",
                    "start_date": seg["date"].iloc[0], "end_date": seg["date"].iloc[-1],
                    "max_daily_rain": float(seg["precip"].max()),
                    "accumulated_rain": float(seg["precip"].sum()),
                    "severity": 3 if seg["temp_max"].max() >= 38 else 2,
                })

        # 4) 干旱：生长季（4-9月）连续 >=20 日降水 <1mm
        m = pd.to_datetime(g["date"]).dt.month
        gs = g[m.isin([4, 5, 6, 7, 8, 9])].reset_index(drop=True)
        dry = (gs["precip"] < 1).astype(int)
        grp2 = (dry != dry.shift()).cumsum()
        for _, seg in gs[dry == 1].groupby(grp2[dry == 1]):
            if len(seg) >= 20:
                out.append({
                    "city": city, "event_type": "drought",
                    "start_date": seg["date"].iloc[0], "end_date": seg["date"].iloc[-1],
                    "max_daily_rain": float(seg["precip"].max()),
                    "accumulated_rain": float(seg["precip"].sum()),
                    "severity": 3 if len(seg) >= 30 else 2,
                })

    df = pd.DataFrame(out)
    if df.empty:
        return df
    df = df.drop_duplicates(subset=["city", "event_type", "start_date", "end_date"])
    df = df.sort_values(["city", "start_date"]).reset_index(drop=True)
    df["event_id"] = ["EV" + str(i + 1).zfill(5) for i in range(len(df))]
    return df


def weekly_exposure(events: pd.DataFrame, weekly: pd.DataFrame) -> pd.DataFrame:
    """事件拆分到城市周：跨周事件在每一个重叠周都标记，并保留 event_id。"""
    if events.empty:
        return pd.DataFrame()
    rows = []
    ev = events.copy()
    ev["start_date"] = pd.to_datetime(ev["start_date"])
    ev["end_date"] = pd.to_datetime(ev["end_date"])
    wk = weekly.copy()
    wk["week_start"] = pd.to_datetime(wk["week_start"])
    wk["week_end"] = pd.to_datetime(wk["week_end"])

    for city, w in wk.groupby("city"):
        ce = ev[ev["city"] == city]
        for _, r in w.iterrows():
            hit = ce[(ce["start_date"] <= r["week_end"]) & (ce["end_date"] >= r["week_start"])]
            rows.append({
                "city": city, "week_start": r["week_start"].date(),
                "extreme_weather_flag": int(len(hit) > 0),
                "event_count": int(len(hit)),
                "heavy_rain_event": int((hit["event_type"] == "heavy_rain").any()),
                "flood_event": int((hit["event_type"] == "rainstorm").any()),
                "heat_event": int((hit["event_type"] == "heat").any()),
                "drought_event": int((hit["event_type"] == "drought").any()),
                "max_event_severity": int(hit["severity"].max()) if len(hit) else 0,
                "event_ids": "|".join(hit["event_id"].tolist()),
            })
    return pd.DataFrame(rows)


def event_study(events: pd.DataFrame, weekly: pd.DataFrame,
                price_panel: pd.DataFrame) -> pd.DataFrame:
    """围绕每次城市级事件，取 ±4 周的价格与天气，供事件前后对比分析。

    价格使用**省级**真实序列（城市级农产品价格不可得），
    并在 price_geo_level 字段明确标注，绝不冒充城市价格。
    """
    if events.empty:
        return pd.DataFrame()
    ev = events.copy()
    ev["start_date"] = pd.to_datetime(ev["start_date"])
    wk = weekly.copy()
    wk["week_start"] = pd.to_datetime(wk["week_start"])

    prov = price_panel.copy()
    prov["week_start"] = pd.to_datetime(prov["week_start"])

    rows = []
    for _, e in ev.iterrows():
        city_w = wk[wk["city"] == e["city"]].sort_values("week_start")
        if city_w.empty:
            continue
        # 事件起始日所在周
        idx = (city_w["week_start"] - e["start_date"]).abs().idxmin()
        base_pos = city_w.index.get_loc(idx)
        for rel in range(-4, 5):
            pos = base_pos + rel
            if pos < 0 or pos >= len(city_w):
                continue
            row = city_w.iloc[pos]
            for crop in prov["crop"].unique():
                pr = prov[(prov["crop"] == crop) &
                          (prov["week_start"] == row["week_start"])]
                if pr.empty:
                    continue
                pr = pr.iloc[0]
                rows.append({
                    "event_id": e["event_id"], "city": e["city"],
                    "event_type": e["event_type"], "severity": e["severity"],
                    "event_start": e["start_date"].date(),
                    "crop": crop,
                    "relative_week": rel,
                    "week_start": row["week_start"].date(),
                    "price": pr.get("price_mean"),
                    "price_geo_level": "province",
                    "rainfall": row["precip_sum"],
                    "temp_mean": row["temp_mean"],
                    "temp_max": row["temp_max"],
                })
    df = pd.DataFrame(rows)
    if df.empty:
        return df
    df = df.sort_values(["event_id", "crop", "relative_week"])
    g = df.groupby(["event_id", "crop"], dropna=False)
    df["price_change"] = g["price"].diff()
    return df


def main() -> None:
    daily = pd.read_parquet(MARTS / "fact_weather_daily.parquet")
    daily = daily[daily["city"].isin(TARGET_CITIES)].copy()
    weekly = pd.read_parquet(MARTS / "fact_weather_weekly.parquet")
    weekly = weekly[weekly["city"].isin(TARGET_CITIES)].copy()
    price_panel = pd.read_parquet(MARTS / "province_crop_week_panel.parquet")

    events = identify_events(daily)
    cols = ["event_id", "city", "event_type", "start_date", "end_date",
            "max_daily_rain", "accumulated_rain", "severity"]
    for c in cols:
        if c not in events.columns:
            events[c] = np.nan
    events = events[cols]
    events["province"] = "辽宁省"
    events["district"] = ""
    events["source"] = "open-meteo-era5-reanalysis 日值阈值识别"
    events["description"] = ""
    # 无法从公开材料获得的字段一律留空（禁止推测）
    for c in ["flood_flag", "drought_flag", "heat_flag", "hail_flag", "wind_flag",
              "affected_crop_area", "damaged_crop_area", "crop_failure_area",
              "drainage_area", "economic_loss", "city_avg_rainfall",
              "max_hourly_rainfall"]:
        events[c] = np.nan
    events.to_parquet(MARTS / "fact_disaster_events.parquet", index=False)
    events.to_csv(MARTS / "fact_disaster_events.csv", index=False, encoding="utf-8-sig")
    print(f"[OK] fact_disaster_events {len(events)} 条")
    print("   类型:", dict(events["event_type"].value_counts()))
    print("   城市:", dict(events["city"].value_counts()))

    exp = weekly_exposure(events, weekly)
    exp.to_parquet(MARTS / "weekly_disaster_exposure.parquet", index=False)
    exp.to_csv(MARTS / "weekly_disaster_exposure.csv", index=False, encoding="utf-8-sig")
    print(f"[OK] weekly_disaster_exposure {len(exp)} 行，"
          f"命中极端周 {int(exp['extreme_weather_flag'].sum())}")

    es = event_study(events, weekly, price_panel)
    es.to_parquet(MARTS / "event_study_panel.parquet", index=False)
    es.to_csv(MARTS / "event_study_panel.csv", index=False, encoding="utf-8-sig")
    print(f"[OK] event_study_panel {len(es)} 行")


if __name__ == "__main__":
    main()
