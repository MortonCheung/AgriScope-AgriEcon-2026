"""FDF-Task1（修正版）：ERA5 显式单模型 2010–2026 六城统一气候基准。

技术事实（实测）：
  - Open-Meteo `models=era5_land` 仅提供 temperature_2m_* 与 relative_humidity_2m_mean；
    降水/风速/辐射/ET0 均为 null。
  - Open-Meteo `models=era5` 提供全部 8 个核心变量的真实值。
  → 因此正式长期基准采用 **显式 models=era5（单一模型，无自动切换）**，
     并另存 ERA5-Land 温度变体（高分辨率，仅温/湿）作补充。

输出：
  raw/weather/era5/2010_2026/era5_{city}_{core|extra}_*.json
  interim/_final/weather_daily_era5.csv            （canonical，8 核心变量）
  interim/_final/weather_extra_daily_era5.csv      （扩展变量）
"""
from __future__ import annotations

import csv
import json
import ssl
import subprocess
import time
import urllib.parse
from datetime import date, timedelta
from pathlib import Path

import pandas as pd

ROOT = next(p for p in Path(__file__).resolve().parents if (p / "AgriScope").is_dir() and (p / "data").is_dir()) / "data/raw/retained_source/city_data"
CITY_META = Path(next(p for p in Path(__file__).resolve().parents if (p / "AgriScope").is_dir() and (p / "data").is_dir())) / "data/raw/metadata/cities.csv"
OM = "https://archive-api.open-meteo.com/v1/archive"
MODEL = "era5"
TZ = "Asia/Shanghai"
START = "2010-01-01"
UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")

CORE = ["temperature_2m_max", "temperature_2m_min", "temperature_2m_mean",
        "precipitation_sum", "relative_humidity_2m_mean", "wind_speed_10m_max",
        "shortwave_radiation_sum", "et0_fao_evapotranspiration"]
EXTRA = ["pressure_msl_mean", "surface_pressure_mean", "dew_point_2m_mean",
         "snowfall_sum", "snow_depth_mean", "cloud_cover_mean",
         "vapour_pressure_deficit_max", "wind_gusts_10m_max"]


def http_json(params: dict, retries: int = 6) -> dict:
    url = f"{OM}?{urllib.parse.urlencode(params)}"
    last = None
    for a in range(retries):
        p = subprocess.run(["curl", "-s", "--max-time", "180", url,
                            "-H", f"User-Agent: {UA}"], capture_output=True)
        try:
            js = json.loads(p.stdout.decode("utf-8", "replace").strip())
        except Exception as exc:
            last = exc; time.sleep(8 * (a + 1)); continue
        if isinstance(js, dict) and (js.get("error") or js.get("reason")):
            r = str(js.get("reason") or js.get("error"))
            if "hourly" in r.lower():
                print(f"      [hourly-limit] 等待 1200s 后重试（可断点续跑）")
                time.sleep(1200)
            elif "limit" in r.lower():
                print(f"      [throttle] {r[:70]} → 65s")
                time.sleep(65)
            else:
                print(f"      [throttle] {r[:70]} → 15s")
                time.sleep(15 * (a + 1))
            last = RuntimeError(r); continue
        return js
    raise last


def fetch_robust(vars_list, lat, lon, start, end):
    vars_ = list(vars_list)
    for _ in range(len(vars_) + 3):
        r = http_json({"latitude": lat, "longitude": lon, "start_date": start, "end_date": end,
                       "daily": ",".join(vars_), "timezone": TZ, "models": MODEL})
        d = r.get("daily") or {}
        # 检查是否有变量全空 → 剔除
        empty = [v for v in vars_ if v in d and all(x is None for x in d[v])]
        missing = [v for v in vars_ if v not in d]
        bad = empty + missing
        if bad:
            for v in bad:
                if v in vars_:
                    vars_.remove(v)
                    print(f"      [drop] {v}（ERA5 该变量为空/不可用）")
            continue
        return r, vars_
    return r, vars_


def build(js, city):
    d = js.get("daily") or {}
    if "time" not in d:
        return pd.DataFrame()
    df = pd.DataFrame({"date": d["time"]})
    for k, v in d.items():
        if k != "time":
            df[k] = v
    df.insert(0, "city", city)
    df["timezone"] = TZ
    df["weather_source"] = f"open-meteo-{MODEL}"
    df["data_type"] = "reanalysis"
    df["latitude"] = js.get("latitude")
    df["longitude"] = js.get("longitude")
    df["elevation"] = js.get("elevation")
    return df


def main():
    NAME2SLUG = {"沈阳": "shenyang", "铁岭": "tieling", "锦州": "jinzhou",
                 "丹东": "dandong", "大连": "dalian", "朝阳": "chaoyang"}
    cities = [c for c in csv.DictReader(CITY_META.open(encoding="utf-8")) if c["city"] in NAME2SLUG]
    end = (date.today() - timedelta(days=8)).isoformat()
    log = []
    for c in cities:
        city, lat, lon = c["city"], c["latitude"], c["longitude"]
        slug = NAME2SLUG[city]
        raw_dir = ROOT.parent / "data/raw" / "web_captures" / slug / "weather" / "era5" / "2010_2026"
        raw_dir.mkdir(parents=True, exist_ok=True)
        out_dir = ROOT / slug / "data"
        out_dir.mkdir(parents=True, exist_ok=True)
        for tag, vars_ in (("core", CORE), ("extra", EXTRA)):
            f = raw_dir / f"era5_{city}_{tag}_{START}_{end}.json"
            if f.exists():
                js = json.load(open(f, encoding="utf-8")); used = vars_
                print(f"[SKIP] {f.name}")
            else:
                js, used = fetch_robust(vars_, lat, lon, START, end)
                n0 = len((js.get("daily") or {}).get("time", []))
                if n0 == 0:
                    print(f"[FAIL] {city} {tag} 0 天，不落盘"); continue
                js.update({"_request": {"latitude": lat, "longitude": lon, "start_date": START,
                                        "end_date": end, "daily": used, "timezone": TZ, "models": MODEL},
                           "_retrieval_date": date.today().isoformat(), "_source": OM})
                f.write_text(json.dumps(js, ensure_ascii=False), encoding="utf-8")
                print(f"[OK] {city} {tag} {n0} 天, vars={len(used)}")
                time.sleep(12)
            df = build(js, city)
            if len(df):
                name = "weather_daily_era5.csv" if tag == "core" else "weather_extra_daily_era5.csv"
                df.to_csv(out_dir / name, index=False, encoding="utf-8-sig")
            log.append({"city": city, "tag": tag, "file": str(f.relative_to(ROOT)), "rows": len(df),
                        "model": MODEL, "start": START, "end": end, "vars": used})
    (ROOT / "reference" / "final_foundation" / "logs" / "weather_era5_log.json").write_text(
        json.dumps(log, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"\n[OK] ERA5 基准下载完成 {len(log)} 项")


if __name__ == "__main__":
    main()
