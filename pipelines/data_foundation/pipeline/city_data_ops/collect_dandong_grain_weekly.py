"""丹东县域「粮油价格简讯」采集（第二轮）：辽宁省农业农村厅周报中的丹东区县极值节点。

来源：辽宁省农业农村厅《辽宁省内主要粮油品种市场价格简讯》（周更）
  https://nync.ln.gov.cn/nync/index/zwgk/zszdgz/ncpxx/lnsnzylypzscjg/index.shtml
  覆盖 2021-03 ~ 2026-09（283 期）。

要点：**旧期（<2024-07）措辞不同**，既有无损源采集器只认新措辞，故此处扩展两套正则：
  - 产地收购价：新「价格较高/较低的地区是X..元/公斤」；旧「最高/最低收购价格出现在X，为..元/公斤」
  - 零售/批发：新「批发均价|零售均价为..」；旧「平均价格为..」

只抽 **丹东县区**（东港市/凤城市/宽甸满族自治县）节点（geo_level=county）。
district→county 仅按显式县名字符串判定，不猜测；其价格性质为「区县极值」，非连续城市价。

原始 HTML 落盘：data/raw/web_captures/dandong/price/lnnync_grain/html/
标准化落盘：city_data/dandong/sources/staged/price/lnnync_grain/

用法：
    python3 collect_dandong_grain_weekly.py --collect
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
import sys
import time
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(next(p for p in Path(__file__).resolve().parents if (p / "AgriScope").is_dir() and (p / "data").is_dir())) / "tools/collectors"))
import lnnync_grain_weekly as L  # noqa: E402

CITY = "丹东"
COUNTY_OF = (("东港", "东港市"), ("凤城", "凤城市"), ("宽甸", "宽甸满族自治县"))

BASE = Path(next(p for p in Path(__file__).resolve().parents if (p / "AgriScope").is_dir() and (p / "data").is_dir())) / "city_data/dandong/data"
RAW = BASE.parents[4] / "data/raw" / "web_captures" / "dandong" / "price" / "lnnync_grain"
HTML_DIR = RAW / "html"
STAGING = BASE / ".." / "sources" / "staged" / "price" / "lnnync_grain"

SOURCE_ID = "SRC-LNNYNC-GRAIN"
SOURCE_NAME = "辽宁省农业农村厅 主要粮油产品价格简讯"

# 措辞A（地点在前）：如「最低收购价格出现在丹东宽甸，为2.26元/公斤」「价格较高的地区是东港黄海超市11.00元/公斤」
#   注意并列句后半常省略「价格」前缀 → 如「…，较低的地区是丹东凤城市2.06元/公斤」
NODE_RE = re.compile(
    r"(最高收购价格出现|最低收购价格出现|价格较高的地区是|价格较低的地区是|价格较高的是|价格较低的是|"
    r"较高的地区是|较低的地区是|较高的是|较低的是)(?:在)?([\u4e00-\u9fff]{2,20}?)(?:，为)?([\d.]+)元/公斤")
# 措辞B（价格在前）：如「最高价格为2.86元/公斤，出现在丹东东港」
NODE_RE_B = re.compile(
    r"(最高价格为|最低价格为)([\d.]+)元/公斤，出现(?:在)?([\u4e00-\u9fff]{2,20}?)(?=[；;。])")


def is_high(kw: str) -> bool:
    return ("最高" in kw) or ("较高" in kw)

FIELDS = ["city", "county", "market_name", "store_name", "platform", "crop_raw", "crop_standard",
          "sku_name", "specification", "package_size", "price_original", "unit_original",
          "price_per_kg", "price_level", "observation_date", "observation_time", "frequency",
          "source_type", "source_name", "source_url", "source_id", "retrieval_time",
          "promotion_flag", "member_price_flag", "derived_flag", "quality_grade", "raw_file",
          "geo_level", "record_kind", "note"]


def html_for(it: dict) -> str | None:
    """优先复用主仓已落盘 HTML，缺失则联网补取并落到本源 raw 目录。"""
    aid = hashlib.md5(it["url"].encode()).hexdigest()[:16]
    master = L.HTML / f"{aid}.html"
    if master.exists():
        return master.read_text(encoding="utf-8")
    if not it.get("date"):
        return None
    dest = HTML_DIR / f"lnnync_grain_{it['date']}_{aid[:8]}.html"
    if dest.exists():
        return dest.read_text(encoding="utf-8")
    try:
        txt = L.get(it["url"])
    except Exception:  # noqa: BLE001
        return None
    time.sleep(0.3)
    return txt


def crop_at(txt: str, pos: int) -> str:
    ci = txt.rfind("【", 0, pos)
    if ci < 0:
        return ""
    cj = txt.find("】", ci)
    return txt[ci + 1:cj] if cj > ci else ""


def collect() -> list[dict]:
    items: list[dict] = []
    for u in [L.INDEX] + L.PAGES:
        try:
            items += L.list_items(L.get(u))
        except Exception as exc:  # noqa: BLE001
            print("  [list fail]", u[-28:], exc)
        time.sleep(0.3)
    seen, uniq = set(), []
    for it in items:
        if it["url"] not in seen:
            seen.add(it["url"])
            uniq.append(it)
    uniq.sort(key=lambda x: x["date"] or "")
    print(f"[list] {len(uniq)} 期  {uniq[0]['date']} ~ {uniq[-1]['date']}")

    now = datetime.now().isoformat(timespec="seconds")
    rows, saved, missing = [], 0, 0
    for it in uniq:
        html = html_for(it)
        if html is None:
            missing += 1
            continue
        txt = L.clean(html)
        if not any(k in txt for k in ("东港", "凤城", "宽甸")):
            continue
        # 落盘含丹东的原始 HTML（证据）
        aid = hashlib.md5(it["url"].encode()).hexdigest()[:16]
        dest = HTML_DIR / f"lnnync_grain_{it['date']}_{aid[:8]}.html"
        HTML_DIR.mkdir(parents=True, exist_ok=True)
        if not dest.exists():
            dest.write_text(html, encoding="utf-8")
            saved += 1
        nodes = []
        for m in NODE_RE.finditer(txt):
            nodes.append((m.group(1), m.group(2), m.group(3), m.start()))
        for m in NODE_RE_B.finditer(txt):
            nodes.append((m.group(1), m.group(3), m.group(2), m.start()))
        for kw, loc, pr, pos in nodes:
            county = next((c for k, c in COUNTY_OF if k in loc), None)
            if county is None:
                continue
            kind = "county_extremum_high" if is_high(kw) else "county_extremum_low"
            crop = crop_at(txt, pos)
            rows.append({
                "city": CITY, "county": county, "market_name": "", "store_name": "",
                "platform": "", "crop_raw": crop, "crop_standard": crop,
                "sku_name": "", "specification": "", "package_size": "",
                "price_original": pr, "unit_original": "元/公斤", "price_per_kg": pr,
                "price_level": "wholesale", "observation_date": it["date"],
                "observation_time": "", "frequency": "weekly",
                "source_type": "official_government", "source_name": SOURCE_NAME,
                "source_url": it["url"], "source_id": SOURCE_ID, "retrieval_time": now,
                "promotion_flag": "", "member_price_flag": "", "derived_flag": "",
                "quality_grade": "B",
                "raw_file": f"data/raw/web_captures/dandong/price/lnnync_grain/html/{dest.name}",
                "geo_level": "county", "record_kind": kind,
                "note": f"区县极值节点（{kw.rstrip('是')}）；原文位置='{loc}'；"
                        f"非连续城市价，仅作极值锚点",
            })
    # 去重（date,crop,record_kind,county）
    seenk, out = set(), []
    for r in rows:
        k = (r["observation_date"], r["crop_raw"], r["record_kind"], r["county"])
        if k in seenk:
            continue
        seenk.add(k)
        out.append(r)
    out.sort(key=lambda x: (x["observation_date"], x["county"], x["crop_raw"]))
    STAGING.mkdir(parents=True, exist_ok=True)
    with (STAGING / "dandong_grain_county.csv").open("w", newline="", encoding="utf-8-sig") as fh:
        w = csv.DictWriter(fh, fieldnames=FIELDS)
        w.writeheader()
        w.writerows(out)
    meta = {"generated_at": now, "articles": len(uniq), "raw_html_saved": saved,
            "articles_missing": missing, "rows": len(out),
            "date_min": out[0]["observation_date"] if out else None,
            "date_max": out[-1]["observation_date"] if out else None}
    (RAW / "dandong_grain_manifest.json").write_text(
        json.dumps(meta, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"[done] rows={len(out)} saved_html={saved} missing={missing} -> dandong_grain_county.csv")
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--collect", action="store_true")
    ap.set_defaults(collect=True)
    ap.parse_args()
    collect()


if __name__ == "__main__":
    main()
