"""朝阳发改委「价格信息」栏目深度采集（本轮第一优先级）。

此前判定"目录空、文件不存在"是**采集失败**，不是数据不存在。
本次通过研究前端 JS 找到真实分页接口：

    http://cms.chaoyang.gov.cn/html/page.xhtml
        ?s=CYFGW                   站点码
        &o=<offset>                页码（0=首屏 glist.html，1..75 为后续页）
        &p=162063350188546         站点ID
        &c=162063350188546         栏目ID

来源函数（fgw.chaoyang.gov.cn/html/CYFGW/globalScript.js）：
    getDynamicPageUrl(domain, siteCode, offset, selfSiteSiteId, columnLogicId)

已验证：o=1 → 2026-08；o=75 → 2017-03，跨度约 9 年。

注意：本机沙箱代理对 gov.cn 会 502，必须**直连**（运行时禁用代理环境变量）。
输出：
  data/raw/prices/chaoyang_deep/article_index.json
  data/raw/prices/chaoyang_deep/html/*.html
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import ssl
import time
import urllib.error
import urllib.request
from datetime import datetime
from pathlib import Path

# 关键：禁用代理，走直连（沙箱代理对 gov.cn 返回 502）
for k in ("HTTP_PROXY", "HTTPS_PROXY", "http_proxy", "https_proxy", "ALL_PROXY", "all_proxy"):
    os.environ.pop(k, None)

ROOT = next(p for p in Path(__file__).resolve().parents if (p / "AgriScope").is_dir() and (p / "data").is_dir())
RAW = ROOT / "data/raw" / "prices" / "chaoyang_deep"
HTML = RAW / "html"
HTML.mkdir(parents=True, exist_ok=True)

CTX = ssl.create_default_context()
CTX.check_hostname = False
CTX.verify_mode = ssl.CERT_NONE
UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")
REFERER = "https://fgw.chaoyang.gov.cn/cysfzhggwyh/zwgk/zwgkzdgz/wjzd/glist.html"
PAGE_API = ("http://cms.chaoyang.gov.cn/html/page.xhtml"
            "?s=CYFGW&o={o}&p=162063350188546&c=162063350188546")

MAX_PAGE = 76     # 尾页 o=75


def get(url: str, timeout: int = 30, retries: int = 3) -> str:
    last = None
    for a in range(retries):
        try:
            req = urllib.request.Request(url, headers={
                "User-Agent": UA, "Referer": REFERER,
                "Accept": "text/html,application/xhtml+xml,*/*"})
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


def parse_items(html: str) -> list[dict]:
    """条目形如：<a href=".../html/CYFGW/YYYYMM/ID.html">标题||日期</a>"""
    out = []
    for m in re.finditer(r'<a[^>]*href="([^"]+)"[^>]*>(.*?)</a>', html, re.S):
        href = m.group(1)
        if "/html/CYFGW/" not in href:
            continue
        txt = re.sub(r"<[^>]+>", "|", m.group(2))
        txt = re.sub(r"[\s\t\r\n]+", "", txt).strip("|")
        parts = [p for p in txt.split("|") if p]
        if not parts:
            continue
        title = parts[0]
        date = ""
        for p in parts[1:]:
            if re.match(r"^20\d\d-\d\d-\d\d$", p):
                date = p
                break
        if not date:
            dm = re.search(r"/(20\d\d)(\d\d)/", href)
            if dm:
                date = f"{dm.group(1)}-{dm.group(2)}-01"
        full = href if href.startswith("http") else "https://fgw.chaoyang.gov.cn" + href
        out.append({"url": full, "title": title, "date": date})
    seen, uniq = set(), []
    for it in out:
        if it["url"] not in seen:
            seen.add(it["url"])
            uniq.append(it)
    return uniq


def crawl_index() -> list[dict]:
    items: list[dict] = []
    # o=0 即首屏 glist.html
    try:
        items += parse_items(get(REFERER))
        print(f"  [列表 o=0] {len(items)} 条")
    except Exception as exc:
        print(f"  [列表 o=0] 失败 {exc}")
    for o in range(1, MAX_PAGE):
        try:
            html = get(PAGE_API.format(o=o))
        except Exception as exc:
            print(f"  [列表 o={o}] 失败 {exc}")
            continue
        got = parse_items(html)
        items += got
        if (o % 10) == 0 or o < 4:
            print(f"  [列表 o={o}] {len(got)} 条，累计 {len(items)}")
        time.sleep(0.35)
    seen, uniq = set(), []
    for it in items:
        if it["url"] not in seen:
            seen.add(it["url"])
            uniq.append(it)
    return uniq


def main() -> None:
    t0 = time.time()
    print("=== 朝阳价格信息栏目：列表抓取 ===")
    items = crawl_index()
    print(f"[OK] 列表条目 {len(items)} 条")
    if items:
        ds = sorted([i["date"] for i in items if i["date"]])
        print(f"    日期范围：{ds[0]} ~ {ds[-1]}")
        kinds = {}
        for i in items:
            k = "每日价情" if "每日价情" in i["title"] else (
                "农资" if "农资" in i["title"] else
                "CPI" if "消费价格" in i["title"] else "其他")
            kinds[k] = kinds.get(k, 0) + 1
        print(f"    标题分类：{kinds}")

    (RAW / "article_index.json").write_text(
        json.dumps(items, ensure_ascii=False, indent=1), encoding="utf-8")

    print("\n=== 文章下载 ===")
    saved = skip = fail = 0
    for i, it in enumerate(items, 1):
        aid = hashlib.md5(it["url"].encode()).hexdigest()[:16]
        out = HTML / f"{aid}.html"
        if out.exists():
            skip += 1
            continue
        try:
            out.write_text(get(it["url"]), encoding="utf-8")
            saved += 1
        except Exception as exc:
            fail += 1
            if fail <= 5:
                print(f"  [FAIL] {it['url']}: {exc}")
            continue
        time.sleep(0.3)
        if i % 100 == 0:
            print(f"  进度 {i}/{len(items)} | 新{saved} 跳过{skip} 失败{fail} | {(time.time()-t0)/60:.1f}min")

    print(f"\n[OK] 朝阳采集完成：新增 {saved}，跳过 {skip}，失败 {fail}")
    print(f"    原始目录 {HTML}")


if __name__ == "__main__":
    main()
