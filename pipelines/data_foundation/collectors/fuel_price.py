"""辽宁省成品油价格调整公告采集（手册第 21 节，P2）。

辽宁发改委以 PDF 形式发布成品油调价公告。本脚本：
  1. 从发改委公告栏目抓取全部调价公告条目
  2. 下载 PDF 原文件到 data/raw/macro/fuel/
  3. 解析 PDF 文本中的 92#/95#/0# 柴油价格（元/升、元/吨）

注意：价格有效期转换（一次调价 → 下次调价前保持）属于**官方价格有效期**，
不是插值，手册第 21 节明确允许，但必须记录 valid_from / valid_to。
"""
from __future__ import annotations

import hashlib
import json
import re
import ssl
import time
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = next(p for p in Path(__file__).resolve().parents if (p / "AgriScope").is_dir() and (p / "data").is_dir())
RAW = ROOT / "data/raw" / "macro" / "fuel"
RAW.mkdir(parents=True, exist_ok=True)

CTX = ssl.create_default_context(); CTX.check_hostname = False; CTX.verify_mode = ssl.CERT_NONE
UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")
BASE = "https://fgw.ln.gov.cn"

# 发改委公告栏目（首页可见的调价公告入口）
LIST_URLS = [
    "https://fgw.ln.gov.cn/fgw/index/tzgg/index.shtml",
    "https://fgw.ln.gov.cn/",
]

ITEM_RE = re.compile(
    r'<a[^>]*href="([^"]*viewer\.html\?file=[^"]+)"[^>]*title="([^"]*(?:成品油|价格调整)[^"]*)"',
    re.I)


def get_bytes(url: str, timeout: int = 60) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=timeout, context=CTX) as r:
        return r.read()


def get_text(url: str, timeout: int = 40) -> str:
    return get_bytes(url, timeout).decode("utf-8", "replace")


def main() -> None:
    found: dict[str, str] = {}
    for lu in LIST_URLS:
        try:
            html = get_text(lu)
        except Exception as exc:
            print(f"[FAIL] 列表 {lu}: {exc}")
            continue
        for href, title in ITEM_RE.findall(html):
            found[href] = title
        print(f"[{lu}] 命中 {len(found)} 条调价公告")

    if not found:
        (RAW / "STATUS.md").write_text(
            "# 成品油价格采集状态\n\nstatus: parse_failed\n\n"
            "未在静态 HTML 中发现调价公告的 PDF 链接（页面可能异步渲染）。\n", encoding="utf-8")
        print("[WARN] 未找到公告链接")
        return

    manifest = []
    for href, title in sorted(found.items()):
        full = href if href.startswith("http") else BASE + href
        # viewer.html?file=/fgw/articleFileDir/... → 真实 PDF 路径
        m = re.search(r"file=([^&]+)", full)
        if not m:
            continue
        pdf_path = urllib.parse.unquote(m.group(1))
        pdf_url = pdf_path if pdf_path.startswith("http") else BASE + pdf_path
        aid = hashlib.md5(pdf_url.encode()).hexdigest()[:16]
        out = RAW / f"{aid}.pdf"
        if not out.exists():
            try:
                data = get_bytes(pdf_url)
                out.write_bytes(data)
                print(f"[OK] {title[:40]} -> {out.name} ({len(data)} bytes)")
            except Exception as exc:
                print(f"[FAIL] {pdf_url}: {exc}")
                continue
            time.sleep(1.0)
        manifest.append({"article_id": aid, "title": title,
                         "pdf_url": pdf_url, "file": str(out.relative_to(ROOT))})

    (RAW / "fuel_manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"[OK] 下载 {len(manifest)} 份调价公告 PDF")


if __name__ == "__main__":
    main()
