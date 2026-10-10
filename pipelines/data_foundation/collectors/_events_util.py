"""四类非价格事件采集共用工具。

覆盖：成交量/供应量、县域物候、官方灾害事件、政策事件。
约定：原始 HTML 一律落盘 data/raw/；禁止编造；受限一律记 ACCESS_RESTRICTED 并保留证据。
"""
from __future__ import annotations

import hashlib
import re
import ssl
import time
import urllib.parse
import urllib.request
from datetime import datetime
from pathlib import Path

ROOT = next(p for p in Path(__file__).resolve().parents if (p / "AgriScope").is_dir() and (p / "data").is_dir())

CTX = ssl.create_default_context()
CTX.check_hostname = False
CTX.verify_mode = ssl.CERT_NONE

UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")

DL_GOV_COLUMNS = {
    "1190": "民生热点",
    "1437": "生活定居.百姓日常",
    "1932": "商务动态",
}

LN_CITIES = ("沈阳", "大连", "鞍山", "抚顺", "本溪", "丹东", "锦州", "营口",
             "阜新", "辽阳", "盘锦", "铁岭", "朝阳", "葫芦岛")
_CITY_TAG = re.compile(r"^\s*[\[【](" + "|".join(LN_CITIES) + r")[\]】]")


def city_from_tag(title: str) -> str:
    """省农业农村厅「全省/各市农业信息联播」标题形如 [丹东]…，取市级标签。"""
    m = _CITY_TAG.search(title or "")
    return m.group(1) if m else ""


def get(url: str, timeout: int = 40, referer: str | None = None, retries: int = 4) -> str:
    headers = {"User-Agent": UA, "Accept-Language": "zh-CN,zh;q=0.9"}
    if referer:
        headers["Referer"] = referer
    last = None
    for attempt in range(retries):
        req = urllib.request.Request(url, headers=headers)
        try:
            with urllib.request.urlopen(req, timeout=timeout, context=CTX) as r:
                raw = r.read()
            break
        except Exception as exc:  # 瞬时 TLS EOF / 超时较多，退避重试
            last = exc
            time.sleep(1.2 * (attempt + 1))
    else:
        raise last  # type: ignore[misc]
    for enc in ("utf-8", "gb18030", "gbk"):
        try:
            return raw.decode(enc)
        except UnicodeDecodeError:
            continue
    return raw.decode("utf-8", errors="replace")


def text_of(html: str) -> str:
    b = re.sub(r"<(script|style)[^>]*>.*?</\1>", "", html, flags=re.S)
    b = re.sub(r"<!--.*?-->", "", b, flags=re.S)
    b = re.sub(r"<br\s*/?>|</p>|</div>|</tr>|</li>", "\n", b, flags=re.I)
    b = re.sub(r"<[^>]+>", " ", b)
    b = b.replace("&nbsp;", " ").replace("&#160;", " ").replace("&amp;", "&")
    b = re.sub(r"[ \t\u3000]+", " ", b)
    lines = [ln.strip() for ln in b.split("\n")]
    return "\n".join(ln for ln in lines if ln)


def article_body(text: str) -> str:
    """剥离站点导航/面包屑，只留正文。

    省级/市级判定绝不能读到导航里的“全省”“辽宁省农业农村厅”等噪声，
    否则会把市级灾情/农情误判成省级口径。以常见正文起始标记切分。
    """
    text = text or ""
    for mk in ("【字体", "字体："):
        i = text.rfind(mk)
        if i > 0:
            j = text.find("\n", i)
            if j > 0:
                return text[j + 1:]
    i = text.rfind("发布时间：")
    if i > 0:
        j = text.find("\n", i)
        if j > 0:
            return text[j + 1:]
    return text


def save_raw(html: str, topic: str, key: str) -> str:
    out_dir = ROOT / "data/raw" / topic
    out_dir.mkdir(parents=True, exist_ok=True)
    aid = hashlib.md5(key.encode()).hexdigest()[:16]
    out = out_dir / f"{aid}.html"
    if not out.exists():
        out.write_text(html, encoding="utf-8")
    return str(out.relative_to(ROOT))


def fetch_article(url: str, topic: str) -> tuple[str, str]:
    rel = f"data/raw/{topic}/{hashlib.md5(url.encode()).hexdigest()[:16]}.html"
    cached = ROOT / rel
    if cached.exists():
        return text_of(cached.read_text(encoding="utf-8")), rel
    html = get(url, referer=url)
    rel = save_raw(html, topic, url)
    return text_of(html), rel


def dl_gov_list(columnid: str, max_pages: int = 40) -> list[dict]:
    """大连政务站（huilan CMS）列表：先解析 unitid，再走 dataproxy.jsp 分页。"""
    page_url = f"https://www.dl.gov.cn/col/col{columnid}/index.html"
    try:
        html = get(page_url)
    except Exception as exc:
        print(f"  [FAIL] 列表页 {page_url}: {exc}")
        return []
    m = re.search(r"param_\d+\s*=\s*\{[^}]*unitid:'(\d+)'", html)
    if not m:
        return []
    unitid = m.group(1)
    total = re.search(r"totalRecord:(\d+)", html)
    total = int(total.group(1)) if total else 0
    out, seen = [], set()
    per = 15
    page = 0
    while page * per < min(total or max_pages * per, max_pages * per):
        page += 1
        start = (page - 1) * per + 1
        end = page * per
        api = ("https://www.dl.gov.cn/module/web/jpage/dataproxy.jsp?"
               "col=1&webid=1&path=https%3A%2F%2Fwww.dl.gov.cn%2F"
               f"&columnid={columnid}&sourceContentType=1&unitid={unitid}"
               f"&webname=x&permissiontype=0&startrecord={start}&endrecord={end}&perpage={per}")
        try:
            ds = get(api)
        except Exception as exc:
            print(f"  [FAIL] 分页 {start}-{end}: {exc}")
            break
        recs = re.findall(r"<record><!\[CDATA\[(.*?)\]\]></record>", ds, re.S)
        if not recs:
            break
        for rec in recs:
            u = re.search(r'href="([^"]+\.html)"', rec)
            t = re.search(r'class="desc">\s*(.*?)\s*</div>', rec, re.S)
            d = re.search(r"\[(\d{4}-\d{2}-\d{2})\]", rec)
            if not u:
                continue
            url = u.group(1)
            if url in seen:
                continue
            seen.add(url)
            out.append({"url": url,
                        "title": re.sub(r"\s+", " ", t.group(1)).strip() if t else "",
                        "date": d.group(1) if d else "",
                        "column": DL_GOV_COLUMNS.get(columnid, columnid)})
        print(f"    列表页 {page} 累计 {len(out)}")
        time.sleep(0.3)
    return out


def ln_gov_list(url: str, max_pages: int = 12) -> list[dict]:
    """辽宁省政府/厅局（huilan CMS）静态列表：条目在 li>a 中，分页在 tagname。"""
    base = "{0.scheme}://{0.netloc}".format(urllib.parse.urlparse(url))
    out, seen, cur = [], set(), url
    for _ in range(max_pages):
        try:
            html = get(cur)
        except Exception as exc:
            print(f"  [FAIL] 列表 {cur}: {exc}")
            break
        items = re.findall(
            r'<a[^>]*href="([^"]+)"[^>]*title="([^"]{5,90})"', html)
        items += [(h, t) for h, t in re.findall(
            r'<a[^>]*href="([^"]+)"[^>]*>\s*([^<>]{6,90})\s*</a>', html)]
        for href, title in items:
            if not href.endswith(".shtml") or "/index/" not in href:
                continue
            full = href if href.startswith("http") else base + href
            if full in seen:
                continue
            seen.add(full)
            out.append({"url": full, "title": re.sub(r"\s+", " ", title).strip()})
        m = re.search(r'title="下一页"[^>]*tagname="([^"]+)"', html) or \
            re.search(r'tagname="([^"]+)"[^>]*title="下一页"', html)
        if not m:
            break
        cur = base + m.group(1)
        time.sleep(0.4)
    return out


def write_csv(path: Path, fieldnames: list[str], rows: list[dict]) -> None:
    import csv
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=fieldnames)
        w.writeheader()
        for r in rows:
            w.writerow({k: r.get(k, "") for k in fieldnames})


def now() -> str:
    return datetime.now().isoformat(timespec="seconds")


def domain(url: str) -> str:
    return urllib.parse.urlparse(url).netloc


DATE_IN_URL = re.compile(r"/(\d{4})(\d{2})(\d{2})\d{6,}/")
DATE_IN_PATH = re.compile(r"/(\d{4})(\d{2})/")
DATE_ANY = re.compile(r"(20\d{2})\s*[-/年.]\s*(\d{1,2})\s*[-/月.]\s*(\d{1,2})")


def _norm_date(y, m, d) -> str:
    try:
        return f"{int(y):04d}-{int(m):02d}-{int(d):02d}"
    except Exception:
        return ""


def date_from_url(url: str) -> str:
    m = DATE_IN_URL.search(url)
    if m:
        return _norm_date(*m.groups())
    m = DATE_IN_PATH.search(url)
    if m:
        return _norm_date(m.group(1), m.group(2), 1)
    return ""


def date_from_text(s: str) -> str:
    m = DATE_ANY.search(s or "")
    if m:
        return _norm_date(*m.groups())
    m = re.search(r"(\d{4})/(\d{1,2})/(\d{1,2})", s or "")
    if m:
        return _norm_date(*m.groups())
    return ""


def _next_page(html: str, base: str, cur: str) -> str | None:
    for pat in (r'title="下一页"[^>]*tagname="([^"]+)"',
                r'tagname="([^"]+)"[^>]*title="下一页"'):
        m = re.search(pat, html)
        if m:
            v = m.group(1)
            if v.startswith("["):
                return None
            return v if v.startswith("http") else base + v
    m = re.search(r'href="([^"]*glist_(\d+)\.html)"', html)
    m2 = re.search(r"glist_(?:(\d+))\.html", cur)
    cp = int(m2.group(1)) if m2 else 1
    if m:
        return base + m.group(1) if m.group(1).startswith("/") else m.group(1)
    return None


def harvest_list(url: str, max_pages: int = 30, sleep: float = 0.4) -> list[dict]:
    """通用栏目列表抓取：兼容 huilan(index.shtml)+tagname 与 glist.html/.htm 列表。"""
    p = urllib.parse.urlparse(url)
    base = f"{p.scheme}://{p.netloc}"
    dirpath = p.path.rsplit("/", 1)[0] + "/"
    out, seen, cur = [], set(), url
    for _ in range(max_pages):
        try:
            html = get(cur)
        except Exception as exc:
            print(f"  [ACCESS_RESTRICTED] 列表 {cur}: {exc}")
            break
        found = []
        for href, inner, tail in re.findall(
                r'<li[^>]*>\s*<a[^>]*href="([^"]+)"[^>]*>(.*?)</a>(.*?)</li>', html, re.S):
            t = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", "", inner)).strip()
            if len(t) < 4:
                continue
            found.append((href, t, date_from_text(tail) or date_from_text(t)))
        for href, inner in re.findall(r'<a[^>]*href="([^"]+)"[^>]*>(.*?)</a>', html, re.S):
            if "javascript" in href:
                continue
            t = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", "", inner)).strip()
            if len(t) < 6:
                continue
            found.append((href, t, date_from_text(t) or date_from_url(href)))
        for href, t, d in found:
            full = urllib.parse.urljoin(cur if cur.endswith("/") else cur, href) \
                if not href.startswith("http") else href
            if full in seen:
                continue
            seen.add(full)
            out.append({"url": full, "title": t, "date": d or date_from_url(full)})
        nxt = _next_page(html, base, cur)
        if not nxt or nxt in seen or nxt == cur:
            break
        cur = nxt
        time.sleep(sleep)
    return out


def harvest_topic(columns: list[dict], keywords: str, max_pages: int = 30,
                  title_filter: bool = True) -> tuple[list[dict], list[dict]]:
    """遍历栏目抓列表，按关键词过滤标题。返回 (命中条目, 全部条目)。"""
    kw = re.compile(keywords)
    hits, allitems = [], []
    for col in columns:
        print(f"[列表] {col.get('name', '')} {col['url']}")
        try:
            items = harvest_list(col["url"], max_pages=max_pages)
        except Exception as exc:
            print(f"  [ACCESS_RESTRICTED] {col['url']}: {exc}")
            continue
        print(f"  -> {len(items)} 条")
        for it in items:
            it["column"] = col.get("name", "")
            it["site"] = col.get("site", "")
            allitems.append(it)
            if not title_filter or kw.search(it["title"] or ""):
                hits.append(it)
    return hits, allitems


def run_curated(sources: list[dict], topic: str, extractor) -> list[dict]:
    """抓取策展 URL 列表：逐条落盘原始 HTML，交给 extractor(text, src) 产出记录。"""
    rows, log = [], []
    for src in sources:
        try:
            text, rel = fetch_article(src["url"], topic)
        except Exception as exc:
            print(f"  [ACCESS_RESTRICTED] {src['url']}: {exc}")
            log.append({**src, "status": "ACCESS_RESTRICTED", "error": str(exc)})
            continue
        got = extractor(text, {**src, "raw_file": rel}) or []
        for g in got:
            g.setdefault("source_url", src["url"])
            g.setdefault("raw_file", rel)
        rows.extend(got)
        log.append({**src, "status": "ok", "n": len(got)})
        print(f"  [ok] {src.get('tag', src['url'])} -> {len(got)} 条")
        time.sleep(0.5)
    return rows
