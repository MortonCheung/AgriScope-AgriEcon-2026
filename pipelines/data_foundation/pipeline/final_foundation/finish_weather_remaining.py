"""FDF-Task1 补全：多坐标单请求，批量补齐缺失城市的 ERA5 2010–2026。

Open-Meteo 支持 latitude/longitude 逗号分隔 → 一次请求返回多城市数组，
可将剩余 4 城压缩为 2 个请求，规避按小时限流。
"""
from __future__ import annotations

import csv
import json
import subprocess
import time
import urllib.parse
from datetime import date, timedelta
from pathlib import Path

import pandas as pd

ROOT = next(p for p in Path(__file__).resolve().parents if (p / "AgriScope").is_dir() and (p / "data").is_dir()) / "data/raw/retained_source/city_data"
META = Path(next(p for p in Path(__file__).resolve().parents if (p / "AgriScope").is_dir() and (p / "data").is_dir())) / "data/raw/metadata/cities.csv"
OM = "https://archive-api.open-meteo.com/v1/archive"
UA = "Mozilla/5.0"
TZ = "Asia/Shanghai"
START = "2010-01-01"
NAME2SLUG = {"沈阳": "shenyang", "铁岭": "tieling", "锦州": "jinzhou",
             "丹东": "dandong", "大连": "dalian", "朝阳": "chaoyang"}
CORE = ["temperature_2m_max", "temperature_2m_min", "temperature_2m_mean", "precipitation_sum",
        "relative_humidity_2m_mean", "wind_speed_10m_max", "shortwave_radiation_sum",
        "et0_fao_evapotranspiration"]
EXTRA = ["pressure_msl_mean", "surface_pressure_mean", "dew_point_2m_mean", "snowfall_sum",
         "snow_depth_mean", "cloud_cover_mean", "vapour_pressure_deficit_max", "wind_gusts_10m_max"]


def call(lats, lons, vars_, start, end, tries=60):
    p = {"latitude": ",".join(map(str, lats)), "longitude": ",".join(map(str, lons)),
         "start_date": start, "end_date": end, "daily": ",".join(vars_),
         "timezone": TZ, "models": "era5"}
    url = f"{OM}?{urllib.parse.urlencode(p)}"
    for i in range(tries):
        r = subprocess.run(["curl", "-s", "--max-time", "180", url, "-H", f"User-Agent: {UA}"],
                           capture_output=True)
        try:
            js = json.loads(r.stdout.decode("utf-8", "replace").strip())
        except Exception:
            time.sleep(20); continue
        if isinstance(js, dict) and (js.get("error") or js.get("reason")):
            print(f"  [wait] {str(js.get('reason'))[:70]}")
            time.sleep(900); continue
        return js
    return None


def main():
    cities = [c for c in csv.DictReader(META.open(encoding="utf-8")) if c["city"] in NAME2SLUG]
    end = (date.today() - timedelta(days=8)).isoformat()
    # 找缺失城市（未生成 weather_daily_era5.csv）
    missing = []
    for c in cities:
        slug = NAME2SLUG[c["city"]]
        out = ROOT / slug / "data" / "weather_daily_era5.csv"
        if not out.exists():
            missing.append(c)
    print(f"待补城市: {[c['city'] for c in missing]}")
    if not missing:
        print("无缺失"); return
    lats = [c["latitude"] for c in missing]
    lons = [c["longitude"] for c in missing]
    for tag, vars_ in (("core", CORE), ("extra", EXTRA)):
        js = call(lats, lons, vars_, START, end)
        if js is None:
            print(f"[FAIL] {tag}"); continue
        arr = js if isinstance(js, list) else [js]
        for c, one in zip(missing, arr):
            slug = NAME2SLUG[c["city"]]
            raw_dir = ROOT.parent / "data/raw" / "web_captures" / slug / "weather" / "era5" / "2010_2026"
            raw_dir.mkdir(parents=True, exist_ok=True)
            out_dir = ROOT / slug / "data"
            out_dir.mkdir(parents=True, exist_ok=True)
            f = raw_dir / f"era5_{c['city']}_{tag}_{START}_{end}.json"
            one.update({"_request": {"latitude": c["latitude"], "longitude": c["longitude"],
                                     "start_date": START, "end_date": end, "daily": vars_,
                                     "timezone": TZ, "models": "era5"},
                        "_retrieval_date": date.today().isoformat(), "_source": OM,
                        "_batch": "multi_location"})
            f.write_text(json.dumps(one, ensure_ascii=False), encoding="utf-8")
            d = one.get("daily") or {}
            if "time" in d:
                df = pd.DataFrame({"date": d["time"]})
                for k, v in d.items():
                    if k != "time":
                        df[k] = v
                df.insert(0, "city", c["city"])
                df["timezone"] = TZ
                df["weather_source"] = "open-meteo-era5"
                df["data_type"] = "reanalysis"
                for kk in ("latitude", "longitude", "elevation"):
                    df[kk] = one.get(kk)
                name = "weather_daily_era5.csv" if tag == "core" else "weather_extra_daily_era5.csv"
                df.to_csv(out_dir / name, index=False, encoding="utf-8-sig")
                print(f"[OK] {c['city']} {tag} {len(df)} 天")
        time.sleep(10)


if __name__ == "__main__":
    main()
