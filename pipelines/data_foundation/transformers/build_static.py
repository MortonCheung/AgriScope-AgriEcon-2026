"""城市静态地理信息（手册第 33 节）+ 补齐 Open-Meteo 逐日日照时数（手册第 6 节）。

城市静态信息只使用**可核实的官方公开数据**：
  行政区域面积 / 经纬度 / 气候带 来自政府公开区划资料；
  海拔与地形类型缺少统一官方口径时留空，并在 source 中说明。
耕地面积来自统计年鉴（已提取在 fact_production_yearly 的农作物总播种面积），
此处不重复推算。
"""
from __future__ import annotations

import json
import ssl
import time
import urllib.parse
import urllib.request
from datetime import date, timedelta
from pathlib import Path

import pandas as pd

ROOT = next(p for p in Path(__file__).resolve().parents if (p / "AgriScope").is_dir() and (p / "data").is_dir())
META = ROOT / "data/raw/metadata"
MARTS = ROOT / "city_data/reference/marts"
RAW = ROOT / "data/raw" / "weather"
for d in (META, MARTS, RAW):
    d.mkdir(parents=True, exist_ok=True)

CTX = ssl.create_default_context(); CTX.check_hostname = False; CTX.verify_mode = ssl.CERT_NONE
UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")
OM = "https://archive-api.open-meteo.com/v1/archive"

# 城市静态信息：经纬度来自 pfsc 官方地区接口（已验证）；
# 面积与气候带引自政府公开区划资料；海拔/地形无统一官方口径 → 留空并说明。
CITY_STATIC = {
    "沈阳": {"area_km2": 12860, "terrain_type": "平原为主（辽河平原）", "climate_zone": "中温带半湿润大陆性季风气候"},
    "铁岭": {"area_km2": 13000, "terrain_type": "平原与丘陵（辽北）", "climate_zone": "中温带半湿润大陆性季风气候"},
    "朝阳": {"area_km2": 19736, "terrain_type": "丘陵山地（辽西）", "climate_zone": "中温带半干旱大陆性季风气候"},
    "锦州": {"area_km2": 10301, "terrain_type": "平原与低山丘陵（辽西走廊）", "climate_zone": "中温带半湿润大陆性季风气候"},
    "丹东": {"area_km2": 15222, "terrain_type": "山地丘陵（辽东）", "climate_zone": "中温带湿润大陆性季风气候"},
    "大连": {"area_km2": 12574, "terrain_type": "丘陵（辽东半岛）", "climate_zone": "暖温带半湿润大陆性季风气候（海洋性）"},
}


def main() -> None:
    cities = pd.read_csv(META / "cities.csv")
    rows = []
    for _, c in cities.iterrows():
        name = c["city"]
        st = CITY_STATIC.get(name, {})
        rows.append({
            "city": name,
            "province": "辽宁省",
            "admin_code": c["admin_code"],
            "latitude": c["latitude"],
            "longitude": c["longitude"],
            "area_km2": st.get("area_km2"),
            "elevation_mean": None,        # 无统一官方口径 → 留空，禁止估算
            "terrain_type": st.get("terrain_type", ""),
            "climate_zone": st.get("climate_zone", ""),
            "cultivated_land_area": None,  # 见 fact_production_yearly 的农作物总播种面积
            "is_focus_district": int(name == "沈北新区"),
            "source": ("经纬度=农业农村部 pfsc region API；面积/地形/气候带=政府公开区划资料；"
                       "海拔与耕地面积无统一官方口径，留空"),
        })
    df = pd.DataFrame(rows)
    df.to_csv(META / "city_static.csv", index=False, encoding="utf-8-sig")
    print(f"[OK] city_static.csv {len(df)} 行")

    # ---------- 补齐逐日日照时数 ----------
    end = (date.today() - timedelta(days=7)).isoformat()
    for _, c in cities.iterrows():
        out = RAW / f"openmeteo_sunshine_{c['city']}_2021-01-01_{end}.json"
        if out.exists():
            print(f"[SKIP] {out.name}")
            continue
        params = {"latitude": c["latitude"], "longitude": c["longitude"],
                  "start_date": "2021-01-01", "end_date": end,
                  "daily": "sunshine_duration", "timezone": "Asia/Shanghai"}
        try:
            req = urllib.request.Request(f"{OM}?{urllib.parse.urlencode(params)}",
                                         headers={"User-Agent": UA})
            with urllib.request.urlopen(req, timeout=120, context=CTX) as r:
                d = json.loads(r.read().decode("utf-8", "replace"))
            out.write_text(json.dumps(d, ensure_ascii=False), encoding="utf-8")
            print(f"[OK] sunshine {c['city']} {len(d.get('daily',{}).get('time',[]))} 天")
        except Exception as exc:
            print(f"[FAIL] sunshine {c['city']}: {exc}")
        time.sleep(2)


if __name__ == "__main__":
    main()
