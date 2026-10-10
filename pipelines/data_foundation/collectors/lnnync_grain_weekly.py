"""辽宁省农业农村厅「主要粮油产品价格简讯」周报采集 + 区县极值价格解析。

栏目：https://nync.ln.gov.cn/nync/index/zwgk/zszdgz/ncpxx/lnsnzylypzscjg/index.shtml
分页：/nync/index/zwgk/zszdgz/ncpxx/lnsnzylypzscjg/e1a5e3b8-{N}.shtml  （N=2..15，尾页15）

每期结构（样例）：
  【黄瓜】批发均价为3.80元/公斤，环比上涨11.82%，同比上涨42.77%。
  价格较高的地区是朝阳市双塔区5.00元/公斤，较低的地区是大连市甘井子区2.00元/公斤。

产出两类记录（**均为极值口径，严格隔离，不得当连续城市价格**）：
  1) province_wholesale_avg : 省级批发均价（可作 province 基准）
  2) county_extremum        : 区县极值价格（可映射到 city，但标注 extremum）

区县 → 城市映射仅用于**标注归属**，不改变其极值性质。
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import ssl
import time
import urllib.request
from pathlib import Path

import pandas as pd

for k in ("HTTP_PROXY", "HTTPS_PROXY", "http_proxy", "https_proxy", "ALL_PROXY", "all_proxy"):
    os.environ.pop(k, None)

ROOT = next(p for p in Path(__file__).resolve().parents if (p / "AgriScope").is_dir() and (p / "data").is_dir())
RAW = ROOT / "data/raw" / "prices" / "lnnync_grain_weekly"
HTML = RAW / "html"
HTML.mkdir(parents=True, exist_ok=True)
STAGING = ROOT / "city_data/reference/staging"

CTX = ssl.create_default_context()
CTX.check_hostname = False
CTX.verify_mode = ssl.CERT_NONE
UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")
BASE = "https://nync.ln.gov.cn/nync/index/zwgk/zszdgz/ncpxx/lnsnzylypzscjg"
INDEX = BASE + "/index.shtml"
# 粮油栏目分页 ID 与蔬菜栏目不同（蔬菜=e1a5e3b8，粮油=1732d1c7）
PAGES = [f"{BASE}/1732d1c7-{n}.shtml" for n in range(2, 16)]

CITY_OF = {
    "沈阳": "沈阳", "大连": "大连", "鞍山": "鞍山", "抚顺": "抚顺", "本溪": "本溪",
    "丹东": "丹东", "锦州": "锦州", "营口": "营口", "阜新": "阜新", "辽阳": "辽阳",
    "盘锦": "盘锦", "铁岭": "铁岭", "朝阳": "朝阳", "葫芦岛": "葫芦岛",
}


def get(url: str, timeout: int = 30, retries: int = 3) -> str:
    last = None
    for a in range(retries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": UA, "Referer": INDEX})
            with urllib.request.urlopen(req, timeout=timeout, context=CTX) as r:
                raw = r.read()
            for enc in ("utf-8", "gb18030"):
                try:
                    return raw.decode(enc)
                except UnicodeDecodeError:
                    continue
            return raw.decode("utf-8", "replace")
        except Exception as exc:
            last = exc
            time.sleep(2 * (a + 1))
    raise last


def list_items(html: str) -> list[dict]:
    out = []
    for m in re.finditer(r'<a[^>]*href="([^"]+)"[^>]*>(.*?)</a>', html, re.S):
        href, tx = m.group(1), re.sub(r"<[^>]+>", "", m.group(2)).strip()
        if "简讯" not in tx:
            continue
        full = href if href.startswith("http") else "https://nync.ln.gov.cn" + href
        dm = re.search(r"\[(20\d\d-\d\d-\d\d)\]", tx)
        wm = re.search(r"(\d{4})年第(\d+)周", tx)
        out.append({"url": full, "title": tx,
                    "date": dm.group(1) if dm else "",
                    "iso_year": int(wm.group(1)) if wm else None,
                    "iso_week": int(wm.group(2)) if wm else None})
    seen, uniq = set(), []
    for it in out:
        if it["url"] not in seen:
            seen.add(it["url"]); uniq.append(it)
    return uniq


def clean(html: str) -> str:
    b = re.sub(r"<(script|style)[^>]*>.*?</\1>", "", html, flags=re.S)
    b = re.sub(r"<[^>]+>", "", b)
    b = re.sub(r"&nbsp;|&#160;", " ", b)
    return re.sub(r"\s+", " ", b)


def parse_article(txt: str, meta: dict) -> list[dict]:
    rows = []
    # 周区间：本周（YYYY年M月D日至YYYY年M月D日）
    # 产地收购价（农场价 farm_gate），如【玉米】干玉米…收购均价为2.26元/公斤
    for m in re.finditer(
            r"【([^】]+)】[^【]*?收购均价为([\d.]+)元/公斤"
            r"[^【]*?价格较高的地区是([^，。]{2,12}?)([\d.]+)元/公斤"
            r"[^【]*?较低的地区是([^，。]{2,12}?)([\d.]+)元/公斤", txt):
        crop = m.group(1).strip(); p = float(m.group(2))
        rows.append({
            "date": meta["date"], "iso_year": meta["iso_year"], "iso_week": meta["iso_week"],
            "crop": crop, "record_kind": "province_farm_gate",
            "geo_level": "province", "city": "辽宁省", "district": None,
            "price": p, "unit_raw": "元/公斤", "price_per_kg": p,
            "price_type": "farm_gate", "frequency": "weekly",
        })
        for grp, kind in ((3, "county_extremum_high"), (5, "county_extremum_low")):
            if not m.group(grp):
                continue
            dist = m.group(grp).strip()
            rows.append({
                "date": meta["date"], "iso_year": meta["iso_year"], "iso_week": meta["iso_week"],
                "crop": crop, "record_kind": kind,
                "geo_level": "county", "city": city_of(dist), "district": dist,
                "price": float(m.group(grp + 1)), "unit_raw": "元/公斤",
                "price_per_kg": float(m.group(grp + 1)),
                "price_type": "farm_gate", "frequency": "weekly",
            })
    for m in re.finditer(
            r"【([^】]+)】[^【]*?(?:批发均价|零售均价)为([\d.]+)元/公斤"
            r"[^【]*?价格较高的地区是([^，。]{2,12}?)([\d.]+)元/公斤"
            r"[^【]*?较低的地区是([^，。]{2,12}?)([\d.]+)元/公斤", txt):
        crop = m.group(1).strip()
        avg = float(m.group(2))
        rows.append({
            "date": meta["date"], "iso_year": meta["iso_year"], "iso_week": meta["iso_week"],
            "crop": crop, "record_kind": "province_wholesale_avg",
            "geo_level": "province", "city": "辽宁省", "district": None,
            "price": avg, "unit_raw": "元/公斤", "price_per_kg": avg,
            "price_type": "wholesale", "frequency": "weekly",
        })
        if m.group(3) and m.group(4):
            d_hi = m.group(3).strip()
            rows.append({
                "date": meta["date"], "iso_year": meta["iso_year"], "iso_week": meta["iso_week"],
                "crop": crop, "record_kind": "county_extremum_high",
                "geo_level": "county", "city": city_of(d_hi), "district": d_hi,
                "price": float(m.group(4)), "unit_raw": "元/公斤",
                "price_per_kg": float(m.group(4)),
                "price_type": "wholesale", "frequency": "weekly",
            })
        if m.group(5) and m.group(6):
            d_lo = m.group(5).strip()
            rows.append({
                "date": meta["date"], "iso_year": meta["iso_year"], "iso_week": meta["iso_week"],
                "crop": crop, "record_kind": "county_extremum_low",
                "geo_level": "county", "city": city_of(d_lo), "district": d_lo,
                "price": float(m.group(6)), "unit_raw": "元/公斤",
                "price_per_kg": float(m.group(6)),
                "price_type": "wholesale", "frequency": "weekly",
            })
    return rows


def city_of(district: str) -> str | None:
    for k, v in CITY_OF.items():
        if district.startswith(k):
            return v
    return None


def main() -> None:
    print("=== 辽宁省主要粮油产品价格简讯：列表抓取 ===")
    items = []
    for u in [INDEX] + PAGES:
        try:
            items += list_items(get(u))
        except Exception as exc:
            print(f"  [列表 {u[-28:]}] 失败 {exc}")
        time.sleep(0.3)
    seen, uniq = set(), []
    for it in items:
        if it["url"] not in seen:
            seen.add(it["url"]); uniq.append(it)
    items = uniq
    print(f"[OK] 列表 {len(items)} 期")
    if items:
        ds = sorted([i["date"] for i in items if i["date"]])
        print(f"    日期 {ds[0]} ~ {ds[-1]}")
    (RAW / "article_index.json").write_text(json.dumps(items, ensure_ascii=False, indent=1),
                                            encoding="utf-8")

    print("\n=== 文章下载与解析 ===")
    rows = []
    saved = skip = fail = 0
    for it in items:
        aid = hashlib.md5(it["url"].encode()).hexdigest()[:16]
        f = HTML / f"{aid}.html"
        if not f.exists():
            try:
                f.write_text(get(it["url"]), encoding="utf-8")
                saved += 1
            except Exception:
                fail += 1
                continue
            time.sleep(0.28)
        else:
            skip += 1
        try:
            rows += parse_article(clean(f.read_text(encoding="utf-8")), it)
        except Exception:
            pass
    print(f"    新增 {saved}，跳过 {skip}，失败 {fail}")
    if not rows:
        print("[WARN] 无解析结果")
        return
    df = pd.DataFrame(rows)
    for r in rows:
        r.setdefault("source_id", "SRC-LNNYNC-GRAIN")
    df["source_id"] = "SRC-LNNYNC-GRAIN"
    df["source_name"] = "辽宁省农业农村厅 主要粮油产品价格简讯"
    df["source_url"] = ""
    for i, it in enumerate(items):
        pass
    df["quality_grade"] = "B"
    df["note"] = ("省级批发均价 + 区县极值价格；"
                  "极值为最高/最低地区，非连续城市价格，严禁当城市价序列使用")
    df = df.drop_duplicates(subset=["date", "crop", "record_kind", "district"])
    df.to_csv(STAGING / "lnnync_grain_weekly.csv", index=False, encoding="utf-8-sig")
    print(f"\n[OK] lnnync_grain_weekly.csv {len(df)} 行")
    print(df.groupby("record_kind").size().to_string())
    cy = df[df["city"].isin(CITY_OF.values())]
    if len(cy):
        print("\n六城相关区县极值：")
        print(cy.groupby("city").agg(n=("price", "size"),
                                     crops=("crop", "nunique")).to_string())


if __name__ == "__main__":
    main()
