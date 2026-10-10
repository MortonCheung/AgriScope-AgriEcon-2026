"""惠农网（cnhnb.com）辽宁五城及县域「产地行情」大规模采集。

数据来源：m.cnhnb.com 触屏站公开 SSR 页 window.__NUXT__ 负载（HTML 原样落盘）。
  - 区域页：/hangqing/q-0-0-0-{areaId}/                     （最新有数据日）
  - 日采样：/hangqing/q-0-0-0-{areaId}-{yyyymmdd}/          （指定日）
  - 分页：  /hangqing/q-0-0-0-{areaId}-{yyyymmdd}-{page}/

areaId 一律**反查**自公开行情页，不推测：
  1) 城市页 /q-0-0-0-{cityId}-{date}/ 的 marketList 行内 `addressDetail` + `areaId`
     给出「区县名 ↔ areaId」对应；
  2) 再抓 /q-0-0-0-{areaId}/ 的 selected.area 取权威 areaName / areaNo 复核。
  城市 areaId 由城市页 selected.area.city.cityId 与 title 复核。

禁止编造：输出字段全部来自原始页面；抓不到记 status，不补造。
禁止绕过 pcapi.cnhnb.com 签名接口（未使用，记 ACCESS_RESTRICTED）。
断点续跑：已落盘且非空的 HTML 直接复用，不重复联网。

用法：
    python3 collectors/hnwb_hangqing_collect.py --discover        # 只反查 areaId
    python3 collectors/hnwb_hangqing_collect.py --collect --freq month
    python3 collectors/hnwb_hangqing_collect.py --rebuild         # 只从落盘 HTML 出 CSV
"""

from __future__ import annotations

import argparse
import csv
import json
import re
import sys
import time
from datetime import date, datetime, timedelta
from pathlib import Path

ROOT = next(p for p in Path(__file__).resolve().parents if (p / "AgriScope").is_dir() and (p / "data").is_dir())
RAW = ROOT / "data/raw" / "prices" / "hnwb"
STAGING = ROOT / "city_data/reference/staging"
REGISTRY = RAW / "area_registry.json"

sys.path.insert(0, str(Path(__file__).resolve().parent))
from b2b_hangqing_probe import (  # noqa: E402
    UA_MOBILE, _curl_get, classify, parse_hangqing,
)

HOST = "https://m.cnhnb.com"
REFERER = "https://m.cnhnb.com/hangqing/"
SOURCE_ID = "SRC-CNHNB-HANGQING"

# 五城市级 areaId（复核见 area_registry.json；来自城市页 selected.area.city.cityId）
CITY_AREA = {108: "大连", 112: "丹东", 118: "铁岭", 113: "锦州", 119: "朝阳"}

# 目标县域：城市 -> [(匹配关键词, 展示名)]，关键词用于在 addressDetail/areaName 中定位。
TARGET_COUNTIES = {
    "大连": [("瓦房店", "瓦房店市"), ("庄河", "庄河市"), ("普兰店", "普兰店区")],
    "丹东": [("东港", "东港市"), ("凤城", "凤城市"), ("宽甸", "宽甸满族自治县")],
    "铁岭": [("开原", "开原市"), ("西丰", "西丰县"), ("铁岭县", "铁岭县"), ("昌图", "昌图县")],
    "锦州": [("黑山", "黑山县"), ("凌海", "凌海市"), ("义县", "义县"), ("北镇", "北镇市")],
    "朝阳": [("北票", "北票市"), ("建平", "建平县"), ("喀喇沁", "喀喇沁左翼蒙古族自治县"),
             ("凌源", "凌源市")],
}

PROBE_DATES = ["20260920", "20250618", "20240615", "20230118"]
THROTTLE = 1.2


# ------------------------------------------------------------------ 抓取

def fetch(path: str, throttle: float = THROTTLE) -> tuple[int, bytes, str]:
    status, body, final = _curl_get(HOST + path, UA_MOBILE, referer=REFERER)
    time.sleep(throttle)
    return status, body, final


def cache_get(path: str, filename: str, throttle: float = THROTTLE) -> tuple[int, bytes, str, bool]:
    RAW.mkdir(parents=True, exist_ok=True)
    target = RAW / filename
    if target.exists() and target.stat().st_size > 0:
        return 200, target.read_bytes(), HOST + path, True
    status, body, final = fetch(path, throttle)
    if status == 200 and b"<html" in body.lower():
        target.write_bytes(body)
    return status, body, final, False


def _area_selected(html: str) -> dict:
    import b2b_hangqing_probe as bp
    i = html.find("selected:{")
    if i < 0:
        return {}
    try:
        sel = bp._literal_to_json(bp._balanced(html, html.find("{", i), "{", "}"), bp.nuxt_varmap(html))
    except Exception:  # noqa: BLE001
        return {}
    return (sel or {}).get("area") or {}


# ------------------------------------------------------------------ areaId 反查

def discover(verbose: bool = True) -> dict:
    """从公开城市页 + 县域页反查 areaId，落盘 area_registry.json。"""
    found: dict[int, dict] = {}
    for cid, cname in CITY_AREA.items():
        for d in PROBE_DATES:
            for page in range(1, 9):
                suffix = "" if page == 1 else f"-{page}"
                path = f"/hangqing/q-0-0-0-{cid}-{d}{suffix}/"
                fname = f"_discover_{cid}_{d}_p{page}.html"
                status, body, final, cached = cache_get(path, fname)
                if status != 200:
                    break
                parsed = parse_hangqing(body.decode("utf-8", "ignore"))
                if not parsed["rows"]:
                    break
                for r in parsed["rows"]:
                    aid, det = r.get("areaId"), r.get("addressDetail")
                    if aid and isinstance(det, str) and det not in found:
                        found[aid] = {"city": cname, "cityId": cid,
                                      "addressDetail": det, "seenAt": path}
            if verbose:
                print(f"  [discover] {cname} {d} 累计 areaId={len(found)}")

    registry = {"generated_at": datetime.now().isoformat(timespec="seconds"),
                "method": "城市页 addressDetail+areaId 反查，再抓县域页 selected.area 复核",
                "cities": [], "counties": []}

    for cid, cname in CITY_AREA.items():
        html = cache_get(f"/hangqing/q-0-0-0-{cid}/", f"_discover_city_{cid}.html")[1]
        sel = _area_selected(html.decode("utf-8", "ignore"))
        registry["cities"].append({
            "city": cname, "areaId": cid,
            "areaName": (sel.get("city") or {}).get("cityName") or cname,
            "areaNo": (sel.get("city") or {}).get("areaNo"),
            "url": f"{HOST}/hangqing/q-0-0-0-{cid}/"})

    for aid, meta in sorted(found.items()):
        html = cache_get(f"/hangqing/q-0-0-0-{aid}/", f"_discover_area_{aid}.html")[1]
        sel = _area_selected(html.decode("utf-8", "ignore"))
        aa = sel.get("area") or {}
        name = aa.get("areaName")
        ano = aa.get("areaNo")
        if not name:
            continue
        det = meta["addressDetail"]
        city = next((c for c in CITY_AREA.values() if c + "市" in det), None)
        entry = {"city": city, "areaId": aid, "areaName": name, "areaNo": ano,
                 "addressDetail": det, "parentCityId": meta["cityId"],
                 "url": f"{HOST}/hangqing/q-0-0-0-{aid}/"}
        registry["counties"].append(entry)
        if verbose:
            print(f"  [area] {name:12s} areaId={aid} areaNo={ano} <- {det}")

    REGISTRY.parent.mkdir(parents=True, exist_ok=True)
    REGISTRY.write_text(json.dumps(registry, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"[discover] cities={len(registry['cities'])} counties={len(registry['counties'])} -> {REGISTRY}")
    return registry


def load_registry() -> dict:
    if REGISTRY.exists():
        return json.loads(REGISTRY.read_text(encoding="utf-8"))
    return discover(verbose=False)


def target_areas(registry: dict | None = None) -> list[dict]:
    """产出待采集区域清单：5 城市 + 目标县域（已复核 areaId）。"""
    reg = registry or load_registry()
    areas: list[dict] = []
    for c in reg["cities"]:
        areas.append({"kind": "city", "city": c["city"], "county": "", "areaId": c["areaId"],
                      "areaName": c["areaName"], "areaNo": c.get("areaNo")})
    by_city = {}
    for e in reg["counties"]:
        by_city.setdefault(e["city"], []).append(e)
    for city, targets in TARGET_COUNTIES.items():
        pool = by_city.get(city, [])
        for kw, disp in targets:
            hit = next((e for e in pool if kw in (e.get("areaName") or "")
                        or kw in (e.get("addressDetail") or "")), None)
            if hit:
                areas.append({"kind": "county", "city": city, "county": hit["areaName"],
                              "areaId": hit["areaId"], "areaName": hit["areaName"],
                              "areaNo": hit.get("areaNo")})
            else:
                print(f"[warn] 未反查到目标县域：{city} {disp}")
    return areas


# ------------------------------------------------------------------ 采样日

def sample_dates(freq: str, start: date, end: date) -> list[date]:
    out: list[date] = []
    if freq == "week":
        d = start + timedelta(days=(0 - start.weekday()) % 7)
        while d <= end:
            out.append(d)
            d += timedelta(days=7)
    else:  # month：每月 15 日，遇周末顺延至周一
        y, m = start.year, start.month
        while date(y, m, 1) <= end:
            d = date(y, m, 15)
            while d.weekday() >= 5:
                d += timedelta(days=1)
            if start <= d <= end:
                out.append(d)
            m += 1
            if m > 12:
                y, m = y + 1, 1
    return out


# ------------------------------------------------------------------ 采集

def collect(areas: list[dict], freq: str, start: date, end: date, retry: int = 2) -> dict:
    dates = sample_dates(freq, start, end)
    manifest, total_rows = [], 0
    for area in areas:
        aid = area["areaId"]
        for d in dates:
            got = 0
            used = None
            for k in range(retry + 1):
                dd = d + timedelta(days=k)
                if dd > end:
                    break
                ymd = dd.strftime("%Y%m%d")
                path = f"/hangqing/q-0-0-0-{aid}-{ymd}/"
                fname = f"{area['city']}_{area.get('county') or area['city']}_{aid}_{ymd}.html"
                status, body, final, cached = cache_get(path, fname)
                state = classify(status, body)
                parsed = parse_hangqing(body.decode("utf-8", "ignore")) if state == "ok" else {"rows": [], "total": None}
                n = len(parsed["rows"])
                manifest.append({"areaId": aid, "city": area["city"], "county": area["county"],
                                 "planned_date": d.strftime("%Y-%m-%d"), "sample_date": dd.strftime("%Y-%m-%d"),
                                 "status": state, "http": status, "file": fname,
                                 "cached": cached, "declared_total": parsed.get("total"),
                                 "parsed_rows": n, "source_url": final})
                if n > 0:
                    got, used = n, fname
                    break
                if state != "ok":
                    break
            total_rows += got
            print(f"[collect] {area['city']}{('-' + area['county']) if area['county'] else ''} "
                  f"{d} -> {got} 行 {('(' + used + ')') if used else ''}")
    mpath = RAW / "collect_manifest.json"
    mpath.write_text(json.dumps({"generated_at": datetime.now().isoformat(timespec="seconds"),
                                 "freq": freq, "start": start.isoformat(), "end": end.isoformat(),
                                 "samples_per_area": len(dates), "areas": len(areas),
                                 "indexed_rows": total_rows, "manifest": manifest},
                                ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"[collect] 采样日 {len(dates)} × 区域 {len(areas)} -> {total_rows} 行 -> {mpath.name}")
    return {"dates": dates, "manifest": manifest}


# ------------------------------------------------------------------ 解析落盘

WEIGHT_KG = {"斤": 0.5, "公斤": 1.0, "千克": 1.0, "kg": 1.0, "KG": 1.0, "吨": 1000.0}


def split_addr(detail: str) -> tuple[str, str]:
    if not detail:
        return "", ""
    s = detail
    for pre in ("辽宁省", "辽宁"):
        if s.startswith(pre):
            s = s[len(pre):]
            break
    for city in CITY_AREA.values():
        if s.startswith(city + "市"):
            return city, s[len(city) + 1:]
    return s[:3], s


def price_per_kg(avg, unit):
    try:
        if unit in WEIGHT_KG and avg is not None:
            return round(float(avg) * (1.0 / WEIGHT_KG[unit]), 4)
    except (TypeError, ValueError):
        pass
    return ""


def level_of(sourse_type: str) -> str:
    return {"supply": "farm_gate", "market": "wholesale"}.get(sourse_type, "farm_gate")


def rebuild() -> dict:
    """只读 data/raw/prices/hnwb/*.html，重建 city_data/reference/staging/hnwb_prices.csv。"""
    files = sorted(p for p in RAW.glob("*.html") if not p.name.startswith("_discover"))
    fields = ["date", "city", "county", "product", "breed", "price_min", "price_max",
              "price_avg", "unit", "price_per_kg", "price_level", "sample_num",
              "source_id", "source_url", "raw_file", "quality_grade", "retrieval_time"]
    seen, rows, pages_ok, pages_bad = set(), [], 0, 0
    for path in files:
        m = re.match(r"(.+?)_(\d{4,6})_(\d{8})(?:-p\d+)?$", path.stem)
        if not m:
            continue
        area_id, ymd = int(m.group(2)), m.group(3)
        html = path.read_text(encoding="utf-8", errors="ignore")
        parsed = parse_hangqing(html)
        if not parsed["rows"]:
            pages_bad += 1
            continue
        pages_ok += 1
        mtime = datetime.fromtimestamp(path.stat().st_mtime).isoformat(timespec="seconds")
        for r in parsed["rows"]:
            city, county = split_addr(r.get("addressDetail") or "")
            if not city:
                city = r.get("query_city") or ""
            avg, unit = r.get("avgPrice"), r.get("unit")
            row = {
                "date": f"{ymd[:4]}-{ymd[4:6]}-{ymd[6:]}",
                "city": city, "county": county,
                "product": r.get("cateName") or "", "breed": r.get("breedName") or "",
                "price_min": r.get("minPrice"), "price_max": r.get("maxPrice"),
                "price_avg": avg, "unit": unit, "price_per_kg": price_per_kg(avg, unit),
                "price_level": level_of(r.get("sourse_type") or ""),
                "sample_num": r.get("statisNum"), "source_id": SOURCE_ID,
                "source_url": f"{HOST}/hangqing/q-0-0-0-{area_id}-{ymd}/",
                "raw_file": f"data/raw/prices/hnwb/{path.name}",
                "quality_grade": "C", "retrieval_time": mtime,
            }
            key = (row["date"], city, county, row["product"], row["breed"],
                   row["price_min"], row["price_max"], avg, unit, row["sample_num"], row["price_level"])
            if key in seen:
                continue
            seen.add(key)
            rows.append(row)
    rows.sort(key=lambda x: (x["date"], x["city"], x["county"], x["product"], x["breed"]))
    STAGING.mkdir(parents=True, exist_ok=True)
    with (STAGING / "hnwb_prices.csv").open("w", newline="", encoding="utf-8-sig") as fh:
        w = csv.DictWriter(fh, fieldnames=fields)
        w.writeheader()
        w.writerows(rows)
    out = {"pages_ok": pages_ok, "pages_empty": pages_bad, "rows": len(rows),
           "dates": sorted({r["date"] for r in rows}),
           "counties": sorted({r["county"] for r in rows if r["county"]}),
           "products": sorted({r["product"] for r in rows if r["product"]})}
    (RAW / "rebuild_summary.json").write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"[rebuild] 页面 ok={pages_ok} empty={pages_bad} -> 去重后 {len(rows)} 行 -> city_data/reference/staging/hnwb_prices.csv")
    return out


# ------------------------------------------------------------------ CLI

def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--discover", action="store_true", help="只反查 areaId")
    ap.add_argument("--collect", action="store_true", help="执行采集")
    ap.add_argument("--rebuild", action="store_true", help="只从落盘 HTML 重建 CSV")
    ap.add_argument("--freq", choices=["week", "month"], default="month")
    ap.add_argument("--start", default="2020-01-01")
    ap.add_argument("--end", default=date.today().isoformat())
    ap.add_argument("--max-areas", type=int, default=0)
    args = ap.parse_args()

    if args.discover:
        discover()
        return
    if args.rebuild:
        rebuild()
        return
    if args.collect:
        areas = target_areas()
        if args.max_areas:
            areas = areas[:args.max_areas]
        print(f"[collect] 目标区域 {len(areas)} 个，采样频率 {args.freq}，"
              f"{args.start}~{args.end}")
        for a in areas:
            print("   -", a["city"], a["county"], a["areaId"], a["areaNo"])
        collect(areas, args.freq, date.fromisoformat(args.start), date.fromisoformat(args.end))
        rebuild()
        return
    ap.print_help()


if __name__ == "__main__":
    main()
