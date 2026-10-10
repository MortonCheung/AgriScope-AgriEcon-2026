"""FDF-Task1：天气扩展 QC + 新旧重叠验证。

输入：interim/_final/weather_daily_era5land.csv（新，2010–2026）
      interim/weather_daily.csv（旧，2021–2026，best_match）
输出：
  01_weather/WEATHER_EXTENSION_QC.csv
  01_weather/WEATHER_OVERLAP_VALIDATION.csv
  01_weather/WEATHER_OVERLAP_YEARLY.csv
"""
from __future__ import annotations

from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = next(p for p in Path(__file__).resolve().parents if (p / "AgriScope").is_dir() and (p / "data").is_dir()) / "data/raw/retained_source/city_data"
OUT = ROOT / "reference" / "final_foundation" / "01_weather"
OUT.mkdir(parents=True, exist_ok=True)
SLUG = {"shenyang": "沈阳", "tieling": "铁岭", "jinzhou": "锦州",
        "dandong": "丹东", "dalian": "大连", "chaoyang": "朝阳"}


def load_new(slug):
    """优先正式基准 ERA5；回退 ERA5-Land 温度变体。"""
    base = ROOT / slug / "data"
    for name in ("weather_daily_era5.csv", "weather_daily_era5land.csv"):
        p = base / name
        if p.exists():
            d = pd.read_csv(p, encoding="utf-8-sig", low_memory=False)
            if "precipitation_sum" in d.columns and d["precipitation_sum"].notna().any():
                return d, name
    p = base / "weather_daily_era5land.csv"
    if p.exists():
        return pd.read_csv(p, encoding="utf-8-sig", low_memory=False), p.name
    return None, None


def load_old(slug):
    """旧天气 legacy：五城为 CSV；沈阳为 parquet（结构不同）。"""
    base = ROOT / slug / "data"
    p = base / "weather_daily.csv"
    if p.exists():
        return pd.read_csv(p, encoding="utf-8-sig", low_memory=False)
    for cand in ("shenyang_weather_daily.parquet",):
        q = base / cand
        if q.exists():
            try:
                d = pd.read_parquet(q)
                d = d.reset_index() if d.index.name else d
                # 归一到 (date, temperature_2m_mean, precipitation_sum)
                ren = {}
                dcol = next((c for c in ("date", "time", "datetime", "Date") if c in d.columns), None)
                if dcol and dcol != "date":
                    ren[dcol] = "date"
                for src, dst in (("temp_mean", "temperature_2m_mean"), ("tmean", "temperature_2m_mean"),
                                 ("precip", "precipitation_sum"), ("precip_sum", "precipitation_sum"),
                                 ("precipitation", "precipitation_sum")):
                    if src in d.columns and dst not in d.columns:
                        ren[src] = dst
                return d.rename(columns=ren)
            except Exception:
                return None
    return None


def qc() -> pd.DataFrame:
    rows = []
    for slug, cn in SLUG.items():
        d, _src = load_new(slug)
        if d is None:
            rows.append({"city": cn, "qc_status": "NO_DATA"}); continue
        d["date"] = pd.to_datetime(d["date"], errors="coerce")
        dd = d["date"].dropna()
        first, last = dd.min().date(), dd.max().date()
        exp = (last - first).days + 1
        uq = dd.dt.date.nunique()
        dup = len(dd) - uq
        tcol = "temperature_2m_mean" if "temperature_2m_mean" in d.columns else "temperature_2m_max"
        pcol = "precipitation_sum"
        null_t = int(d[tcol].isna().sum()); null_p = int(d[pcol].isna().sum())
        rows.append({
            "city": cn, "first_date": str(first), "last_date": str(last),
            "expected_days": exp, "actual_days": uq, "missing_days": exp - uq,
            "duplicate_days": dup,
            "null_temperature_days": null_t,
            "null_precipitation_days": null_p,
            "min_temperature": round(float(d[tcol].min()), 2),
            "max_temperature": round(float(d[tcol].max()), 2),
            "max_daily_precipitation": round(float(d[pcol].max()), 2) if d[pcol].notna().any() else None,
            "neg_precip_days": int((d[pcol] < 0).sum()),
            "rh_out_of_range_days": int(((d["relative_humidity_2m_mean"] < 0) |
                                         (d["relative_humidity_2m_mean"] > 100)).sum())
            if "relative_humidity_2m_mean" in d.columns else 0,
            "source_file": _src,
            "has_precipitation": bool(d[pcol].notna().any()),
            "qc_status": "PASS_ERA5" if (_src == "weather_daily_era5.csv" and d[pcol].notna().all()
                                         and null_t == 0 and dup == 0)
                         else ("PASS_ERA5LAND_TEMP_ONLY" if _src == "weather_daily_era5land.csv"
                               else "CHECK"),
            "notes": "ERA5 统一基准" if _src == "weather_daily_era5.csv" else "ERA5-Land 温度变体(降水/风/辐射缺失)",
        })
    return pd.DataFrame(rows)


OLD_MAP = {"temperature_2m_mean": "temp_mean", "temperature_2m_max": "temp_max",
           "temperature_2m_min": "temp_min", "precipitation_sum": "precip",
           "relative_humidity_2m_mean": "humidity", "wind_speed_10m_max": "wind_max",
           "shortwave_radiation_sum": "sunshine_radiation", "et0_fao_evapotranspiration": "et0"}


def overlap() -> tuple[pd.DataFrame, pd.DataFrame]:
    rows, yrows = [], []
    for slug, cn in SLUG.items():
        new, _src = load_new(slug)
        old = load_old(slug)
        if new is None or old is None:
            continue
        new["date"] = pd.to_datetime(new["date"], errors="coerce")
        old["date"] = pd.to_datetime(old["date"], errors="coerce")
        # 旧表列名映射到新表
        old2 = old.rename(columns={v: k for k, v in OLD_MAP.items()})
        m = pd.merge(new[["date", "temperature_2m_mean", "precipitation_sum"]],
                     old2[["date", "temperature_2m_mean", "precipitation_sum"]],
                     on="date", suffixes=("_new", "_old")).dropna()
        if len(m) == 0:
            continue
        for var, unit in (("temperature_2m_mean", "degC"), ("precipitation_sum", "mm")):
            a, b = m[f"{var}_new"], m[f"{var}_old"]
            diff = a - b
            rows.append({
                "city": cn, "variable": var, "unit": unit, "n_overlap_days": len(m),
                "new_mean": round(float(a.mean()), 3), "old_mean": round(float(b.mean()), 3),
                "bias_new_minus_old": round(float(diff.mean()), 4),
                "MAE": round(float(diff.abs().mean()), 4),
                "RMSE": round(float(np.sqrt((diff ** 2).mean())), 4),
                "pearson_r": round(float(a.corr(b)), 4) if a.std() and b.std() else None,
            })
        # 逐年偏差（温度、降水）
        mm = m.copy(); mm["year"] = mm["date"].dt.year
        for y, g in mm.groupby("year"):
            yrows.append({
                "city": cn, "year": int(y), "n": len(g),
                "temp_bias": round(float((g["temperature_2m_mean_new"] - g["temperature_2m_mean_old"]).mean()), 4),
                "temp_mae": round(float((g["temperature_2m_mean_new"] - g["temperature_2m_mean_old"]).abs().mean()), 4),
                "precip_bias": round(float((g["precipitation_sum_new"] - g["precipitation_sum_old"]).mean()), 4),
                "precip_mae": round(float((g["precipitation_sum_new"] - g["precipitation_sum_old"]).abs().mean()), 4),
            })
    return pd.DataFrame(rows), pd.DataFrame(yrows)


if __name__ == "__main__":
    q = qc(); q.to_csv(OUT / "WEATHER_EXTENSION_QC.csv", index=False, encoding="utf-8-sig")
    print("[OK] WEATHER_EXTENSION_QC.csv", q.shape)
    print(q[["city", "first_date", "last_date", "actual_days", "missing_days", "duplicate_days", "qc_status"]].to_string(index=False))
    v, yv = overlap()
    v.to_csv(OUT / "WEATHER_OVERLAP_VALIDATION.csv", index=False, encoding="utf-8-sig")
    yv.to_csv(OUT / "WEATHER_OVERLAP_YEARLY.csv", index=False, encoding="utf-8-sig")
    print("\n[OK] WEATHER_OVERLAP_VALIDATION.csv", v.shape)
    print(v.to_string(index=False))
