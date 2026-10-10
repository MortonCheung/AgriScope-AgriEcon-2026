"""气象日值采集：中国气象数据网（首选）→ Open-Meteo / NASA POWER（备用）。

重要合规说明（手册第 11 节）：
- 中国气象数据网 data.cma.cn 的数据下载需登录/实名认证，本项目**不绕过任何安全机制**，
  实测其数据接口无法匿名访问，故记为 blocked_by_auth，并切换到备用源。
- 备用源为 **再分析数据**（Open-Meteo = ERA5；NASA POWER = MERRA2），
  在 weather_source 字段中明确标注为 reanalysis，**绝不冒充为中国气象局观测站数据**。
- 站点坐标来自官方地区接口（pfsc region），非估计值。
"""
from __future__ import annotations

import csv
import json
import ssl
import urllib.parse
import urllib.request
from datetime import date
from pathlib import Path

ROOT = next(p for p in Path(__file__).resolve().parents if (p / "AgriScope").is_dir() and (p / "data").is_dir())
META = ROOT / "data/raw/metadata"
RAW = ROOT / "data/raw" / "weather_fallback"
RAW_CMA = ROOT / "data/raw" / "weather_cma"
for d in (RAW, RAW_CMA, META):
    d.mkdir(parents=True, exist_ok=True)

CTX = ssl.create_default_context()
CTX.check_hostname = False
CTX.verify_mode = ssl.CERT_NONE
UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")

DAILY_VARS = [
    "temperature_2m_max", "temperature_2m_min", "temperature_2m_mean",
    "precipitation_sum", "relative_humidity_2m_mean", "wind_speed_10m_max",
    "shortwave_radiation_sum", "et0_fao_evapotranspiration",
    "soil_moisture_0_to_10cm_mean",
]

OM_BASE = "https://archive-api.open-meteo.com/v1/archive"
NASA_BASE = "https://power.larc.nasa.gov/api/temporal/daily/point"


def http_json(url: str, timeout: int = 120, retries: int = 4) -> dict:
    """带 429/5xx 退避的请求。再分析源对请求频率敏感，失败必须退避重试而不是放弃。"""
    import time
    import urllib.error
    last = None
    for attempt in range(retries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": UA})
            with urllib.request.urlopen(req, timeout=timeout, context=CTX) as r:
                return json.loads(r.read().decode("utf-8", "replace"))
        except urllib.error.HTTPError as exc:
            last = exc
            if exc.code in (429, 500, 502, 503, 504):
                wait = 5 * (attempt + 1)
                print(f"      [RETRY] HTTP {exc.code}，退避 {wait}s")
                time.sleep(wait)
                continue
            raise
        except Exception as exc:
            last = exc
            time.sleep(3)
    raise last


def load_cities() -> list[dict]:
    with (META / "cities.csv").open(encoding="utf-8") as fh:
        return list(csv.DictReader(fh))


def fetch_openmeteo(lat: float, lon: float, start: str, end: str) -> dict:
    params = {
        "latitude": lat, "longitude": lon,
        "start_date": start, "end_date": end,
        "daily": ",".join(DAILY_VARS),
        "timezone": "Asia/Shanghai",
    }
    return http_json(f"{OM_BASE}?{urllib.parse.urlencode(params)}")


def fetch_nasa(lat: float, lon: float, start: str, end: str) -> dict:
    params = {
        "parameters": "T2M,T2M_MAX,T2M_MIN,PRECTOTCORR,RH2M,WS2M",
        "community": "AG",
        "longitude": lon, "latitude": lat,
        "start": start.replace("-", ""), "end": end.replace("-", ""),
        "format": "JSON",
    }
    return http_json(f"{NASA_BASE}?{urllib.parse.urlencode(params)}", timeout=180)


def main() -> None:
    cities = load_cities()
    # 再分析数据有发布延迟（实测 end_date 取当天会返回 400），统一回退 7 天。
    today = (date.today() - __import__("datetime").timedelta(days=7)).isoformat()
    periods = [
        ("current", "2021-01-01", today),
        ("baseline", "1991-01-01", "2020-12-31"),   # 1991—2020 长期气候基线
    ]
    manifest = []

    for c in cities:
        city = c["city"]
        lat, lon = float(c["latitude"]), float(c["longitude"])
        for tag, start, end in periods:
            out = RAW / f"openmeteo_{city}_{tag}_{start}_{end}.json"
            if out.exists():
                print(f"[SKIP] 已存在 {out.name}")
            else:
                try:
                    data = fetch_openmeteo(lat, lon, start, end)
                    out.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
                    n = len(data.get("daily", {}).get("time", []))
                    print(f"[OK] {city} {tag} {start}~{end} -> {n} 天")
                except Exception as exc:
                    print(f"[FAIL] {city} {tag}: {exc}")
                    continue
            manifest.append({"city": city, "period": tag, "start": start, "end": end,
                             "source": "open-meteo-era5", "file": str(out.relative_to(ROOT))})

    # NASA POWER 交叉验证（仅当前时段，增强项，失败不阻塞）
    for c in cities:
        city = c["city"]
        out = RAW / f"nasapower_{city}_current.json"
        if out.exists():
            continue
        try:
            data = fetch_nasa(float(c["latitude"]), float(c["longitude"]), "2021-01-01", today)
            out.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
            print(f"[OK] NASA POWER {city} 交叉验证数据")
        except Exception as exc:
            print(f"[WARN] NASA POWER {city} 失败（不影响主流程）：{exc}")

    (RAW / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"[OK] manifest {len(manifest)} 条")

    # 记录 CMA 状态
    (RAW_CMA / "STATUS.md").write_text(
        "# 中国气象数据网（data.cma.cn）采集状态\n\n"
        "状态：**blocked_by_auth**\n\n"
        "实测：首页返回 SPA 壳（534 字节），数据接口 `/api/weather`、`/site/login` 均 404，"
        "数据下载需登录与实名认证。按施工手册第 11 节规定，不绕过任何登录/验证码机制，"
        "故切换备用再分析源（Open-Meteo / ERA5，NASA POWER / MERRA2）。\n\n"
        "所有天气数据的 weather_source 字段均标注为 `open-meteo-era5` 或 `nasapower-merra2`，"
        "**不得标注为中国气象局观测站数据**。\n", encoding="utf-8")
    print("[OK] CMA 状态记录")


if __name__ == "__main__":
    main()
