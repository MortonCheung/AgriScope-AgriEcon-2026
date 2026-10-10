"""农作物病虫害情报采集（手册第 15 节，P1）。

来源：辽宁省农业农村厅及其下属事业单位公开栏目（植保植检、农业技术推广）。
只保存原文与可确定性提取的字段；文章中只写「辽西北局部」这类区域描述时，
保存到 region_raw，**不自行映射到某个城市**。
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
RAW = ROOT / "data/raw" / "pests"
HTML = RAW / "html"
HTML.mkdir(parents=True, exist_ok=True)

CTX = ssl.create_default_context(); CTX.check_hostname = False; CTX.verify_mode = ssl.CERT_NONE
UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")

SOURCES = [
    ("辽宁省农业农村厅", "通知公告", "https://nync.ln.gov.cn/nync/index/tzgg/index.shtml"),
    ("辽宁省农业农村厅", "农业要闻", "https://nync.ln.gov.cn/nync/index/nyyw/index.shtml"),
    ("辽宁省农业农村厅", "图片新闻", "https://nync.ln.gov.cn/nync/index/tpxw/index.shtml"),
    ("辽宁省农业发展服务中心", "中心动态", "https://nync.ln.gov.cn/nync/index/lnsnyfzfwzx/zxdt/index.shtml"),
]

KEYWORDS = re.compile(
    r"病虫|虫害|病害|病疫|防治|植保|蝗虫|草地贪夜蛾|粘虫|玉米螟|稻瘟病|"
    r"锈病|蚜虫|红蜘蛛|棉铃虫|农产品质量安全|农药")

ITEM_RE = re.compile(r'<a[^>]*href="(/[^"]+/index\.shtml)"[^>]*>\s*<span>(.*?)</span>\s*<span>\[(.*?)\]</span>', re.S)
TITLE_ATTR = re.compile(r'<a[^>]*href="(/[^"]+/index\.shtml)"[^>]*title="([^"]{5,90})"')


def get(url: str, timeout: int = 40) -> str:
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=timeout, context=CTX) as r:
        raw = r.read()
    for enc in ("utf-8", "gb18030"):
        try:
            return raw.decode(enc)
        except UnicodeDecodeError:
            continue
    return raw.decode("utf-8", "replace")


def parse_items(html: str, base: str) -> list[tuple[str, str, str]]:
    out = []
    for href, title, d in ITEM_RE.findall(html):
        out.append((base + href, re.sub(r"<[^>]+>", "", title).strip(), d.strip()))
    if not out:
        for href, title in TITLE_ATTR.findall(html):
            out.append((base + href, title, ""))
    seen, u = set(), []
    for i in out:
        if i[0] not in seen:
            seen.add(i[0]); u.append(i)
    return u


def next_page(html: str, base: str) -> str | None:
    for m in re.finditer(r'<a[^>]*title="下一页"[^>]*tagname="([^"]+)"', html):
        return base + m.group(1)
    for m in re.finditer(r'<a[^>]*tagname="([^"]+)"[^>]*title="下一页"', html):
        return base + m.group(1)
    return None


def extract_text(html: str) -> str:
    b = re.sub(r"<(script|style)[^>]*>.*?</\1>", "", html, flags=re.S)
    b = re.sub(r"<[^>]+>", "\n", b)
    b = re.sub(r"&nbsp;|&#160;", " ", b)
    lines = [x.strip() for x in b.split("\n") if x.strip()]
    seen, o = set(), []
    for x in lines:
        if x not in seen:
            seen.add(x); o.append(x)
    return "\n".join(o)


def main() -> None:
    all_items = []
    for site, col, url in SOURCES:
        base = "https://" + url.split("//")[1].split("/")[0]
        cur, seen_pages, page = url, set(), 0
        while cur and cur not in seen_pages and page < 30:
            page += 1; seen_pages.add(cur)
            try:
                html = get(cur)
            except Exception as exc:
                print(f"  [FAIL] {cur}: {exc}")
                break
            items = parse_items(html, base)
            all_items += [{"url": u, "title": t, "list_date": d, "site": site, "column": col}
                          for u, t, d in items]
            print(f"  [{site}/{col}] 第{page}页 {len(items)} 条")
            nxt = next_page(html, base)
            if not nxt or nxt in seen_pages:
                break
            cur = nxt
            time.sleep(0.8)

    hit = [i for i in all_items if KEYWORDS.search(i["title"] or "")]
    print(f"\n列表合计 {len(all_items)}，命中病虫害关键词 {len(hit)}")

    saved = []
    for i, it in enumerate(hit, 1):
        aid = hashlib.md5(it["url"].encode()).hexdigest()[:16]
        out = HTML / f"{aid}.html"
        if out.exists():
            continue
        try:
            h = get(it["url"])
            out.write_text(h, encoding="utf-8")
            saved.append({**it, "article_id": aid, "html_path": str(out.relative_to(ROOT)),
                          "raw_text": extract_text(h)[:15000],
                          "fetched_at": datetime.now().isoformat(timespec="seconds")})
        except Exception as exc:
            print(f"  [FAIL] {it['url']}: {exc}")
        time.sleep(0.7)

    with (RAW / "pest_articles.jsonl").open("w", encoding="utf-8") as fh:
        for r in saved:
            fh.write(json.dumps(r, ensure_ascii=False) + "\n")
    print(f"[OK] 保存 {len(saved)} 篇病虫害相关文章")


if __name__ == "__main__":
    main()
