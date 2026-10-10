"""极端天气与农业灾情公开信息采集（数据源 D / E）。

来源（全部为政府公开网站）：
  辽宁省水利厅  汛情快报 / 监测预警 / 防汛动态
  辽宁省农业农村厅  农业要闻（含防灾减灾、抗灾、排涝）
  辽宁省政府    灾情 / 应急相关

只保存原始 HTML 与正文文本，事件结构化留到 parsers/disaster_parser.py 做，
确保原始证据完整、可追溯。
"""
from __future__ import annotations

import hashlib
import json
import re
import ssl
import time
import urllib.parse
import urllib.request
from datetime import datetime
from pathlib import Path

ROOT = next(p for p in Path(__file__).resolve().parents if (p / "AgriScope").is_dir() and (p / "data").is_dir())
RAW = ROOT / "data/raw" / "disaster_reports"
HTML_DIR = RAW / "html"
HTML_DIR.mkdir(parents=True, exist_ok=True)

CTX = ssl.create_default_context()
CTX.check_hostname = False
CTX.verify_mode = ssl.CERT_NONE
UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")

SOURCES = [
    {"site": "辽宁省水利厅", "name": "汛情快报", "url": "https://slt.ln.gov.cn/slt/xwzx/fxdt/xqkb/index.shtml"},
    {"site": "辽宁省水利厅", "name": "监测预警", "url": "https://slt.ln.gov.cn/slt/xwzx/fxdt/jcyj/index.shtml"},
    {"site": "辽宁省水利厅", "name": "防汛动态", "url": "https://slt.ln.gov.cn/slt/xwzx/fxdt/index.shtml"},
    {"site": "辽宁省农业农村厅", "name": "农业要闻", "url": "https://nync.ln.gov.cn/nync/index/nyyw/index.shtml"},
    {"site": "辽宁省农业农村厅", "name": "通知公告", "url": "https://nync.ln.gov.cn/nync/index/tzgg/index.shtml"},
    {"site": "辽宁省水利厅", "name": "水利要闻", "url": "https://slt.ln.gov.cn/slt/xwzx/slyw/index.shtml"},
    {"site": "辽宁省水利厅", "name": "水旱灾害防御", "url": "https://slt.ln.gov.cn/slt/xwzx/slyw/shzhfycswc/index.shtml"},
]

ITEM_RE = re.compile(
    r'<li><a href="(/[^"]+/index\.shtml)"[^>]*>\s*<span>(.*?)</span>\s*<span>\[(.*?)\]</span>', re.S)
TOTAL_RE = re.compile(r"共(\d+)页")
PAGE_URL_RE = re.compile(r"(/[a-z]+/[a-z]+/[a-z]+/[a-z0-9]+/[a-z0-9]+/[0-9a-fA-F]+-\d+\.shtml)")
TITLE_RE = re.compile(r"title=\"([^\"]{5,90})\"")

# 仅保留与天气/灾害相关的文章（避免抓成新闻全集）
KEYWORDS = re.compile(
    r"暴雨|洪涝|洪水|汛情|台风|干旱|旱情|冰雹|大风|寒潮|低温|霜冻|雪灾|"
    r"受灾|成灾|绝收|灾情|抗灾|减灾|救灾|排涝|农田积水|农业损失|农作物受灾|"
    r"强降雨|强对流|预警|应急响应")


def get(url: str, timeout: int = 40) -> str:
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=timeout, context=CTX) as r:
        raw = r.read()
    for enc in ("utf-8", "gb18030"):
        try:
            return raw.decode(enc)
        except UnicodeDecodeError:
            continue
    return raw.decode("utf-8", errors="replace")


def parse_listing(html: str, base: str) -> list[tuple[str, str, str]]:
    out = []
    for href, title, date_raw in ITEM_RE.findall(html):
        title = re.sub(r"<[^>]+>", "", title).strip()
        dm = re.search(r"(\d{4})-(\d{1,2})-(\d{1,2})", date_raw)
        url = href if href.startswith("http") else base + href
        out.append((url, title, dm.group(0) if dm else ""))
    if not out:  # 备选结构：title 属性
        for href, title in re.findall(r'<a[^>]*href="(/[^"]+/index\.shtml)"[^>]*title="([^"]{5,90})"', html):
            out.append((base + href, title, ""))
    seen, uniq = set(), []
    for u, t, d in out:
        if u not in seen:
            seen.add(u)
            uniq.append((u, t, d))
    return uniq


def next_page(html: str, base: str) -> str | None:
    """分页 URL 在 tagname / onclick 中（JS 驱动）。

    必须排除 title="首页"/"上一页"/"尾页" 的 tagname，否则会取回上一页导致死循环或提前结束。
    """
    for m in re.finditer(r'<a[^>]*title="下一页"[^>]*tagname="(/[^"]+)"', html):
        return base + m.group(1)
    for m in re.finditer(r'<a[^>]*tagname="(/[^"]+)"[^>]*title="下一页"', html):
        return base + m.group(1)
    for m in re.finditer(r'tagname="(/[^"]*?-\d+\.shtml)"', html):
        return base + m.group(1)
    m = PAGE_URL_RE.search(html)
    return base + m.group(0) if m else None


def extract_text(html: str) -> str:
    import re as _re
    body = _re.sub(r"<(script|style)[^>]*>.*?</\1>", "", html, flags=_re.S)
    body = _re.sub(r"<[^>]+>", "\n", body)
    body = _re.sub(r"&nbsp;|&#160;", " ", body)
    lines = [l.strip() for l in body.split("\n") if l.strip()]
    seen, out = set(), []
    for l in lines:
        if l not in seen:
            seen.add(l)
            out.append(l)
    return "\n".join(out)


def crawl_source(src: dict) -> list[dict]:
    base = urllib.parse.urlparse(src["url"]).scheme + "://" + urllib.parse.urlparse(src["url"]).netloc
    url = src["url"]
    seen_pages, items, page_no = set(), [], 0
    while url and url not in seen_pages and page_no < 60:
        page_no += 1
        seen_pages.add(url)
        try:
            html = get(url)
        except Exception as exc:
            print(f"    [FAIL] 列表 {url}: {exc}")
            break
        found = parse_listing(html, base)
        items.extend(found)
        print(f"    第{page_no}页 条目 {len(found)} 累计 {len(items)}")
        nxt = next_page(html, base)
        if not nxt or nxt in seen_pages:
            break
        url = nxt
        time.sleep(1.0)
    return [{"url": u, "title": t, "list_date": d,
             "site": src["site"], "column": src["name"]} for u, t, d in items]


def main() -> None:
    all_items = []
    for src in SOURCES:
        print(f"[{src['site']} / {src['name']}]")
        items = crawl_source(src)
        print(f"  -> {len(items)} 条")
        all_items.extend(items)

    # 关键词过滤（只保留灾害相关）
    filtered = [i for i in all_items if KEYWORDS.search(i["title"] or "")]
    print(f"\n列表合计 {len(all_items)}，命中灾害关键词 {len(filtered)}")

    saved = []
    for i, it in enumerate(filtered, 1):
        aid = hashlib.md5(it["url"].encode()).hexdigest()[:16]
        out = HTML_DIR / f"{aid}.html"
        if out.exists():
            continue
        try:
            html = get(it["url"])
            out.write_text(html, encoding="utf-8")
            text = extract_text(html)
            saved.append({**it, "article_id": aid,
                          "html_path": str(out.relative_to(ROOT)),
                          "raw_text": text[:20000],
                          "fetched_at": datetime.now().isoformat(timespec="seconds")})
            if i % 20 == 0:
                print(f"  已保存 {len(saved)}/{len(filtered)}")
        except Exception as exc:
            print(f"  [FAIL] {it['url']}: {exc}")
        time.sleep(0.8)

    with (RAW / "disaster_articles.jsonl").open("w", encoding="utf-8") as fh:
        for r in saved:
            fh.write(json.dumps(r, ensure_ascii=False) + "\n")
    print(f"[OK] 保存 {len(saved)} 篇灾害相关文章 -> data/raw/disaster_reports/")


if __name__ == "__main__":
    main()
