"""分类列表分页遍历 → data/intermediate/article_index.csv

实测结论（2026-09 站点探查，非推测）：
1. 列表条目形如
       <li><a href="/nync/index/zwgk/zszdgz/ncpxx/<cat>/<ARTICLE_ID>/index.shtml" target="_blank">
           <span>标题</span><span>[2026-09-17]</span></a></li>
   其中 ARTICLE_ID 早期文章是大写十六进制串，近期是数字时间戳 —— 因此不按 ID 形态推算文章。
2. 分页为 JS 驱动：`<a ... title="下一页" tagname="/…/<uid>-2.shtml">下一页</a>`，
   分页链接没有 href，真实目标 URL 在 tagname / onclick 中。
3. 已实测该 tagname URL 可直接 HTTP GET 返回 200 与对应页内容，无需浏览器自动化。
4. 页码超限（如农资第 16 页）会落到另一个模块并报出不同总页数 —— 故严格按「下一页」跟随 + 总页数上限。
"""
from __future__ import annotations

import csv
import re
import time
from dataclasses import dataclass, asdict
from datetime import datetime
from pathlib import Path
from typing import Iterable

from bs4 import BeautifulSoup

from . import PROJECT_ROOT, get_logger
from .client import FetchError, HttpClient

log = get_logger("crawler.listing")

INDEX_PATH = PROJECT_ROOT / "data" / "intermediate" / "article_index.csv"
FIELDS = ["category", "category_key", "title", "list_date", "url", "discovered_at", "status"]

# 列表条目 href 形态（分类 slug 与文章 ID 均不限制字符集）
ITEM_HREF_RE = re.compile(r"/nync/index/zwgk/zszdgz/ncpxx/([^/]+)/([^/]+)/index\.shtml")
TOTAL_PAGE_RE = re.compile(r"共(\d+)页")
# 分页 URL：/<cat-path>/<module_uid>-<n>.shtml
PAGE_URL_RE = re.compile(r"(/nync/index/zwgk/zszdgz/ncpxx/[^/]+/[0-9a-fA-F]+)-(\d+)\.shtml")


@dataclass
class ArticleRef:
    category: str
    category_key: str
    title: str
    list_date: str
    url: str
    discovered_at: str
    status: str = "pending"


def _clean(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "").replace("\u00a0", " ")).strip()


def parse_listing(html: str, category: str, category_key: str, base_url: str) -> list[ArticleRef]:
    """从列表页 HTML 中解析文章条目。先用 DOM（bs4），失败时回退到正则。"""
    soup = BeautifulSoup(html, "lxml")
    out: list[ArticleRef] = []
    now = datetime.now().isoformat(timespec="seconds")

    for a in soup.find_all("a", href=True):
        href = a["href"]
        m = ITEM_HREF_RE.search(href)
        if not m:
            continue
        spans = a.find_all("span")
        if len(spans) >= 2:
            title = _clean(spans[0].get_text())
            date_raw = _clean(spans[1].get_text())
        else:  # 结构异常时的兜底
            title = _clean(a.get_text())
            date_raw = ""
        list_date = ""
        dm = re.search(r"(\d{4})-(\d{2})-(\d{2})", date_raw)
        if dm:
            list_date = f"{dm.group(1)}-{dm.group(2)}-{dm.group(3)}"
        url = href if href.startswith("http") else base_url + href
        out.append(
            ArticleRef(
                category=category,
                category_key=category_key,
                title=title,
                list_date=list_date,
                url=url,
                discovered_at=now,
            )
        )

    if not out:  # DOM 解析失败 → 正则兜底，并记日志
        log.warning("[%s] DOM 解析列表失败，回退正则", category)
        for href, title, date_raw in re.findall(
            r'<li><a href="(/nync/index/zwgk/zszdgz/ncpxx/[^"]+/index\.shtml)"[^>]*>\s*'
            r"<span>(.*?)</span>\s*<span>\[(.*?)\]</span>",
            html,
            re.S,
        ):
            dm = re.search(r"(\d{4})-(\d{2})-(\d{2})", _clean(date_raw))
            out.append(
                ArticleRef(
                    category=category,
                    category_key=category_key,
                    title=_clean(re.sub(r"<[^>]+>", "", title)),
                    list_date=f"{dm.group(1)}-{dm.group(2)}-{dm.group(3)}" if dm else "",
                    url=href if href.startswith("http") else base_url + href,
                    discovered_at=now,
                )
            )
    return out


def find_next_page(html: str) -> str | None:
    """从 DOM 中解析「下一页」的真实目标 URL（tagname 属性 / onclick 参数）。"""
    soup = BeautifulSoup(html, "lxml")
    for a in soup.find_all("a"):
        title = (a.get("title") or "").strip()
        text = _clean(a.get_text())
        if title == "下一页" or text == "下一页":
            for key in ("tagname", "onclick"):
                val = a.get(key) or ""
                m = PAGE_URL_RE.search(val)
                if m:
                    return m.group(0)
    return None


def find_total_pages(html: str) -> int | None:
    m = TOTAL_PAGE_RE.search(html)
    return int(m.group(1)) if m else None


def discover_category(
    client: HttpClient,
    category_key: str,
    category: str,
    path: str,
    base_url: str,
    known_urls: set[str] | None = None,
    incremental: bool = False,
) -> list[ArticleRef]:
    """遍历单个分类的全部历史分页。"""
    known_urls = known_urls or set()
    start_url = base_url + path
    refs: list[ArticleRef] = []
    seen_pages: set[str] = set()
    seen_articles: set[str] = set()

    page_url: str | None = start_url
    page_no = 0
    total_pages: int | None = None
    consecutive_known_pages = 0

    while page_url and page_url not in seen_pages:
        page_no += 1
        seen_pages.add(page_url)
        try:
            res = client.get(page_url)
        except FetchError as exc:
            log.error("[%s] 列表页抓取失败，停止本分类：%s (%s)", category, page_url, exc.message)
            break

        html = res.text
        if total_pages is None:
            total_pages = find_total_pages(html)
            log.info("[%s] 发现第 1 页，共 %s 页", category, total_pages or "?")

        items = parse_listing(html, category, category_key, base_url)
        new_in_page = 0
        for ref in items:
            if ref.url in seen_articles:
                continue
            seen_articles.add(ref.url)
            refs.append(ref)
            if ref.url not in known_urls:
                new_in_page += 1
        log.info(
            "[%s] 第 %d 页：条目 %d（新增 %d），累计 %d 篇",
            category, page_no, len(items), new_in_page, len(refs),
        )

        # 增量模式：整页都是已知文章 → 说明已追平历史，可提前收工
        if incremental and items:
            if new_in_page == 0:
                consecutive_known_pages += 1
                if consecutive_known_pages >= 2:
                    log.info("[%s] 连续 2 页无新增，增量到达历史边界，停止遍历", category)
                    break
            else:
                consecutive_known_pages = 0

        next_url = find_next_page(html)
        if not next_url:
            log.info("[%s] 没有下一页，遍历结束（%d 页）", category, page_no)
            break
        if next_url in seen_pages:
            log.info("[%s] 下一页已访问，遍历结束（%d 页）", category, page_no)
            break
        if total_pages and page_no >= total_pages:
            log.info("[%s] 已到达尾页 %d/%d，遍历结束", category, page_no, total_pages)
            break

        page_url = next_url if next_url.startswith("http") else base_url + next_url
        time.sleep(0)

    return refs


def load_known_urls(path: Path = INDEX_PATH) -> set[str]:
    if not path.exists():
        return set()
    with path.open("r", encoding="utf-8") as fh:
        return {row["url"] for row in csv.DictReader(fh) if row.get("url")}


def write_index(rows: list[ArticleRef], path: Path = INDEX_PATH) -> None:
    """写入索引：URL 去重，已存在的记录保留原 discovered_at，新记录追加。"""
    path.parent.mkdir(parents=True, exist_ok=True)
    existing: dict[str, dict] = {}
    if path.exists():
        with path.open("r", encoding="utf-8") as fh:
            for row in csv.DictReader(fh):
                if row.get("url"):
                    existing[row["url"]] = row

    for ref in rows:
        d = asdict(ref)
        if ref.url in existing:
            # 保留首次发现时间，仅刷新标题/日期
            d["discovered_at"] = existing[ref.url].get("discovered_at", d["discovered_at"])
            d["status"] = existing[ref.url].get("status", "pending")
        existing[ref.url] = d

    ordered = sorted(existing.values(), key=lambda r: (r["category_key"], r.get("list_date", ""), r["url"]))
    with path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=FIELDS, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(ordered)
    log.info("索引已写入：%s（%d 条，URL 唯一）", path, len(ordered))
