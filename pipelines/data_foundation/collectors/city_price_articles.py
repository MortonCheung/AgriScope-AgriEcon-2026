"""城市级价格信息文章采集（B 级：政府网站结构化程度较低的价格发布）。

已确认可用渠道：
  大连 · 市发展改革研究中心「农副产品价格」周报     col1437（www.dl.gov.cn）
  大连 · 市发展改革委「成品粮油市场运行情况」月报   col1699（pc.dl.gov.cn）
  （沈阳菜篮子平台另有独立日度 API，见 shenyang_price.py）

这些栏目以**叙述性文本**发布价格（如「粳米价格为每500克3.08元，环比持平」），
属质量等级 B 的数据：可追溯、可提取，但需文本解析，非结构化接口。

原文 HTML 原样落盘到 data/raw/prices/{city}_articles/，绝不修改。
"""
from __future__ import annotations

import hashlib
import json
import re
import ssl
import time
import urllib.request
from datetime import datetime
from pathlib import Path

ROOT = next(p for p in Path(__file__).resolve().parents if (p / "AgriScope").is_dir() and (p / "data").is_dir())

CTX = ssl.create_default_context(); CTX.check_hostname = False; CTX.verify_mode = ssl.CERT_NONE
UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")

SOURCES = [
    {"city": "大连", "name": "农副产品价格周报", "kind": "weekly",
     "list": "https://www.dl.gov.cn/col/col1437/index.html",
     "max_page": 30},
    {"city": "大连", "name": "成品粮油市场月度综述", "kind": "monthly",
     "list": "https://pc.dl.gov.cn/col/col1699/index.html",
     "max_page": 20},
]

ART_RE = re.compile(r'<a[^>]*href="([^"]*?/art/[^"]+\.html)"[^>]*>(.*?)</a>', re.S)
NEXT_RE = re.compile(r'<a[^>]*href="([^"]*index_\d+\.html)"[^>]*>\s*(?:下一页|下页)')


def get(url, timeout=30):
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=timeout, context=CTX) as r:
        raw = r.read()
    for enc in ("utf-8", "gb18030"):
        try:
            return raw.decode(enc)
        except UnicodeDecodeError:
            continue
    return raw.decode("utf-8", "replace")


def extract_text(html: str) -> str:
    b = re.sub(r"<(script|style)[^>]*>.*?</\1>", "", html, flags=re.S)
    b = re.sub(r"<[^>]+>", "\n", b)
    b = re.sub(r"&nbsp;|&#160;", " ", b)
    lines = [x.strip() for x in b.split("\n") if x.strip()]
    seen, out = set(), []
    for x in lines:
        if x not in seen:
            seen.add(x); out.append(x)
    return "\n".join(out)


def crawl(src: dict) -> list[dict]:
    city, name, kind = src["city"], src["name"], src["kind"]
    RAW = ROOT / "data/raw" / "prices" / f"{city}_articles"
    RAW.mkdir(parents=True, exist_ok=True)

    url = src["list"]
    seen_pages, arts = set(), []
    page = 0
    while url and url not in seen_pages and page < src["max_page"]:
        page += 1
        seen_pages.add(url)
        try:
            h = get(url)
        except Exception as exc:
            print(f"  [FAIL] 列表 {url}: {exc}")
            break
        for href, title in ART_RE.findall(h):
            t = re.sub(r"<[^>]+>", "", title).strip()
            if len(t) < 6:
                continue
            full = href if href.startswith("http") else (
                "https://" + url.split("/")[2] + ("" if href.startswith("/") else "/") + href)
            arts.append((full, t))
        m = NEXT_RE.search(h)
        url = m.group(1) if m else None
        time.sleep(0.6)

    seen, uniq = set(), []
    for u, t in arts:
        if u not in seen:
            seen.add(u); uniq.append((u, t))
    print(f"  [{city}/{name}] 列表 {len(uniq)} 篇")

    saved = []
    for u, t in uniq:
        aid = hashlib.md5(u.encode()).hexdigest()[:16]
        out = RAW / f"{aid}.html"
        if not out.exists():
            try:
                h = get(u)
                out.write_text(h, encoding="utf-8")
            except Exception as exc:
                print(f"    [FAIL] {u}: {exc}")
                continue
            time.sleep(0.6)
        txt = extract_text(out.read_text(encoding="utf-8"))
        dm = re.search(r"/(20\d\d)/(\d{1,2})/", u)
        saved.append({
            "city": city, "source_name": name, "source_kind": kind,
            "article_id": aid, "title": t, "url": u,
            "publish_month": f"{dm.group(1)}-{int(dm.group(2)):02d}" if dm else None,
            "raw_file": str(out.relative_to(ROOT)),
            "raw_text": txt[:12000],
            "fetched_at": datetime.now().isoformat(timespec="seconds"),
        })
    return saved


def main() -> None:
    all_rows = []
    for src in SOURCES:
        rows = crawl(src)
        all_rows += rows
    for city in {r["city"] for r in all_rows}:
        sub = [r for r in all_rows if r["city"] == city]
        out = ROOT / "data/raw" / "prices" / f"{city}_articles" / "articles.jsonl"
        with out.open("w", encoding="utf-8") as fh:
            for r in sub:
                fh.write(json.dumps(r, ensure_ascii=False) + "\n")
        print(f"[OK] {city} 文章 {len(sub)} 篇 -> {out.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
