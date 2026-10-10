"""生成地理主数据 cities.csv 与 markets.csv。

坐标来源：农业农村部全国农产品批发市场价格信息系统公开接口
    POST /price_portal/region/selectList        → 省/市/区 名称与经纬度
    POST /api/priceQuotationController/getMarketByProvinceCode → 市场元数据（含经纬度）
不使用任何估计坐标。
"""
from __future__ import annotations

import csv
import json
import ssl
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = next(p for p in Path(__file__).resolve().parents if (p / "AgriScope").is_dir() and (p / "data").is_dir())
META = ROOT / "data/raw/metadata"
RAW_MOA = ROOT / "data/raw" / "moa_market_prices"
META.mkdir(parents=True, exist_ok=True)
RAW_MOA.mkdir(parents=True, exist_ok=True)

UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")
BASE = "https://pfsc.agri.cn"
CTX = ssl.create_default_context()
CTX.check_hostname = False
CTX.verify_mode = ssl.CERT_NONE

TARGET_CITIES = ["沈阳", "铁岭", "朝阳", "锦州", "丹东", "大连"]
FOCUS_DISTRICT = "沈北新区"


def post(path: str, payload=None, params=None) -> dict:
    url = BASE + path + (("?" + urllib.parse.urlencode(params)) if params else "")
    data = json.dumps(payload or {}).encode()
    req = urllib.request.Request(url, data=data,
                                 headers={"User-Agent": UA, "Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=60, context=CTX) as r:
        return json.loads(r.read().decode("utf-8", "replace"))


def main() -> None:
    # ---------- 1. 地区树 ----------
    reg = post("/price_portal/region/selectList")
    (RAW_MOA / "region_selectList.json").write_text(
        json.dumps(reg, ensure_ascii=False, indent=1), encoding="utf-8")
    rows = reg.get("data", [])
    prov = next(r for r in rows if r["name"] == "辽宁省")
    city_rows = [r for r in rows if r.get("pid") == prov["id"]]
    city_by_name = {r["name"]: r for r in city_rows}

    cities = []
    for name in TARGET_CITIES:
        key = name + "市"
        r = city_by_name.get(key)
        if not r:
            print(f"[WARN] 未找到 {key}")
            continue
        cities.append({
            "city": name,
            "province": "辽宁省",
            "admin_code": r["id"],
            "latitude": r.get("lat"),
            "longitude": r.get("lng"),
            "focus_district": FOCUS_DISTRICT if name == "沈阳" else "",
            "source": "pfsc.agri.cn /price_portal/region/selectList",
        })

    # 沈北新区（沈阳市下辖区）作为重点案例单独登记
    shenyang_id = city_by_name["沈阳市"]["id"]
    districts = [r for r in rows if r.get("pid") == shenyang_id]
    sb = next((d for d in districts if FOCUS_DISTRICT in d["name"]), None)
    if sb:
        cities.append({
            "city": "沈北新区",
            "province": "辽宁省",
            "admin_code": sb["id"],
            "latitude": sb.get("lat"),
            "longitude": sb.get("lng"),
            "focus_district": FOCUS_DISTRICT,
            "source": "pfsc.agri.cn /price_portal/region/selectList",
        })
        print(f"[OK] 沈北新区坐标 {sb.get('lat')},{sb.get('lng')}")

    with (META / "cities.csv").open("w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(cities[0].keys()))
        w.writeheader()
        w.writerows(cities)
    print(f"[OK] cities.csv 写入 {len(cities)} 行")

    # ---------- 2. 市场 ----------
    mk = post("/api/priceQuotationController/getMarketByProvinceCode",
              {"provinceCode": prov["id"]})
    (RAW_MOA / "markets_all.json").write_text(
        json.dumps(mk, ensure_ascii=False, indent=1), encoding="utf-8")
    content = mk.get("content", [])
    # marketCode 前两位即省份行政区划码前缀，辽宁为 21
    ln = [m for m in content if str(m.get("marketCode", "")).startswith("21")]
    print(f"[OK] 全国市场 {len(content)}，辽宁市场 {len(ln)}")

    markets = []
    for m in ln:
        markets.append({
            "market_id": m.get("marketCode"),
            "market_name": m.get("marketName"),
            "province": m.get("province") or "辽宁省",
            "city": m.get("area") or "",
            "district": m.get("county") or "",
            "market_type": m.get("marketType") or "",
            "market_category": m.get("marketCategory") or "",
            "enterprise_name": m.get("enterpriseName") or "",
            "address": m.get("address") or "",
            "latitude": m.get("latitude"),
            "longitude": m.get("longitude"),
            "source": "pfsc.agri.cn /api/priceQuotationController/getMarketByProvinceCode",
        })
    with (META / "markets.csv").open("w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(markets[0].keys()))
        w.writeheader()
        w.writerows(markets)
    print(f"[OK] markets.csv 写入 {len(markets)} 行")

    # 目标城市市场统计
    from collections import Counter
    cnt = Counter(m["city"] for m in markets)
    print("各城市市场数:", dict(cnt))


if __name__ == "__main__":
    main()
