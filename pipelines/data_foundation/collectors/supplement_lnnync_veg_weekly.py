#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
采集 辽宁省农业农村厅「省内主要蔬菜品种价格」周度批发价简讯。
来源：https://nync.ln.gov.cn/nync/index/zwgk/zszdgz/ncpxx/lnsnzyscpzjg/
- 枚举 15 页列表页，抓取每篇原文 HTML（保存为原始证据）
- 解析 5-8 个蔬菜品种的批发均价(元/公斤)、环比、同比、最高/最低地区
- 产出标准化 CSV
只读采集，不修改任何既有数据。
"""
from __future__ import annotations
import csv
import json
import re
import ssl
import time
import urllib.request
from pathlib import Path
from datetime import datetime

ROOT = next(p for p in Path(__file__).resolve().parents if (p / "AgriScope").is_dir() and (p / "data").is_dir())
RAW = ROOT / "data/raw" / "decision_engine_supplement" / "price" / "lnnync_veg_weekly"
OUT = ROOT / "data/raw/retained_source/city_data" / "reference" / "decision_engine_supplement"
RAW.mkdir(parents=True, exist_ok=True)

BASE = "https://nync.ln.gov.cn"
LIST = "/nync/index/zwgk/zszdgz/ncpxx/lnsnzyscpzjg/"
CTX = ssl.create_default_context(); CTX.check_hostname = False; CTX.verify_mode = ssl.CERT_NONE
UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")
ACCESS_DATE = datetime.now().strftime("%Y-%m-%d")

# 规范作物名映射
CROP_MAP = {
    "黄瓜": "黄瓜", "西红柿": "西红柿", "大白菜": "大白菜", "芹菜": "芹菜",
    "茄子": "茄子", "尖椒": "尖椒", "大葱": "大葱", "胡萝卜": "胡萝卜",
    "架豆王": "架豆王", "角瓜": "角瓜", "青椒": "青椒", "甘蓝": "甘蓝",
    "土豆": "土豆", "菠菜": "菠菜", "菜花": "菜花", "韭菜": "韭菜",
    "芸豆": "芸豆", "油菜": "油菜", "白萝卜": "白萝卜", "圆葱": "圆葱",
}


def fetch(url: str, retries: int = 3) -> str | None:
    for a in range(retries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": UA})
            with urllib.request.urlopen(req, timeout=40, context=CTX) as r:
                return r.read().decode("utf-8", "replace")
        except Exception as e:
            print(f"   [retry {a+1}] {url[:80]} {e}")
            time.sleep(3)
    return None


def strip_tags(h: str) -> str:
    h = re.sub(r"<script.*?</script>", " ", h, flags=re.S | re.I)
    h = re.sub(r"<style.*?</style>", " ", h, flags=re.S | re.I)
    h = re.sub(r"<[^>]+>", "", h)
    h = (h.replace("&nbsp;", " ").replace("&amp;", "&").replace("&ldquo;", "“")
          .replace("&rdquo;", "”").replace("&mdash;", "—"))
    return re.sub(r"[ \t\u3000]+", " ", h)


def enum_articles() -> list[dict]:
    arts = {}
    for p in range(1, 16):
        url = f"{BASE}{LIST}index.shtml" if p == 1 else f"{BASE}{LIST}e1a5e3b8-{p}.shtml"
        h = fetch(url)
        if not h:
            continue
        for href, title, date in re.findall(
                r'href="(/nync/index/zwgk/zszdgz/ncpxx/lnsnzyscpzjg/\d+/index\.shtml)"[^>]*>'
                r'<span>([^<]+)</span><span>\[([\d-]+)\]', h):
            arts[href] = {"url": BASE + href, "title": title.strip(), "pub_date": date}
        print(f"[list p{p}] 累计 {len(arts)} 篇")
        time.sleep(0.6)
    return list(arts.values())


PRICE_RE = re.compile(
    r"【(?P<crop>[^】]{1,10})】批发均价为\s*(?P<price>[\d.]+)\s*元/公斤，"
    r"环比(?P<mom_dir>上涨|下降|持平)\s*(?P<mom>[\d.]+)?%?，"
    r"同比(?P<yoy_dir>上涨|下降|持平)\s*(?P<yoy>[\d.]+)?%?")
REGION_RE = re.compile(
    r"价格较高的地区是\s*(?P<hi_reg>[^\d，。,\.]{2,24}?)\s*(?P<hi>[\d.]+)\s*/?\s*元?/?\s*公斤?，"
    r"较低的地区是\s*(?P<lo_reg>[^\d，。,\.]{2,24}?)\s*(?P<lo>[\d.]+)\s*/?\s*元?/?\s*公斤?")
WEEK_RE = re.compile(r"(20\d{2})年第(\d{1,2})周")


def clean_name(s: str) -> str:
    return re.sub(r"[\s\u00a0\u3000]+", "", s or "")


def iso_week(date_str: str):
    try:
        d = datetime.strptime(date_str, "%Y-%m-%d")
        y, w, _ = d.isocalendar()
        return str(y), str(w)
    except Exception:
        return "", ""


def parse_article(html: str, meta: dict) -> list[dict]:
    txt = strip_tags(html)
    m = WEEK_RE.search(meta["title"]) or WEEK_RE.search(txt)
    if m:
        year, week = m.group(1), m.group(2)
    else:
        year, week = iso_week(meta["pub_date"])
    rows = []
    # 按【作物】切段，便于把最高/最低地区配到对应作物
    segs = re.split(r"(?=【[^】]{1,10}】批发均价)", txt)
    for seg in segs:
        pm = PRICE_RE.search(seg)
        if not pm:
            continue
        raw_crop = clean_name(pm.group("crop"))
        crop = CROP_MAP.get(raw_crop, raw_crop)
        rm = REGION_RE.search(seg)
        def num(x):
            return float(x) if x not in (None, "") else ""
        rows.append({
            "year": year, "week": week, "pub_date": meta["pub_date"],
            "title": meta["title"], "url": meta["url"],
            "crop_raw": raw_crop, "crop_standard": crop,
            "price": num(pm.group("price")), "unit": "元/公斤",
            "price_level": "wholesale", "geo_level": "province",
            "frequency": "weekly",
            "mom_dir": pm.group("mom_dir"), "mom_pct": num(pm.group("mom")),
            "yoy_dir": pm.group("yoy_dir"), "yoy_pct": num(pm.group("yoy")),
            "highest_region": rm.group("hi_reg").strip() if rm else "",
            "highest_price": num(rm.group("hi")) if rm else "",
            "lowest_region": rm.group("lo_reg").strip() if rm else "",
            "lowest_price": num(rm.group("lo")) if rm else "",
            "source_id": "SRC-LN-NYNC-VEG-WEEKLY",
            "source_name": "辽宁省农业农村厅 省内主要蔬菜品种价格简讯",
            "source_level": "S", "access_date": ACCESS_DATE,
        })
    return rows


def main():
    arts = enum_articles()
    print(f"共枚举 {len(arts)} 篇")
    (RAW / "_article_index.json").write_text(
        json.dumps(arts, ensure_ascii=False, indent=1), encoding="utf-8")

    all_rows = []
    ok = skip = 0
    for i, a in enumerate(arts, 1):
        aid = a["url"].rstrip("/").split("/")[-2]
        f = RAW / f"{aid}.html"
        if f.exists():
            html = f.read_text(encoding="utf-8", errors="replace")
            skip += 1
        else:
            html = fetch(a["url"])
            if html:
                f.write_text(html, encoding="utf-8")
                time.sleep(0.6)
        if not html:
            continue
        all_rows.extend(parse_article(html, a))
        ok += 1
        if i % 25 == 0:
            print(f"  已处理 {i}/{len(arts)}，解析记录 {len(all_rows)}")

    cols = ["year", "week", "pub_date", "crop_raw", "crop_standard", "price", "unit",
            "price_level", "geo_level", "frequency", "mom_dir", "mom_pct",
            "yoy_dir", "yoy_pct", "highest_region", "highest_price",
            "lowest_region", "lowest_price", "source_id", "source_name",
            "source_level", "access_date", "title", "url"]
    with (OUT / "price_lnnync_veg_weekly_extended.csv").open("w", newline="", encoding="utf-8-sig") as fp:
        w = csv.DictWriter(fp, fieldnames=cols, extrasaction="ignore")
        w.writeheader()
        for r in all_rows:
            w.writerow(r)
    print(f"[OK] 文章 {ok} 篇（缓存命中 {skip}），价格记录 {len(all_rows)} 行")
    print(f"     -> {OUT/'price_lnnync_veg_weekly_extended.csv'}")
    if all_rows:
        ys = sorted({r['year'] for r in all_rows if r['year']})
        print(f"     年份范围 {ys[0]}~{ys[-1]}；作物 {sorted({r['crop_standard'] for r in all_rows})}")


if __name__ == "__main__":
    main()
