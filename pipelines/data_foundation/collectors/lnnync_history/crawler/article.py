"""文章正文下载与原始证据备份。

对每一篇文章：
    GET URL → 校验 HTTP 状态 → 保存原始 HTML → 提取正文文本 → 追加 articles.jsonl

原始 HTML 永久保存在 data/raw/html/{article_id}.html，并计算 SHA256。
这样即使官网日后改版或删除文章，仍可从本地 HTML 完整重建结构化数据（验收标准 F）。
"""
from __future__ import annotations

import csv
import hashlib
import json
import re
from dataclasses import dataclass, asdict
from datetime import datetime
from pathlib import Path

from bs4 import BeautifulSoup

from . import PROJECT_ROOT, get_logger
from .client import FetchError, HttpClient

log = get_logger("crawler.article")

RAW_HTML_DIR = PROJECT_ROOT / "data" / "raw" / "html"
ARTICLES_JSONL = PROJECT_ROOT / "data" / "raw" / "articles.jsonl"
INDEX_PATH = PROJECT_ROOT / "data" / "intermediate" / "article_index.csv"

CONTENT_SELECTORS = [
    "div.TRS_Editor",
    "div.TRS_UEDITOR",
    "div#pages_content",
    "div.pages_content",
    "div.nr",
    "div.article-content",
    "div.content",
]
TITLE_SELECTORS = ["h1", "div.artical-title", "p.dt_title", "title"]

DATE_META_NAMES = ["PubDate", "publishdate", "PublishDate", "pubdate", "createdate", "ArticleCreateDate"]
DATE_TEXT_RE = re.compile(r"(20\d{2})[-/年.](\d{1,2})[-/月.](\d{1,2})")


@dataclass
class ArticleRecord:
    article_id: str
    category: str
    category_key: str
    title: str
    publication_date: str
    url: str
    html_path: str
    raw_text: str
    fetched_at: str
    http_status: int
    content_hash: str


def article_id_from_url(url: str) -> str:
    """取 URL 末段目录名作为稳定 article_id（早期为十六进制串，近期为数字时间戳）。"""
    parts = [p for p in url.split("?")[0].split("/") if p]
    return parts[-2] if len(parts) >= 2 and parts[-1].startswith("index") else parts[-1]


def extract_content(html: str) -> tuple[str, str]:
    """返回 (title, raw_text)。正文容器按候选 selector 依次 fallback。"""
    soup = BeautifulSoup(html, "lxml")
    for tag in soup(["script", "style"]):
        tag.decompose()

    title = ""
    for sel in TITLE_SELECTORS:
        node = soup.select_one(sel)
        if node:
            t = re.sub(r"\s+", " ", node.get_text()).strip()
            if t:
                title = t
                break

    body = None
    for sel in CONTENT_SELECTORS:
        node = soup.select_one(sel)
        if node and len(node.get_text(strip=True)) > 30:
            body = node
            break
    if body is None:
        body = soup.body or soup

    # 段落级抽取：保留换行结构，便于后续按段解析
    texts = []
    for p in body.find_all(["p", "div", "li"], recursive=True):
        # 只取没有子块级元素的叶子段落，避免父 div 重复输出整篇
        if p.find(["p", "div", "li"], recursive=False):
            continue
        t = re.sub(r"\s+", " ", p.get_text()).replace("\u00a0", " ").strip()
        if t:
            texts.append(t)
    if not texts:
        texts = [re.sub(r"\s+", " ", body.get_text()).replace("\u00a0", " ").strip()]

    seen, raw_lines = set(), []
    for t in texts:
        if t not in seen:
            seen.add(t)
            raw_lines.append(t)
    return title, "\n".join(raw_lines)


def extract_publication_date(html: str, fallback: str = "") -> str:
    soup = BeautifulSoup(html, "lxml")
    for name in DATE_META_NAMES:
        node = soup.find("meta", attrs={"name": re.compile(f"^{name}$", re.I)})
        if node and node.get("content"):
            m = DATE_TEXT_RE.search(node["content"])
            if m:
                return f"{m.group(1)}-{int(m.group(2)):02d}-{int(m.group(3)):02d}"
    for node in soup.select("div.artical-info, span.date, div.info, div.source"):
        m = DATE_TEXT_RE.search(node.get_text())
        if m:
            return f"{m.group(1)}-{int(m.group(2)):02d}-{int(m.group(3)):02d}"
    return fallback


def load_fetched(path: Path = ARTICLES_JSONL) -> dict[str, dict]:
    """已下载文章索引 {article_id: record}，用于断点续跑与增量更新。"""
    if not path.exists():
        return {}
    out = {}
    with path.open("r", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                rec = json.loads(line)
            except json.JSONDecodeError:
                continue
            if rec.get("article_id"):
                out[rec["article_id"]] = rec
    return out


def fetch_article(
    client: HttpClient,
    url: str,
    category: str,
    category_key: str,
    list_date: str,
    list_title: str,
) -> ArticleRecord | None:
    """下载单篇文章并落盘。失败返回 None（不抛异常，避免中断整体采集）。"""
    aid = article_id_from_url(url)
    html_path = RAW_HTML_DIR / f"{aid}.html"

    try:
        res = client.get(url)
    except FetchError as exc:
        log.error("[FAIL] %s -> %s", url, exc.message)
        return None

    html = res.text
    RAW_HTML_DIR.mkdir(parents=True, exist_ok=True)
    html_path.write_text(html, encoding="utf-8")

    title, raw_text = extract_content(html)
    pub_date = extract_publication_date(html, fallback=list_date)
    rec = ArticleRecord(
        article_id=aid,
        category=category,
        category_key=category_key,
        title=title or list_title,
        publication_date=pub_date,
        url=url,
        html_path=str(html_path.relative_to(PROJECT_ROOT)),
        raw_text=raw_text,
        fetched_at=datetime.now().isoformat(timespec="seconds"),
        http_status=res.status,
        content_hash=hashlib.sha256(raw_text.encode("utf-8")).hexdigest(),
    )
    return rec


def append_articles(records: list[ArticleRecord], path: Path = ARTICLES_JSONL) -> None:
    """增量追加：同 article_id 只保留最新一条（先全量重写，保证幂等）。"""
    path.parent.mkdir(parents=True, exist_ok=True)
    existing = load_fetched(path)
    for rec in records:
        existing[rec.article_id] = asdict(rec)
    with path.open("w", encoding="utf-8") as fh:
        for rec in existing.values():
            fh.write(json.dumps(rec, ensure_ascii=False) + "\n")


def read_index(path: Path = INDEX_PATH) -> list[dict]:
    if not path.exists():
        return []
    with path.open("r", encoding="utf-8") as fh:
        return [r for r in csv.DictReader(fh) if r.get("url")]
