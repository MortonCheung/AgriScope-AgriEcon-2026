"""气象扩展变量采集（手册第 8、9 节）。

在已有核心变量（温度/降水/湿度/风速/辐射/ET0）基础上，补充：
  气压（海平面 + 地面）、露点、降雪、雪深、云量、饱和水汽压差 VPD、阵风

土壤分层（手册第 9.2 节）：ERA5-Land 的 0-7cm / 7-28cm / 28-100cm 土壤含水量，
以 hourly 取日聚合，单独请求以控制单次响应体积。

data_type 一律标记为 reanalysis，绝不冒充气象站观测数据。
"""
from __future__ import annotations

import csv
import json
import ssl
import time
import urllib.parse
import urllib.request
from datetime import date, timedelta
from pathlib import Path

ROOT = next(p for p in Path(__file__).resolve().parents if (p / "AgriScope").is_dir() and (p / "data").is_dir())
META = ROOT / "data/raw/metadata"
RAW = ROOT / "data/raw" / "weather"
SOIL_RAW = ROOT / "data/raw" / "soil"
for d in (RAW, SOIL_RAW):
    d.mkdir(parents=True, exist_ok=True)

CTX = ssl.create_default_context(); CTX.check_hostname = False; CTX.verify_mode = ssl.CERT_NONE
UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")
OM = "https://archive-api.open-meteo.com/v1/archive"

EXTRA_DAILY = ["pressure_msl_mean", "surface_pressure_mean", "dew_point_2m_mean",
               "snowfall_sum", "snow_depth_mean", "cloud_cover_mean",
               "vapour_pressure_deficit_max", "wind_gusts_10m_max"]

SOIL_HOURLY = ["soil_moisture_0_to_7cm", "soil_moisture_7_to_28cm",
               "soil_moisture_28_to_100cm", "soil_temperature_0_to_7cm"]


def http_json(url: str, timeout: int = 180, retries: int = 5) -> dict:
    import urllib.error
    last = None
    for a in range(retries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": UA})
            with urllib.request.urlopen(req, timeout=timeout, context=CTX) as r:
                return json.loads(r.read().decode("utf-8", "replace"))
        except urllib.error.HTTPError as exc:
            last = exc
            if exc.code in (429, 500, 502, 503, 504):
                w = 6 * (a + 1)
                print(f"      [RETRY] HTTP {exc.code} 退避 {w}s")
                time.sleep(w)
                continue
            raise
        except Exception as exc:
            last = exc
            time.sleep(4)
    raise last


def main() -> None:
    cities = list(csv.DictReader((META / "cities.csv").open(encoding="utf-8")))
    end = (date.today() - timedelta(days=7)).isoformat()

    # ---------- 1. 扩展日变量 ----------
    for c in cities:
        out = RAW / f"openmeteo_extra_{c['city']}_2021-01-01_{end}.json"
        if out.exists():
            print(f"[SKIP] {out.name}")
            continue
        params = {"latitude": c["latitude"], "longitude": c["longitude"],
                  "start_date": "2021-01-01", "end_date": end,
                  "daily": ",".join(EXTRA_DAILY), "timezone": "Asia/Shanghai"}
        try:
            d = http_json(f"{OM}?{urllib.parse.urlencode(params)}")
            out.write_text(json.dumps(d, ensure_ascii=False), encoding="utf-8")
            print(f"[OK] extra {c['city']} {len(d.get('daily',{}).get('time',[]))} 天")
        except Exception as exc:
            print(f"[FAIL] extra {c['city']}: {exc}")
        time.sleep(2)

    # ---------- 2. 土壤分层（ERA5-Land，逐年请求以控制体积）----------
    for c in cities:
        for year in range(2021, int(end[:4]) + 1):
            s = f"{year}-01-01"
            e = f"{year}-12-31" if year < int(end[:4]) else end
            out = SOIL_RAW / f"openmeteo_soil_{c['city']}_{year}.json"
            if out.exists():
                print(f"[SKIP] {out.name}")
                continue
            params = {"latitude": c["latitude"], "longitude": c["longitude"],
                      "start_date": s, "end_date": e,
                      "hourly": ",".join(SOIL_HOURLY),
                      "models": "era5_land", "timezone": "Asia/Shanghai"}
            try:
                d = http_json(f"{OM}?{urllib.parse.urlencode(params)}")
                out.write_text(json.dumps(d, ensure_ascii=False), encoding="utf-8")
                n = len(d.get("hourly", {}).get("time", []))
                print(f"[OK] soil {c['city']} {year} {n} 小时")
            except Exception as exc:
                print(f"[FAIL] soil {c['city']} {year}: {exc}")
            time.sleep(2)

    (RAW / "EXTEND_STATUS.md").write_text(
        "# 气象扩展采集\n\n"
        f"- 扩展日变量：{', '.join(EXTRA_DAILY)}\n"
        f"- 土壤分层（ERA5-Land hourly，聚合为日）：{', '.join(SOIL_HOURLY)}\n"
        "- data_type = reanalysis（**非气象站观测**）\n"
        "- 源：Open-Meteo Archive API（ERA5 / ERA5-Land）\n", encoding="utf-8")
    print("[OK] EXTEND_STATUS.md")


if __name__ == "__main__":
    main()
