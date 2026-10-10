"""朝阳发改委「朝阳市主要菜篮子产品每日价情」采集脚本。

来源：https://fgw.chaoyang.gov.cn/cysfzhggwyh/zwgk/zwgkzdgz/wjzd/glist.html
输出：
  data/raw/prices/chaoyang/article_meta.json   （全量列表索引：url/date/title）
  data/raw/prices/chaoyang/html/*.html          （文章原文）
  city_data/reference/staging/chaoyang_price_basket.csv        （解析后的价格观测）
"""
from __future__ import annotations

import hashlib
import json
import re
import ssl
import sys
import time
import urllib.request
import urllib.error
from datetime import datetime
from pathlib import Path

import pandas as pd

ROOT = next(p for p in Path(__file__).resolve().parents if (p / "AgriScope").is_dir() and (p / "data").is_dir())
RAW = ROOT / "data/raw" / "prices" / "chaoyang"
HTML = RAW / "html"
STAGING = ROOT / "city_data/reference/staging"
HTML.mkdir(parents=True, exist_ok=True)
STAGING.mkdir(parents=True, exist_ok=True)

CTX = ssl.create_default_context()
CTX.check_hostname = False
CTX.verify_mode = ssl.CERT_NONE
UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36"
LIST_URL = "https://fgw.chaoyang.gov.cn/cysfzhggwyh/zwgk/zwgkzdgz/wjzd/glist.html"


def get_bytes(url: str, retries: int = 3) -> bytes:
    last = None
    # 禁用系统代理（本机 7892 代理对 gov.cn 挂起），走直连
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    for a in range(retries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": UA})
            with opener.open(req, timeout=30) as r:
                return r.read()
        except Exception as exc:
            last = exc
            time.sleep(2 * (a + 1))
    raise last


def decode(raw: bytes) -> str:
    for enc in ("utf-8", "gbk", "gb18030"):
        try:
            return raw.decode(enc)
        except Exception:
            continue
    return raw.decode("utf-8", "ignore")


def fetch_list_pages(n_pages: int = 200) -> list[dict]:
    """抓取列表页，返回 [{url, title, date}, ...] 按日期降序。
    部分页码可能 404（分页不连续），跳过继续。"""
    arts = []
    for p in range(1, n_pages + 1):
        url = LIST_URL if p == 1 else LIST_URL.replace("glist.html", f"glist{p}.html")
        try:
            html = decode(get_bytes(url))
        except Exception as exc:
            if isinstance(exc, urllib.error.HTTPError) and exc.code == 404:
                print(f"  列表页 {p}: 404 跳过")
                continue
            raise
        items = re.findall(
            r'href="(https://fgw\.chaoyang\.gov\.cn/html/CYFGW/\d{6}/[^"]+\.html)"[^>]*>\s*'
            r"<b>([^<]*)</b>\s*<span>([^<]*)</span>", html)
        for u, t, d in items:
            arts.append({"url": u, "title": t.strip(), "date": d.strip()})
        print(f"  列表页 {p}: {len(items)} 条")
        time.sleep(0.6)
    # 去重保序
    seen, out = set(), []
    for a in arts:
        if a["url"] not in seen:
            seen.add(a["url"])
            out.append(a)
    return out


def parse_table(html: str, article_date: str) -> list[dict]:
    """解析每日价情表格。"""
    rows = []
    for tbm in re.finditer(r"<table[\s\S]*?</table>", html, re.I):
        t = tbm.group(0)
        for row in re.finditer(r"<tr[\s\S]*?</tr>", t, re.I):
            cells = re.findall(r"<t[dh][\s\S]*?</t[dh]>", row.group(0), re.I)
            if len(cells) < 4:
                continue
            def c(i):
                c = re.sub(r"<[^>]+>", " ", cells[i])
                c = c.replace("&nbsp;", " ").replace("\xa0", " ")
                return re.sub(r"\s+", " ", c).strip()
            name, typ, unit, price = c(0), c(1), c(2), c(3)
            if not name or not price:
                continue
            pm = re.search(r"([\d.]+)", price)
            if not pm:
                continue
            rows.append({"article_date": article_date, "product": name,
                         "product_type": typ, "unit_raw": unit,
                         "price": pm.group(1), "price_raw": price})
    return rows


def main(months: int = 12) -> None:
    arts = fetch_list_pages()
    (RAW / "article_meta.json").write_text(
        json.dumps(arts, ensure_ascii=False, indent=1), encoding="utf-8")
    dates = sorted(a["date"] for a in arts)
    print(f"[索引] 共 {len(arts)} 篇，范围 {dates[0]} ~ {dates[-1]}")

    # 按日期降序取最近 N 个月（跨年安全）
    latest = datetime.strptime(dates[-1], "%Y-%m-%d")
    y, mo = latest.year, latest.month - (months - 1)
    while mo <= 0:
        mo += 12
        y -= 1
    cutoff = datetime(y, mo, 1)
    sel = [a for a in arts if datetime.strptime(a["date"], "%Y-%m-%d") >= cutoff]
    print(f"[下载] 最近 {months} 个月 {len(sel)} 篇")

    all_obs = []
    ok = 0
    for a in sel:
        h = hashlib.md5(a["url"].encode()).hexdigest()[:12]
        f = HTML / f"{h}.html"
        if not f.exists():
            try:
                f.write_bytes(get_bytes(a["url"]))
            except Exception as exc:
                print(f"  [FAIL] {a['date']}: {exc}")
                continue
            time.sleep(0.7)
        obs = parse_table(decode(f.read_bytes()), a["date"])
        all_obs.extend(obs)
        ok += 1
        print(f"  [OK] {a['date']} 观测{len(obs)}")
    print(f"[完成] 文章 {ok} 篇，观测 {len(all_obs)} 条")

    if all_obs:
        df = pd.DataFrame(all_obs)
        df["city"] = "朝阳"
        df["source_id"] = "SRC-CY-FGW-BASKET"
        df["source_name"] = "朝阳市发改委·主要菜篮子产品每日价情(全市平均)"
        df["source_url"] = LIST_URL
        df["fetch_time"] = datetime.now().isoformat(timespec="seconds")
        df["parser_version"] = "chaoyang_basket_v1"
        df["quality_grade"] = "A"
        out = STAGING / "chaoyang_price_basket.csv"
        df.to_csv(out, index=False, encoding="utf-8-sig")
        print(f"[OK] → {out}")
        print(df.groupby("product").size().sort_values(ascending=False).to_string())


if __name__ == "__main__":
    m = int(sys.argv[1]) if len(sys.argv) > 1 else 12
    main(m)
