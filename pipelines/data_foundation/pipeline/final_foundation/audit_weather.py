"""FDF-1a：现有天气审计 → WEATHER_EXISTING_AUDIT.csv（读真实 Raw JSON + interim CSV）。"""
from __future__ import annotations

import glob
import json
from datetime import date
from pathlib import Path

import pandas as pd

ROOT = next(p for p in Path(__file__).resolve().parents if (p / "AgriScope").is_dir() and (p / "data").is_dir()) / "data/raw/retained_source/city_data"          # city_data/
OUT = ROOT / "reference" / "final_foundation" / "00_audit"
OUT.mkdir(parents=True, exist_ok=True)
CITIES = {"shenyang": "沈阳", "tieling": "铁岭", "jinzhou": "锦州",
          "dandong": "丹东", "dalian": "大连", "chaoyang": "朝阳"}
DATASETS = ["weather_daily", "weather_extra_daily", "soil_daily"]


def expected_days(a: date, b: date) -> int:
    return (b - a).days + 1


def raw_meta(city_cn: str) -> dict:
    """从 Raw JSON 提取 coordinate/model/timezone。"""
    d = ROOT.parent / "data/raw" / "web_captures" / [k for k, v in CITIES.items() if v == city_cn][0] / "weather"
    metas = []
    for f in glob.glob(str(d / "**" / "*.json"), recursive=True):
        try:
            j = json.load(open(f, encoding="utf-8"))
        except Exception:
            continue
        if isinstance(j, dict) and "latitude" in j:
            metas.append({"file": Path(f).name, "lat": j.get("latitude"), "lon": j.get("longitude"),
                          "elev": j.get("elevation"), "tz": j.get("timezone"),
                          "vars": list((j.get("daily") or {}).keys()) or list((j.get("hourly") or {}).keys())})
    return metas


def main() -> None:
    rows = []
    for code, cn in CITIES.items():
        inter = ROOT / code / "data"
        rmeta = raw_meta(cn)
        # 取第一个有 lat 的 raw 作为代表
        rep = rmeta[0] if rmeta else {}
        for ds in DATASETS:
            p = inter / f"{ds}.csv"
            if not p.exists():
                continue
            d = pd.read_csv(p, encoding="utf-8-sig", low_memory=False)
            dcol = next((c for c in ("date", "time", "observation_date") if c in d.columns), None)
            dt = pd.to_datetime(d[dcol], errors="coerce") if dcol else pd.Series([], dtype="datetime64[ns]")
            uq = dt.dropna().dt.date.nunique()
            exp = expected_days(dt.min().date(), dt.max().date()) if len(dt.dropna()) else 0
            units = {}
            for v in ("temperature_2m_max", "temperature_2m_min", "temperature_2m_mean",
                      "precipitation_sum", "relative_humidity_2m_mean", "wind_speed_10m_max",
                      "shortwave_radiation_sum", "et0_fao_evapotranspiration"):
                if v in d.columns:
                    units[v] = d[v].dtype
            rows.append({
                "city": cn, "dataset": ds,
                "source": "Open-Meteo archive-api",
                "model": "best_match(未指定models)" if ds != "soil_daily" else "era5_land(显式)",
                "latitude": rep.get("lat"), "longitude": rep.get("lon"),
                "elevation": rep.get("elev"), "timezone": rep.get("tz"),
                "first_date": str(dt.min().date()) if len(dt.dropna()) else "",
                "last_date": str(dt.max().date()) if len(dt.dropna()) else "",
                "rows": len(d), "unique_days": int(uq),
                "missing_days": int(exp - uq) if exp else 0,
                "duplicate_days": int(len(dt.dropna()) - uq),
                "variables": ",".join([c for c in d.columns if c not in ("city", "date", "time", "observation_date")])[:400],
                "temperature_unit": "degC", "precipitation_unit": "mm", "wind_unit": "km/h",
                "notes": f"raw代表={rep.get('file','')}",
            })
    df = pd.DataFrame(rows)
    df.to_csv(OUT / "WEATHER_EXISTING_AUDIT.csv", index=False, encoding="utf-8-sig")
    print(f"[OK] WEATHER_EXISTING_AUDIT.csv {df.shape}")
    print(df[["city", "dataset", "model", "first_date", "last_date", "unique_days", "missing_days", "duplicate_days"]].to_string(index=False))


if __name__ == "__main__":
    main()
