"""FDF-Task1：ERA5-Land 2010–2026 六城统一气候基准下载与构建。

关键原则（任务书 §7/§9/§10/§11）：
  - 显式 models=era5_land（禁止 best_match 自动切模型）
  - 坐标继承 data/raw/metadata/cities.csv（pfsc region），不重新选点
  - timezone=Asia/Shanghai（中国本地日）
  - Raw 全量落盘，含 request params / model / lat / lon / timezone
  - 旧天气保留（不删除），新序列单独命名 weather_daily_era5land

输出：
  city_data/<city>/workspace/data/raw/weather/era5_land/2010_2026/*.json
  city_data/<city>/workspace/data/interim/_final/weather_daily_era5land.csv
  city_data/<city>/workspace/data/interim/_final/weather_extra_daily_era5land.csv
"""
from __future__ import annotations

import csv
import json
import ssl
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import date, timedelta
from pathlib import Path

import pandas as pd

ROOT = next(p for p in Path(__file__).resolve().parents if (p / "AgriScope").is_dir() and (p / "data").is_dir()) / "data/raw/retained_source/city_data"           # city_data/
CITY_META = Path(next(p for p in Path(__file__).resolve().parents if (p / "AgriScope").is_dir() and (p / "data").is_dir())) / "data/raw/metadata/cities.csv"
OM = "https://archive-api.open-meteo.com/v1/archive"
MODEL = "era5_land"
TZ = "Asia/Shanghai"
START = "2010-01-01"

CTX = ssl.create_default_context(); CTX.check_hostname = False; CTX.verify_mode = ssl.CERT_NONE
UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")

CORE = ["temperature_2m_max", "temperature_2m_min", "temperature_2m_mean",
        "precipitation_sum", "relative_humidity_2m_mean", "wind_speed_10m_max",
        "shortwave_radiation_sum", "et0_fao_evapotranspiration"]
EXTRA = ["pressure_msl_mean", "surface_pressure_mean", "dew_point_2m_mean",
         "snowfall_sum", "snow_depth_mean", "cloud_cover_mean",
         "vapour_pressure_deficit_max", "wind_gusts_10m_max"]


def http_json(params: dict, retries: int = 6) -> dict:
    """用 curl 子进程请求；遇到限流(error/reason)自动长退避重试，绝不把错误响应当数据。"""
    import subprocess
    url = f"{OM}?{urllib.parse.urlencode(params)}"
    last = None
    for a in range(retries):
        p = subprocess.run(["curl", "-s", "--max-time", "180", url,
                            "-H", f"User-Agent: {UA}"], capture_output=True)
        out = p.stdout.decode("utf-8", "replace").strip()
        try:
            js = json.loads(out)
        except Exception as exc:
            last = exc; time.sleep(8 * (a + 1)); continue
        # Open-Meteo 限流/错误响应
        if isinstance(js, dict) and (js.get("error") or js.get("reason")):
            reason = str(js.get("reason") or js.get("error"))
            print(f"      [throttle] {reason[:80]} → 等待重试")
            time.sleep(65 if "limit" in reason.lower() else 15 * (a + 1))
            last = RuntimeError(reason)
            continue
        return js
    raise last


def fetch_robust(vars_list, lat, lon, start, end):
    """请求全部变量；若某变量不被 ERA5-Land 支持，剔除后重试。"""
    vars_ = list(vars_list)
    for _ in range(len(vars_) + 2):
        p = {"latitude": lat, "longitude": lon, "start_date": start, "end_date": end,
             "daily": ",".join(vars_), "timezone": TZ, "models": MODEL}
        r = http_json(p)
        if "__error__" in r:
            msg = json.dumps(r["__error__"], ensure_ascii=False)
            dropped = False
            for v in list(vars_):
                if v in msg:
                    vars_.remove(v); dropped = True
                    print(f"      [drop] {v}（ERA5-Land 不支持）")
            if not dropped:
                print(f"      [err] {msg[:200]}")
                return r, vars_
            continue
        return r, vars_
    return {"__error__": "exhausted"}, vars_


def build_frames(js: dict, city: str) -> pd.DataFrame:
    d = js.get("daily") or {}
    if "time" not in d:
        return pd.DataFrame()
    df = pd.DataFrame({"date": d["time"]})
    for k, v in d.items():
        if k == "time":
            continue
        df[k] = v
    df.insert(0, "city", city)
    df["timezone"] = TZ
    df["weather_source"] = f"open-meteo-{MODEL}"
    df["data_type"] = "reanalysis"
    df["latitude"] = js.get("latitude")
    df["longitude"] = js.get("longitude")
    df["elevation"] = js.get("elevation")
    return df


def main() -> None:
    NAME2SLUG = {"沈阳": "shenyang", "铁岭": "tieling", "锦州": "jinzhou",
                 "丹东": "dandong", "大连": "dalian", "朝阳": "chaoyang"}
    cities = list(csv.DictReader(CITY_META.open(encoding="utf-8")))
    cities = [c for c in cities if c["city"] in NAME2SLUG]
    # ERA5 archive 有发布延迟，回溯 8 天
    end = (date.today() - timedelta(days=8)).isoformat()
    log = []
    for c in cities:
        city, lat, lon = c["city"], c["latitude"], c["longitude"]
        slug = NAME2SLUG[city]
        raw_dir = ROOT.parent / "data/raw" / "web_captures" / slug / "weather" / "era5_land" / "2010_2026"
        raw_dir.mkdir(parents=True, exist_ok=True)
        out_dir = ROOT / slug / "data"
        out_dir.mkdir(parents=True, exist_ok=True)

        for tag, vars_ in (("daily_core", CORE), ("daily_extra", EXTRA)):
            f = raw_dir / f"era5land_{city}_{tag}_{START}_{end}.json"
            if f.exists():
                js = json.load(open(f, encoding="utf-8")); used = vars_
                print(f"[SKIP] {f.name}")
            else:
                js, used = fetch_robust(vars_, lat, lon, START, end)
                n = len((js.get("daily") or {}).get("time", []))
                if n == 0:
                    print(f"[FAIL] {city} {tag} 返回 0 天，不落盘")
                    continue
                meta = {"_request": {"latitude": lat, "longitude": lon, "start_date": START,
                                     "end_date": end, "daily": used, "timezone": TZ, "models": MODEL},
                        "_retrieval_date": date.today().isoformat(), "_source": OM}
                js.update(meta)
                f.write_text(json.dumps(js, ensure_ascii=False), encoding="utf-8")
                print(f"[OK] {city} {tag} {n} 天, vars={len(used)}")
                time.sleep(12)   # 规避 Open-Meteo 每分钟限流
            df = build_frames(js, city)
            if len(df):
                name = "weather_daily_era5land.csv" if tag == "daily_core" else "weather_extra_daily_era5land.csv"
                df.to_csv(out_dir / name, index=False, encoding="utf-8-sig")
            log.append({"city": city, "tag": tag, "file": str(f.relative_to(ROOT)), "rows": len(df),
                        "start": START, "end": end, "model": MODEL})
    (ROOT / "reference" / "final_foundation" / "logs" / "weather_download_log.json").write_text(
        json.dumps(log, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"\n[OK] 下载完成 {len(log)} 项 → 详见 city_data/reference/final_foundation/logs/weather_download_log.json")


if __name__ == "__main__":
    main()
