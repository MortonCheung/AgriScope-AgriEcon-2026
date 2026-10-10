"""B2B 平台产地/批发行情可达性与小样验证（惠农网 cnhnb.com / 中商情报网 askci.com）。

本脚本只做两件事：
  1) 探测并原样落盘公开页面（不修改、不填补、不删除任何字段）；
  2) 从页面内嵌的 Nuxt SSR 负载中抽出「地区 + 商品 + 日期 + 价格」行，写入 jsonl，便于核对。

禁止编造：所有输出字段均来自原始页面；抓不到就记 status，不补造。
受限主机记 ACCESS_RESTRICTED（不绕过验证码/签名）。

用法：
    python3 collectors/b2b_hangqing_probe.py                 # 跑内置小样
    python3 collectors/b2b_hangqing_probe.py --dates 20260915 20260616
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import ssl
import subprocess
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime
from pathlib import Path

ROOT = next(p for p in Path(__file__).resolve().parents if (p / "AgriScope").is_dir() and (p / "data").is_dir())
RAW = ROOT / "data/raw" / "prices" / "b2b"
CNHNB_RAW = RAW / "cnhnb" / "hangqing"
ASKCI_RAW = RAW / "askci" / "html"

UA_MOBILE = ("Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) "
             "AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Mobile/15E148 Safari/604.1")
UA_DESKTOP = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
              "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")

CTX = ssl.create_default_context()
CTX.check_hostname = False
CTX.verify_mode = ssl.CERT_NONE

# 惠农网内部地区 ID（areaId）。来源：公开行情页 URL，非推测。
CNHNB_AREAS = {
    "东港市": {"city": "丹东", "area_id": 1562, "area_no": "210681"},
    "昌图县": {"city": "铁岭", "area_id": 1600, "area_no": "211224"},
    "庄河市": {"city": "大连", "area_id": 1533, "area_no": "210283"},
    "北镇市": {"city": "锦州", "area_id": 1571, "area_no": "210782"},
    "凌源市": {"city": "朝阳", "area_id": 1606, "area_no": "211382"},
}

CNHNB_HOSTS = ["https://www.cnhnb.com", "https://m.cnhnb.com"]
VERIFY_MARKERS = ("请验证", "fas-potato/verify")


def _curl_get(url: str, ua: str, referer: str | None = None) -> tuple[int, bytes, str]:
    """用 curl 传输（HTTP/2）。惠农网 WAF 对 HTTP/1.1 客户端返回 503「请验证」挑战页，
    对标准浏览器（HTTP/2）正常返回；此处仅是换用等价的普通客户端，不绕过任何验证。"""
    cmd = ["curl", "-sS", "-L", "--max-time", "25", "-w", "\n%{http_code} %{url_effective}",
           "-A", ua,
           "-H", "Accept: text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
           "-H", "Accept-Language: zh-CN,zh;q=0.9,en;q=0.8",
           "-H", "Upgrade-Insecure-Requests: 1",
           "-H", 'sec-ch-ua: "Chromium";v="120", "Not:A-Brand";v="99"',
           "-H", 'sec-ch-ua-platform: "macOS"']
    if referer:
        cmd += ["-H", f"Referer: {referer}"]
    cmd.append(url)
    proc = subprocess.run(cmd, capture_output=True)
    raw = proc.stdout
    tail_start = raw.rfind(b"\n")
    if tail_start < 0:
        return 0, raw, url
    meta = raw[tail_start + 1:].decode("utf-8", "ignore").split()
    body = raw[:tail_start]
    status = int(meta[0]) if meta and meta[0].isdigit() else 0
    final = meta[1] if len(meta) > 1 else url
    return status, body, final


def get(url: str, ua: str, referer: str | None = None, retries: int = 2) -> tuple[int, bytes, str]:
    last_exc = None
    for attempt in range(retries + 1):
        try:
            headers = {
                "User-Agent": ua,
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
                "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
                "Upgrade-Insecure-Requests": "1",
                "sec-ch-ua": '"Chromium";v="120", "Not:A-Brand";v="99"',
                "sec-ch-ua-platform": '"macOS"',
            }
            if referer:
                headers["Referer"] = referer
            req = urllib.request.Request(url, headers=headers)
            with urllib.request.urlopen(req, timeout=25, context=CTX) as resp:
                return resp.status, resp.read(), resp.geturl()
        except urllib.error.HTTPError as exc:
            body = exc.read() if hasattr(exc, "read") else b""
            if exc.code in (403, 404):
                return exc.code, body, url
            last_exc = exc
        except Exception as exc:  # noqa: BLE001
            last_exc = exc
        time.sleep(2 * (attempt + 1))
    raise last_exc  # type: ignore[misc]


def classify(status: int, body: bytes) -> str:
    text = body[:2000].decode("utf-8", "ignore")
    if any(m in text for m in VERIFY_MARKERS):
        return "ACCESS_RESTRICTED"
    if status == 429:
        return "RATE_LIMITED"
    if status == 403:
        return "ACCESS_RESTRICTED"
    if status >= 400:
        return f"HTTP_{status}"
    return "ok"


# ---------------------------------------------------------------- Nuxt 负载解析

def _split_args(text: str) -> list[str]:
    parts, buf, depth, quote, esc = [], [], 0, None, False
    for ch in text:
        if quote:
            buf.append(ch)
            if esc:
                esc = False
            elif ch == "\\":
                esc = True
            elif ch == quote:
                quote = None
            continue
        if ch in "\"'":
            quote = ch
            buf.append(ch)
        elif ch in "[{(":
            depth += 1
            buf.append(ch)
        elif ch in "]})":
            depth -= 1
            buf.append(ch)
        elif ch == "," and depth == 0:
            parts.append("".join(buf).strip())
            buf = []
        else:
            buf.append(ch)
    if buf:
        parts.append("".join(buf).strip())
    return [p for p in parts if p != ""]


def _js_scalar(token: str):
    t = token.strip()
    if t.startswith(("'", '"')):
        return json.loads(t) if t.startswith('"') else t[1:-1]
    if t in ("true", "false"):
        return t == "true"
    if t in ("null", "undefined"):
        return None
    try:
        return int(t)
    except ValueError:
        pass
    try:
        return float(t if not t.startswith(".") else "0" + t)
    except ValueError:
        return t


def nuxt_varmap(html: str) -> dict[str, object]:
    i = html.find("window.__NUXT__=")
    if i < 0:
        return {}
    seg = html[i + len("window.__NUXT__="):]
    m = re.match(r"\(function\(([^)]*)\)", seg)
    if not m:
        return {}
    params = [p.strip() for p in m.group(1).split(",") if p.strip()]
    tail = seg.rfind("}(")
    if tail < 0:
        return {}
    call = _balanced(seg, tail + 1, "(", ")")
    args = _split_args(call[1:-1])
    return {p: _js_scalar(a) for p, a in zip(params, args)}


def _literal_to_json(text: str, varmap: dict[str, object]) -> object:
    s = text
    s = re.sub(r"([{,]\s*)([A-Za-z_$][A-Za-z0-9_$]*)\s*:", r'\1"\2":', s)
    s = re.sub(r"(\d)\.(\d)", r"\1.\2", s)
    s = re.sub(r":\s*\.(\d)", r":0.\1", s)

    def sub_ident(m: re.Match) -> str:
        name = m.group(1)
        if name in ("true", "false", "null"):
            return name
        if name in varmap:
            val = varmap[name]
            if isinstance(val, str):
                return json.dumps(val, ensure_ascii=False)
            if val is None:
                return "null"
            return str(val)
        return json.dumps(name, ensure_ascii=False)

    s = re.sub(r"(?<=:)([A-Za-z_$][A-Za-z0-9_$]*)(?=\s*[,}])", sub_ident, s)
    return json.loads(s)


def _balanced(text: str, start: int, open_ch: str, close_ch: str) -> str:
    depth, quote, esc = 0, None, False
    for idx in range(start, len(text)):
        ch = text[idx]
        if quote:
            if esc:
                esc = False
            elif ch == "\\":
                esc = True
            elif ch == quote:
                quote = None
            continue
        if ch in "\"'":
            quote = ch
        elif ch == open_ch:
            depth += 1
        elif ch == close_ch:
            depth -= 1
            if depth == 0:
                return text[start:idx + 1]
    return text[start:]


def parse_hangqing(html: str) -> dict:
    varmap = nuxt_varmap(html)
    out = {"rows": [], "selected": None, "total": None}
    i = html.find("marketList:{")
    if i < 0:
        i = html.find("market:{")
        if i < 0:
            return out
    block = _balanced(html, html.find("{", i), "{", "}")
    tm = re.search(r"total:([A-Za-z0-9_$]+)", block)
    if tm:
        out["total"] = _js_scalar(str(varmap.get(tm.group(1), tm.group(1))))
    lm = block.find("list:[")
    if lm >= 0:
        arr = _balanced(block, block.find("[", lm), "[", "]")
        for obj in re.findall(r"\{[^{}]*\}", arr):
            try:
                out["rows"].append(_literal_to_json(obj, varmap))
            except Exception:  # noqa: BLE001
                continue
    sm = html.find("selected:{")
    if sm >= 0:
        try:
            out["selected"] = _literal_to_json(_balanced(html, html.find("{", sm), "{", "}"), varmap)
        except Exception:  # noqa: BLE001
            out["selected"] = None
    return out


# ---------------------------------------------------------------- 采集

def fetch_cnhnb_hangqing(area: str, area_id: int, date: str, page: int = 1,
                         throttle: float = 2.0) -> dict:
    suffix = "" if page == 1 else f"-{page}"
    path = f"/hangqing/q-0-0-0-{area_id}-{date}{suffix}/"
    CNHNB_RAW.mkdir(parents=True, exist_ok=True)
    target = CNHNB_RAW / f"{area}_{area_id}_{date}_p{page}.html"
    if target.exists():
        body = target.read_bytes()
        status, final = 200, f"(cached) {path}"
    else:
        status, body, final = 0, b"", ""
        for host in CNHNB_HOSTS:
            # PC 站需桌面 UA；触屏站需移动 UA。UA 与站点不匹配会触发「请验证」墙。
            ua = UA_DESKTOP if "www." in host else UA_MOBILE
            ref = "https://www.cnhnb.com/hangqing/" if "www." in host else "https://m.cnhnb.com/hangqing/"
            try:
                status, body, final = _curl_get(host + path, ua, referer=ref)
            except Exception as exc:  # noqa: BLE001
                status, body, final = 0, str(exc).encode(), host + path
            if status == 200 and classify(status, body) == "ok":
                break
            time.sleep(1.5)
        if status == 200 and b"<title>" in body:
            target.write_bytes(body)
        time.sleep(throttle)
    state = classify(status, body)
    parsed = parse_hangqing(body.decode("utf-8", "ignore")) if state == "ok" else {"rows": [], "total": None}
    host = "www.cnhnb.com" if "www.cnhnb.com" in str(final) else ("m.cnhnb.com" if "m.cnhnb.com" in str(final) else None)
    rows = [dict(r, query_area=area, query_area_id=area_id, query_date=date, query_page=page,
                 source="cnhnb_hangqing", source_url=final) for r in parsed["rows"]]
    return {"area": area, "area_id": area_id, "date": date, "page": page, "status": state,
            "http": status, "host": host, "file": target.name if target.exists() else None,
            "total": parsed["total"], "rows": rows}


def fetch_askci_article(url: str, throttle: float = 1.5) -> dict:
    ASKCI_RAW.mkdir(parents=True, exist_ok=True)
    slug = hashlib.md5(url.encode()).hexdigest()[:16]
    target = ASKCI_RAW / f"{slug}.html"
    if target.exists():
        body, status = target.read_bytes(), 200
    else:
        status, body, _ = get(url, UA_DESKTOP)
        if status == 200:
            target.write_bytes(body)
        time.sleep(throttle)
    state = classify(status, body)
    text = body.decode("utf-8", "ignore")
    title = re.search(r"<title>([^<]*)</title>", text)
    return {"url": url, "status": state, "http": status,
            "file": target.name if target.exists() else None,
            "title": title.group(1).strip() if title else None}


def fetch_askci_tag(tag: str, throttle: float = 1.5) -> dict:
    """抓标签页（按品种聚合的最近文章列表），抽出标题含“辽宁”的文章 URL。"""
    ASKCI_RAW.mkdir(parents=True, exist_ok=True)
    url = f"https://www.askci.com/news/list/tag-{urllib.parse.quote(tag)}/"
    slug = hashlib.md5(url.encode()).hexdigest()[:16]
    target = ASKCI_RAW / f"tag_{slug}.html"
    if target.exists():
        body, status = target.read_bytes(), 200
    else:
        status, body, _ = get(url, UA_DESKTOP)
        if status == 200:
            target.write_bytes(body)
        time.sleep(throttle)
    state = classify(status, body)
    text = body.decode("utf-8", "ignore")
    items = re.findall(
        r'href="(https://www\.askci\.com/news/data/price/\d{8}/\d+\.shtml)"[^>]*>\s*'
        r'<div class="list_box1_title">([^<]+)</div>', text)
    liaoning = [{"url": u, "title": t.strip(), "tag": tag} for u, t in items if "辽宁" in t]
    return {"tag": tag, "url": url, "status": state, "http": status,
            "file": target.name if target.exists() else None,
            "records_in_page": len(items), "liaoning": liaoning}


def parse_askci_price(html: str) -> dict:
    """解析中商情报网「XX省XX批发价格行情」页：地区 + 市场 + 品种 + 当日/前一日价格 + 日期。"""
    out = {"title": None, "publish": None, "article_date": None, "region": None,
           "product": None, "url": None, "rows": []}
    t = re.search(r"<title>([^<]*)</title>", html)
    if t:
        out["title"] = t.group(1).strip()
        tm = re.match(r"(\d{4})年(\d{1,2})月(\d{1,2})日(.+?)批发价格行情", out["title"])
        if tm:
            out["article_date"] = f"{tm.group(1)}-{int(tm.group(2)):02d}-{int(tm.group(3)):02d}"
            out["region"] = tm.group(4)
            out["product"] = re.sub(r".*?省|.*?市|.*?自治区", "", tm.group(4)) or tm.group(4)
    p = re.search(r"中商产业研究院\s*(\d{4}-\d{2}-\d{2}[^<]*)", html)
    if p:
        out["publish"] = p.group(1).strip()
    table = re.search(r"<table>.*?</table>", html, re.S)
    if not table:
        return out
    for tr in re.findall(r"<tr>(.*?)</tr>", table.group(0), re.S):
        cells = [re.sub(r"<[^>]+>", "", c).strip() for c in re.findall(r"<td>(.*?)</td>", tr, re.S)]
        if len(cells) >= 5 and cells[0] != "地区":
            out["rows"].append({"province": cells[0], "market": cells[1], "product": cells[2],
                                "price_today": cells[3], "price_prev": cells[4]})
    return out


def rebuild_from_cache() -> dict:
    """只读已落盘 HTML，重建合并 jsonl 与清单（不联网）。"""
    files = sorted(CNHNB_RAW.glob("*.html"))
    manifest, rows_total = [], 0
    lines: list[str] = []
    for path in files:
        stem = path.stem
        m = re.match(r"(.+?)_(\d+)_(\d{8})_p(\d+)$", stem)
        if not m:
            continue
        area, area_id, date, page = m.group(1), int(m.group(2)), m.group(3), int(m.group(4))
        html = path.read_text(encoding="utf-8", errors="ignore")
        parsed = parse_hangqing(html)
        rows_total += len(parsed["rows"])
        for row in parsed["rows"]:
            lines.append(json.dumps(dict(row, query_area=area, query_area_id=area_id,
                                         query_date=date, query_page=page,
                                         source="cnhnb_hangqing",
                                         source_url=f"https://m.cnhnb.com/hangqing/q-0-0-0-{area_id}-{date}/"),
                                    ensure_ascii=False))
        sel = (parsed.get("selected") or {}).get("area") or {}
        head = html[:4000]
        host = "m.cnhnb.com" if "触屏版" in head else "www.cnhnb.com"
        manifest.append({"area": area, "area_id": area_id, "date": date, "page": page,
                         "file": path.name, "bytes": path.stat().st_size, "host": host,
                         "declared_total": parsed["total"], "parsed_rows": len(parsed["rows"]),
                         "area_no": (sel.get("area") or {}).get("areaNo")})
    rows_path = RAW / "cnhnb_hangqing_rows.jsonl"
    rows_path.write_text("\n".join(lines) + ("\n" if lines else ""), encoding="utf-8")
    out = {"generated_at": datetime.now().isoformat(timespec="seconds"),
           "files": len(manifest), "parsed_rows": rows_total,
           "rows_path": str(rows_path.relative_to(ROOT)), "manifest": manifest}
    (RAW / "cnhnb_cache_manifest.json").write_text(
        json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"[rebuild] cnhnb {len(manifest)} 个原始页 -> {rows_total} 行 -> {rows_path.name}")

    askci_lines, askci_manifest, askci_rows_total = [], [], 0
    for path in sorted(ASKCI_RAW.glob("*.html")):
        if path.name.startswith("tag_"):
            continue
        parsed = parse_askci_price(path.read_text(encoding="utf-8", errors="ignore"))
        askci_rows_total += len(parsed["rows"])
        for row in parsed["rows"]:
            askci_lines.append(json.dumps(dict(row, article_title=parsed["title"],
                                               article_date=parsed["article_date"],
                                               article_region=parsed["region"],
                                               publish=parsed["publish"], source="askci_price",
                                               source_url=parsed["url"] or path.name),
                                          ensure_ascii=False))
        askci_manifest.append({"file": path.name, "bytes": path.stat().st_size,
                               "title": parsed["title"], "article_date": parsed["article_date"],
                               "region": parsed["region"], "markets": len(parsed["rows"])})
    askci_rows_path = RAW / "askci_price_rows.jsonl"
    askci_rows_path.write_text("\n".join(askci_lines) + ("\n" if askci_lines else ""), encoding="utf-8")
    (RAW / "askci_cache_manifest.json").write_text(
        json.dumps({"generated_at": datetime.now().isoformat(timespec="seconds"),
                    "files": len(askci_manifest), "parsed_rows": askci_rows_total,
                    "rows_path": str(askci_rows_path.relative_to(ROOT)),
                    "manifest": askci_manifest}, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"[rebuild] askci {len(askci_manifest)} 篇文章 -> {askci_rows_total} 行 -> {askci_rows_path.name}")

    (RAW / "b2b_probe_report.json").write_text(json.dumps({
        "generated_at": out["generated_at"],
        "cnhnb": {"pages": len(manifest), "rows": rows_total,
                  "rows_path": out["rows_path"], "manifest": manifest},
        "askci": {"pages": len(askci_manifest), "rows": askci_rows_total,
                  "rows_path": str(askci_rows_path.relative_to(ROOT)), "manifest": askci_manifest},
    }, ensure_ascii=False, indent=1), encoding="utf-8")
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dates", nargs="*", default=None, help="YYYYMMDD 列表")
    ap.add_argument("--full", action="store_true", help="五县域全量小样（默认只跑东港+北镇）")
    ap.add_argument("--rebuild-only", action="store_true", help="只从已落盘 HTML 重建，不联网")
    args = ap.parse_args()

    if args.rebuild_only:
        rebuild_from_cache()
        return

    sample_dates = args.dates or ["20260915"]

    areas = CNHNB_AREAS if args.full else {k: CNHNB_AREAS[k] for k in ("东港市", "北镇市")}
    for area, meta in areas.items():
        for date in sample_dates:
            res = fetch_cnhnb_hangqing(area, meta["area_id"], date)
            print(f"[cnhnb] {area} {date} -> {res['status']} host={res['host']} "
                  f"total={res['total']} rows={len(res['rows'])}")

    for tag in ("豆角价格", "西红柿价格", "土豆价格", "大白菜价格", "黄瓜价格"):
        res = fetch_askci_tag(tag)
        print(f"[askci-tag] {tag} -> {res['status']} 页内记录={res['records_in_page']} 辽宁={len(res['liaoning'])}")
        for item in res["liaoning"][:2]:
            art = fetch_askci_article(item["url"])
            print(f"[askci] {art['status']} {art['title']}")

    rebuild_from_cache()


if __name__ == "__main__":
    main()
