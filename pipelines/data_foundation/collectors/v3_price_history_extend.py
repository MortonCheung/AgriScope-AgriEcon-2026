#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
V3 P0-4：把「辽宁 省内主要蔬菜品种价格简讯」向历史（2022 之前）延长。

既有数据 price_lnnync_veg_weekly_extended.csv 覆盖 2022-12 ~ 2026-09。
辽宁省农业农村厅旧 CMS 的文章路径为：
    http://nync.ln.gov.cn/zwgk/zdgz/ncpxx/<子栏目>/YYYYMM/tYYYYMMDD_#######.html
该路径现已 404，但 web.archive.org 保留了若干旧快照。
本脚本：
  1) 用 CDX API 枚举归档中 ncpxx 栏目下全部历史文章快照；
  2) 逐个下载 Wayback 快照（id_ 原始版本）保存为证据 HTML；
  3) 只保留「主要蔬菜品种价格简讯」型文章（含多个【品种】批发均价为 X 元/公斤）；
  4) 解析为与既有 CSV 完全一致的字段口径，追加 is_proxy / source_type / source_url / source_text；
  5) 产出历史 CSV + 来源登记 + 备注。

只读采集；不修改 v3 目录以外的任何文件。
"""
from __future__ import annotations

import csv
import json
import re
import ssl
import time
import urllib.request
from datetime import datetime
from pathlib import Path

ROOT = next(p for p in Path(__file__).resolve().parents if (p / "AgriScope").is_dir() and (p / "data").is_dir())
RAW = ROOT / "data/raw" / "decision_engine_supplement_v3" / "price"
HTML = RAW / "html"
OUT = ROOT / "data/raw/retained_source/city_data" / "reference" / "decision_engine_supplement_v3"
HTML.mkdir(parents=True, exist_ok=True)
OUT.mkdir(parents=True, exist_ok=True)
ACCESS_DATE = "2026-10-04"

CTX = ssl.create_default_context()
CTX.check_hostname = False
CTX.verify_mode = ssl.CERT_NONE
UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")

CDX_TMPL = ("http://web.archive.org/cdx/search/cdx?url={u}&matchType=prefix&output=json"
            "&from=2015&to=2024&limit=20000&fl=timestamp,original,statuscode")

CROP_MAP = {
    "黄瓜": "黄瓜", "西红柿": "西红柿", "大白菜": "大白菜", "芹菜": "芹菜",
    "茄子": "茄子", "尖椒": "尖椒", "大葱": "大葱", "胡萝卜": "胡萝卜",
    "架豆王": "架豆王", "角瓜": "角瓜", "青椒": "青椒", "甘蓝": "甘蓝",
    "土豆": "土豆", "菠菜": "菠菜", "菜花": "菜花", "韭菜": "韭菜",
    "芸豆": "芸豆", "油菜": "油菜", "白萝卜": "白萝卜", "圆葱": "圆葱",
    "蒜薹": "蒜薹", "生菜": "生菜", "冬瓜": "冬瓜", "南瓜": "南瓜",
    "小白菜": "小白菜", "辣椒": "辣椒",
}


def fetch(url: str, retries: int = 3, timeout: int = 60) -> str | None:
    for a in range(retries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": UA})
            with urllib.request.urlopen(req, timeout=timeout, context=CTX) as r:
                return r.read().decode("utf-8", "replace")
        except Exception as e:  # noqa
            print(f"   [retry {a+1}] {url[:90]} {e}")
            time.sleep(2 + a)
    return None


def enumerate_cdx() -> dict:
    """返回 {original_url: wayback_timestamp}，覆盖 ncpxx 全部子栏目。"""
    out: dict[str, str] = {}
    for prefix in ("nync.ln.gov.cn/zwgk/zdgz/ncpxx/",):
        r = fetch(CDX_TMPL.format(u=prefix), timeout=180)
        if not r:
            continue
        try:
            data = json.loads(r)
        except Exception:
            continue
        for row in data[1:]:
            ts, orig, sc = row[0], row[1], row[2]
            if sc == "200" and "/t2" in orig and orig.endswith(".html"):
                out.setdefault(orig, ts)
    return out


def strip_tags(h: str) -> str:
    h = re.sub(r"<script.*?</script>", " ", h, flags=re.S | re.I)
    h = re.sub(r"<style.*?</style>", " ", h, flags=re.S | re.I)
    h = re.sub(r"<[^>]+>", "", h)
    h = (h.replace("&nbsp;", " ").replace("&#160;", " ").replace("&amp;", "&")
         .replace("&ldquo;", "“").replace("&rdquo;", "”").replace("&mdash;", "—"))
    return re.sub(r"[ \t\u3000]+", " ", h)


def norm_txt(h: str) -> str:
    """压掉所有空白，便于对旧格式（字间带空格）统一匹配。"""
    return re.sub(r"[\s\u00a0\u3000]+", "", strip_tags(h))


# 只要蔬菜品种；畜/水/粮油/水果一律排除
VEG_SET = set(CROP_MAP.values()) | {
    "西红柿", "大白菜", "芹菜", "茄子", "尖椒", "大葱", "胡萝卜", "架豆王",
    "黄瓜", "土豆", "角瓜", "青椒", "甘蓝", "菠菜", "菜花", "韭菜", "芸豆",
    "油菜", "白萝卜", "圆葱", "蒜薹", "生菜", "冬瓜", "南瓜", "小白菜", "辣椒",
}

CROP_SEG_RE = re.compile(r"(?=【[^】]{1,12}】批发均价)")
CROP_RE = re.compile(
    r"【(?P<crop>[^】]{1,12})】批发均价为?(?P<price>\d+(?:\.\d+)?)元/?公斤"
    r"(?:，环比(?P<mom_dir>上涨|下降|持平)(?P<mom>\d+(?:\.\d+)?)?%?)?"
    r"(?:，同比(?P<yoy_dir>上涨|下降|持平)(?P<yoy>\d+(?:\.\d+)?)?%?)?")
HI_RE = re.compile(
    r"较高(?:的地区)?是?[，,]?(?P<reg>[^，,。\.\d]{2,30}?)[，,]?(?P<price>\d+(?:\.\d+)?)元/?公斤")
LO_RE = re.compile(
    r"较低(?:的地区)?是?[，,]?(?P<reg>[^，,。\.\d]{2,30}?)[，,]?(?P<price>\d+(?:\.\d+)?)元/?公斤")
WEEK_RE = re.compile(r"(20\d{2})年第(\d{1,2})周")
WEEK_ONLY_RE = re.compile(r"第(\d{1,2})周")
DATE_IN_URL_RE = re.compile(r"/t(20\d{2})(\d{2})(\d{2})_")
# 蔬菜子报告标题：辽宁省内第17周主要蔬菜品种市场价格简讯
VEG_HEAD_RE = re.compile(r"辽宁省内第(\d{1,2})周主要蔬菜(?:品种市场价格|品种价格|产品价格)简讯")
# 任意子报告标题（用于切段：粮油/蔬菜/畜水…）
ANY_HEAD_RE = re.compile(r"辽宁省内第\d{1,2}周主要[^。]{2,16}简讯")
PERIOD_RE = re.compile(r"[上周本]+周?（(\d{4})年(\d{1,2})月(\d{1,2})日")
TITLE_YEAR_RE = re.compile(r"(20\d{2})年辽宁省内")
CONTENT_SNIP_RE = re.compile(r"【[^】]{1,12}】[^【]{0,150}")


def clean_name(s: str) -> str:
    return re.sub(r"[\s\u00a0\u3000]+", "", s or "")


def iso_week(d: datetime):
    y, w, _ = d.isocalendar()
    return str(y), str(w)


def extract_section(txt: str, title: str):
    """定位蔬菜子报告段落，返回 (section_text, year, week) 或 (None,'','')。"""
    m = VEG_HEAD_RE.search(txt)
    if not m:
        # 新格式单篇蔬菜简讯（页面标题含“蔬菜”）
        if "蔬菜" in title:
            return txt, "", ""
        return None, "", ""
    week = m.group(1)
    start = m.end()
    nxt = ANY_HEAD_RE.search(txt, start)
    sec = txt[start:nxt.start()] if nxt else txt[start:]
    year = ""
    pm = PERIOD_RE.search(sec)
    if pm:
        year = pm.group(1)
    if not year:
        tm = TITLE_YEAR_RE.search(title)
        year = tm.group(1) if tm else ""
    return sec, year, week


def parse_article(html: str, meta: dict) -> list[dict]:
    txt = norm_txt(html)
    if "批发均价" not in txt:
        return []
    title = meta["title"]
    sec, year, week = extract_section(txt, title)
    if sec is None:
        return []
    pub_date = meta["pub_date"]
    if not year:
        tm = TITLE_YEAR_RE.search(title)
        year = tm.group(1) if tm else (pub_date[:4] if pub_date else "")
    if not week:
        wm = WEEK_RE.search(title)
        if wm:
            year, week = wm.group(1), wm.group(2)
        else:
            wo = WEEK_ONLY_RE.search(title)
            if wo:
                week = wo.group(1)
        if not week and pub_date:
            try:
                year, week = iso_week(datetime.strptime(pub_date, "%Y-%m-%d"))
            except Exception:
                pass
    rows = []
    for seg in CROP_SEG_RE.split(sec):
        pm = CROP_RE.search(seg)
        if not pm:
            continue
        raw_crop = clean_name(pm.group("crop"))
        crop = CROP_MAP.get(raw_crop, raw_crop)
        if crop not in VEG_SET:
            continue
        snippet = strip_tags(seg)
        snippet = re.sub(r"\s+", " ", snippet).strip()[:150]
        hm = HI_RE.search(seg)
        lm = LO_RE.search(seg)

        def num(x):
            return float(x) if x not in (None, "") else ""

        rows.append({
            "year": year, "week": week, "pub_date": pub_date,
            "crop_raw": raw_crop, "crop_standard": crop,
            "price": num(pm.group("price")), "unit": "元/公斤",
            "price_level": "wholesale", "geo_level": "province",
            "frequency": "weekly",
            "mom_dir": pm.group("mom_dir") or "", "mom_pct": num(pm.group("mom")),
            "yoy_dir": pm.group("yoy_dir") or "", "yoy_pct": num(pm.group("yoy")),
            "highest_region": clean_name(hm.group("reg")) if hm else "",
            "highest_price": num(hm.group("price")) if hm else "",
            "lowest_region": clean_name(lm.group("reg")) if lm else "",
            "lowest_price": num(lm.group("price")) if lm else "",
            "source_id": "SRC-LN-NYNC-VEG-WEEKLY-HIST",
            "source_name": "辽宁省农业农村厅 省内主要蔬菜品种价格简讯(历史, Wayback)",
            "source_level": "S", "access_date": ACCESS_DATE,
            "title": title, "url": meta["url"],
            "is_proxy": "false", "source_type": "archive_wayback",
            "source_text": snippet,
        })
    return rows


def title_from_html(html: str, fallback: str) -> str:
    # 旧综合周报标题形如：[农产品价格信息]2019年辽宁省内17周主要农产品价格信息简讯
    m = re.search(r'\[[^\]]*农产品价格信息\][^<]*简讯', html)
    if not m:
        m = re.search(r"(20\d{2}年)?辽宁省内第\d{1,2}周主要[^<]{2,20}简讯", html)
    if m:
        return clean_name(m.group(0))
    return fallback


def main() -> None:
    arts = enumerate_cdx()
    print(f"[CDX] ncpxx 归档文章 {len(arts)} 篇")
    (RAW / "_cdx_articles.json").write_text(
        json.dumps(arts, ensure_ascii=False, indent=1), encoding="utf-8")

    all_rows = []
    n_veg = 0
    cache_hit = 0
    for i, (orig, ts) in enumerate(sorted(arts.items(), key=lambda kv: kv[1]), 1):
        aid = re.sub(r"[^0-9A-Za-z]+", "_", orig.split("ncpxx/", 1)[-1])
        f = HTML / f"hist_{ts}_{aid}"
        if f.exists():
            html = f.read_text(encoding="utf-8", errors="replace")
            cache_hit += 1
        else:
            wb_url = f"http://web.archive.org/web/{ts}id_/{orig}"
            html = fetch(wb_url)
            if html:
                f.write_text(html, encoding="utf-8")
            time.sleep(0.4)
        if not html:
            continue
        dm = DATE_IN_URL_RE.search(orig)
        pub = f"{dm.group(1)}-{dm.group(2)}-{dm.group(3)}" if dm else ""
        wb_url = f"http://web.archive.org/web/{ts}/{orig}"
        meta = {"url": wb_url, "pub_date": pub,
                "title": title_from_html(html, orig.split("/")[-1])}
        rows = parse_article(html, meta)
        if rows:
            n_veg += 1
            print(f"   [{n_veg}] {pub} {meta['title'][:34]} -> {len(rows)} 品种")
        all_rows.extend(rows)

    # 去重：同 (year,week,crop) 保留首条
    seen = set()
    ded = []
    for r in all_rows:
        k = (r["year"], r["week"], r["crop_standard"])
        if k in seen:
            continue
        seen.add(k)
        ded.append(r)

    ded.sort(key=lambda r: (r["year"], int(r["week"]) if str(r["week"]).isdigit() else 0))
    cols = ["year", "week", "pub_date", "crop_raw", "crop_standard", "price", "unit",
            "price_level", "geo_level", "frequency", "mom_dir", "mom_pct",
            "yoy_dir", "yoy_pct", "highest_region", "highest_price",
            "lowest_region", "lowest_price", "source_id", "source_name",
            "source_level", "access_date", "title", "url",
            "is_proxy", "source_type", "source_text"]

    # 解析结果原始副本（保存在 v3 原始数据集目录）
    with (RAW / "price_history_parsed.csv").open(
            "w", newline="", encoding="utf-8-sig") as fp:
        w = csv.DictWriter(fp, fieldnames=cols, extrasaction="ignore")
        w.writeheader()
        w.writerows(ded)

    with (OUT / "price_lnnync_veg_weekly_historical.csv").open(
            "w", newline="", encoding="utf-8-sig") as fp:
        w = csv.DictWriter(fp, fieldnames=cols, extrasaction="ignore")
        w.writeheader()
        w.writerows(ded)

    rules = ded[-1]["access_date"] if ded else "-"
    ys = sorted({r["year"] for r in ded if r["year"]})
    print(f"[OK] 归档 {len(arts)} 篇（缓存命中 {cache_hit}），命中蔬菜简讯 {n_veg} 篇，"
          f"去重后 {len(ded)} 行；年份 {ys[0] if ys else '-'}~{ys[-1] if ys else '-'} "
          f"(access {rules})")


if __name__ == "__main__":
    main()
