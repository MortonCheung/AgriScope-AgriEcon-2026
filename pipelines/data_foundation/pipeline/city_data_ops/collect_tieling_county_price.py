"""铁岭县域价格补采：惠农网（cnhnb.com）「产地行情」逐区县采集 + 解析。

目的：为铁岭补齐县域连续价格（铁岭县/昌图县/开原市/西丰县/调兵山市/清河区）。

数据来源：公开触屏站 / PC 站 SSR 页（window.__NUXT__ 负载），HTML 原样落盘。
  - 区域页：/hangqing/q-0-0-0-{areaId}/                 （最新有数据日，用于复核 areaName/areaNo）
  - 日采样：/hangqing/q-0-0-0-{areaId}-{yyyymmdd}/       （指定日快照）

areaId 一律取自公开行情页，不推测：
  开原市=1599 昌图县=1600 清河区=1601 西丰县=1602 调兵山市=1603 铁岭县=1604

禁止编造：所有字段来自原始页面；抓不到记 status，不补造、不插值。
断点续跑：已落盘且非空的 HTML 直接复用，不重复联网。

用法：
    python3 collect_tieling_county_price.py --collect
    python3 collect_tieling_county_price.py --rebuild
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
import time
from datetime import date, datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(next(p for p in Path(__file__).resolve().parents if (p / "AgriScope").is_dir() and (p / "data").is_dir())) / "tools/collectors"))
from b2b_hangqing_probe import (  # noqa: E402
    UA_MOBILE, UA_DESKTOP, _curl_get, classify, parse_hangqing,
)

HOST_M = "https://m.cnhnb.com"
HOST_W = "https://www.cnhnb.com"
REFERER_M = "https://m.cnhnb.com/hangqing/"
REFERER_W = "https://www.cnhnb.com/hangqing/"
SOURCE_ID = "SRC-CNHNB-HANGQING"
SOURCE_NAME = "惠农网行情"

CITY = "铁岭"
COUNTIES = [
    ("开原市", 1599),
    ("昌图县", 1600),
    ("清河区", 1601),
    ("西丰县", 1602),
    ("调兵山市", 1603),
    ("铁岭县", 1604),
]

BASE = Path(next(p for p in Path(__file__).resolve().parents if (p / "AgriScope").is_dir() and (p / "data").is_dir())) / "city_data/tieling/data"
RAW = BASE.parents[4] / "data/raw" / "web_captures" / "tieling" / "price" / "cnhnb"
STAGING = BASE / ".." / "sources" / "staged" / "price" / "cnhnb"
THROTTLE = 0.9
RETRY_DAYS = 2  # 空页时向后顺延 1..2 天再试


def fetch(area_id: int, ymd: str | None, fname: str) -> tuple[int, bytes, str, bool]:
    RAW.mkdir(parents=True, exist_ok=True)
    target = RAW / fname
    if target.exists() and target.stat().st_size > 0:
        return 200, target.read_bytes(), "", True
    path = f"/hangqing/q-0-0-0-{area_id}/" if ymd is None else f"/hangqing/q-0-0-0-{area_id}-{ymd}/"
    status, body, final = 0, b"", ""
    for host, ua, ref in ((HOST_M, UA_MOBILE, REFERER_M), (HOST_W, UA_DESKTOP, REFERER_W)):
        try:
            status, body, final = _curl_get(host + path, ua, referer=ref)
        except Exception as exc:  # noqa: BLE001
            status, body, final = 0, str(exc).encode(), host + path
        if status == 200 and classify(status, body) == "ok":
            break
        time.sleep(1.0)
    if status == 200 and b"<title>" in body:
        target.write_bytes(body)
    time.sleep(THROTTLE)
    return status, body, final, False


SAMPLE_DAYS = (1, 15)


def sample_dates(start: date, end: date) -> list[date]:
    out: list[date] = []
    y, m = start.year, start.month
    while date(y, m, 1) <= end:
        for day in SAMPLE_DAYS:
            d = date(y, m, day)
            if start <= d <= end:
                out.append(d)
        m += 1
        if m > 12:
            y, m = y + 1, 1
    return sorted(set(out))


def collect(start: date, end: date) -> list[dict]:
    dates = sample_dates(start, end)
    manifest: list[dict] = []
    for county, aid in COUNTIES:
        # 区域页复核 areaName
        st, body, fin, cached = fetch(aid, None, f"_region_{county}_{aid}.html")
        sel = (parse_hangqing(body.decode("utf-8", "ignore")).get("selected") or {}).get("area") or {}
        manifest.append({"kind": "region", "county": county, "areaId": aid,
                         "areaName": sel.get("areaName"), "areaNo": sel.get("areaNo"),
                         "status": classify(st, body), "http": st, "file": f"_region_{county}_{aid}.html"})
        print(f"[region] {county} areaId={aid} -> {sel.get('areaName')} No={sel.get('areaNo')} {classify(st, body)}")
        for d in dates:
            got, used = 0, None
            for k in range(RETRY_DAYS + 1):
                dd = d + timedelta(days=k)
                if dd > end:
                    break
                ymd = dd.strftime("%Y%m%d")
                fname = f"{county}_{aid}_{ymd}.html"
                st, body, fin, cached = fetch(aid, ymd, fname)
                state = classify(st, body)
                n = len(parse_hangqing(body.decode("utf-8", "ignore"))["rows"]) if state == "ok" else 0
                manifest.append({"kind": "day", "county": county, "areaId": aid,
                                 "planned": d.isoformat(), "sample": dd.isoformat(), "ymd": ymd,
                                 "status": state, "http": st, "rows": n, "file": fname,
                                 "cached": cached, "url": fin})
                if n > 0:
                    got, used = n, fname
                    break
                if state != "ok":
                    break
            if got == 0:
                print(f"[day] {county} {d} -> 0")
    RAW.mkdir(parents=True, exist_ok=True)
    (RAW / "tieling_cnhnb_manifest.json").write_text(
        json.dumps({"generated_at": datetime.now().isoformat(timespec="seconds"),
                    "source_id": SOURCE_ID, "counties": COUNTIES,
                    "start": start.isoformat(), "end": end.isoformat(), "manifest": manifest},
                   ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"[collect] manifest {len(manifest)} 条 -> tieling_cnhnb_manifest.json")
    return manifest


WEIGHT_KG = {"斤": 0.5, "公斤": 1.0, "千克": 1.0, "kg": 1.0, "KG": 1.0, "吨": 1000.0}
FIELDS = ["city", "county", "market_name", "store_name", "platform", "crop_raw", "crop_standard",
          "sku_name", "specification", "package_size", "price_original", "unit_original",
          "price_per_kg", "price_level", "observation_date", "observation_time", "frequency",
          "source_type", "source_name", "source_url", "source_id", "retrieval_time",
          "promotion_flag", "member_price_flag", "derived_flag", "quality_grade", "raw_file",
          "geo_level", "record_kind", "note"]


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
    now = datetime.now().isoformat(timespec="seconds")
    seen, rows = set(), []
    pages_ok = pages_bad = 0
    for path in sorted(RAW.glob("*.html")):
        if path.name.startswith("_region"):
            continue
        parts = path.stem.rsplit("_", 1)
        if len(parts) != 2 or not parts[1].isdigit():
            continue
        county_aid, ymd = parts[0], parts[1]
        aid = int(county_aid.split("_")[-1])
        county = county_aid.rsplit("_", 1)[0]
        html = path.read_text(encoding="utf-8", errors="ignore")
        parsed = parse_hangqing(html)
        if not parsed["rows"]:
            pages_bad += 1
            continue
        pages_ok += 1
        odate = f"{ymd[:4]}-{ymd[4:6]}-{ymd[6:]}"
        for r in parsed["rows"]:
            stype = r.get("sourse_type") or ""
            avg, unit = r.get("avgPrice"), r.get("unit")
            cate = r.get("cateName") or ""
            breed = r.get("breedName") or ""
            status_txt = "supply商户供货价" if stype == "supply" else "market市场行情价"
            row = {
                "city": CITY, "county": county,
                "market_name": "惠农网商户供货" if stype == "supply" else "惠农网市场行情",
                "store_name": "", "platform": "cnhnb",
                "crop_raw": breed, "crop_standard": breed, "sku_name": "", "specification": cate,
                "package_size": "", "price_original": avg, "unit_original": ("元/" + unit) if unit else unit,
                "price_per_kg": price_per_kg(avg, unit), "price_level": level_of(stype),
                "observation_date": odate, "observation_time": "", "frequency": "daily",
                "source_type": "third_party_b2b", "source_name": SOURCE_NAME,
                "source_url": f"https://www.cnhnb.com/hangqing/q-0-0-0-{aid}-{ymd}/",
                "source_id": SOURCE_ID, "retrieval_time": now,
                "promotion_flag": "", "member_price_flag": "", "derived_flag": "",
                "quality_grade": "C", "raw_file": f"data/raw/web_captures/tieling/price/cnhnb/{path.name}",
                "geo_level": "county", "record_kind": "",
                "note": f"{status_txt};样本数={r.get('statisNum')};min={r.get('minPrice')};max={r.get('maxPrice')}",
            }
            key = (row["county"], row["crop_raw"], row["specification"], row["observation_date"],
                   row["price_original"], row["unit_original"], row["price_level"], row["market_name"])
            if key in seen:
                continue
            seen.add(key)
            rows.append(row)
    rows.sort(key=lambda x: (x["observation_date"], x["county"], x["crop_raw"], x["specification"]))
    STAGING.mkdir(parents=True, exist_ok=True)
    with (STAGING / "tieling_price_cnhnb_county.csv").open("w", newline="", encoding="utf-8-sig") as fh:
        w = csv.DictWriter(fh, fieldnames=FIELDS)
        w.writeheader()
        w.writerows(rows)
    out = {"pages_ok": pages_ok, "pages_empty": pages_bad, "rows": len(rows),
           "counties": sorted({r["county"] for r in rows}),
           "date_min": min((r["observation_date"] for r in rows), default=None),
           "date_max": max((r["observation_date"] for r in rows), default=None)}
    print(f"[rebuild] pages_ok={pages_ok} empty={pages_bad} rows={len(rows)} -> tieling_price_cnhnb_county.csv")
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--collect", action="store_true")
    ap.add_argument("--rebuild", action="store_true")
    ap.add_argument("--start", default="2020-01-01")
    ap.add_argument("--end", default="2026-09-01")
    args = ap.parse_args()
    if args.collect:
        collect(date.fromisoformat(args.start), date.fromisoformat(args.end))
        rebuild()
    elif args.rebuild:
        rebuild()
    else:
        ap.print_help()


if __name__ == "__main__":
    main()
