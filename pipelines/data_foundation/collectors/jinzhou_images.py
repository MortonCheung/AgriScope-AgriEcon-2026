"""锦州价格图片采集 + OCR（价格数据为图片型表格）。

背景：锦州菜篮子平台的日度文章**正文无表格**，价格表以 **PNG 图片**发布
（`/__local/.../*.png`，另有 `_vsl` 附件路径）。因此走 OCR 路线：
  1. 从已下载的文章 HTML 提取图片 URL
  2. 下载图片原文件（**必须保留原图**，不删）
  3. 用 macOS Vision 框架 OCR（collectors/ocr_image.swift）
  4. 输出文本供后续解析

质量等级说明：OCR 结果属**机器转录**，quality_grade = B。
抽样人工核对后如准确率高方可使用；发现错误须回原图核对。
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import ssl
import subprocess
import time
import urllib.request
from pathlib import Path

for k in ("HTTP_PROXY", "HTTPS_PROXY", "http_proxy", "https_proxy", "ALL_PROXY", "all_proxy"):
    os.environ.pop(k, None)

ROOT = next(p for p in Path(__file__).resolve().parents if (p / "AgriScope").is_dir() and (p / "data").is_dir())
RAW = ROOT / "data/raw" / "prices" / "jinzhou_deep"
HTML = RAW / "html"
IMG = RAW / "images"
OCR = RAW / "ocr"
for d in (IMG, OCR):
    d.mkdir(parents=True, exist_ok=True)

CTX = ssl.create_default_context()
CTX.check_hostname = False
CTX.verify_mode = ssl.CERT_NONE
UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")
SWIFT = ROOT / "collectors" / "ocr_image.swift"

IMG_RE = re.compile(r'<img[^>]*src="([^"]+\.(?:png|jpg|jpeg))"[^>]*>', re.I)


def fetch(url: str, referer: str = "", timeout: int = 30, retries: int = 3) -> bytes:
    last = None
    for a in range(retries):
        try:
            h = {"User-Agent": UA}
            if referer:
                h["Referer"] = referer
            req = urllib.request.Request(url, headers=h)
            with urllib.request.urlopen(req, timeout=timeout, context=CTX) as r:
                return r.read()
        except Exception as exc:
            last = exc
            time.sleep(1.5 * (a + 1))
    raise last


def abs_url(src: str, page: str) -> str:
    if src.startswith("http"):
        return src
    base = "https://www.jz.gov.cn"
    return base + (src if src.startswith("/") else "/" + src)


def main() -> None:
    idx = json.loads((RAW / "article_index.json").read_text(encoding="utf-8"))
    daily = [x for x in idx if x["kind"] == "daily"]
    print(f"日度文章 {len(daily)} 篇；已下载 HTML {len(list(HTML.glob('*.html')))} 篇")

    meta_out = []
    img_saved = img_skip = img_fail = 0
    t0 = time.time()
    for it in daily:
        aid = hashlib.md5(it["url"].encode()).hexdigest()[:16]
        hf = HTML / f"{aid}.html"
        if not hf.exists():
            continue
        try:
            html = hf.read_text(encoding="utf-8", errors="replace")
        except Exception:
            continue
        srcs = [s for s in IMG_RE.findall(html)
                if ("__local" in s or "_vsl" in s or "upload" in s.lower())]
        if not srcs:
            meta_out.append({**it, "article_id": aid, "images": [],
                             "note": "未发现价格图片"})
            continue
        saved_paths = []
        for s in srcs:
            full = abs_url(s, it["url"])
            iid = hashlib.md5(full.encode()).hexdigest()[:16]
            f = IMG / f"{it['date'] or 'nogdate'}_{iid}.png"
            if f.exists():
                img_skip += 1
                saved_paths.append(str(f.relative_to(ROOT)))
                continue
            try:
                data = fetch(full, referer=it["url"])
                if len(data) < 800:      # 太小基本是图标
                    continue
                f.write_bytes(data)
                img_saved += 1
                saved_paths.append(str(f.relative_to(ROOT)))
            except Exception:
                img_fail += 1
            time.sleep(0.2)
        meta_out.append({**it, "article_id": aid, "images": saved_paths})
        if len(meta_out) % 100 == 0:
            print(f"  进度 {len(meta_out)}/{len(daily)} | 图新{img_saved} 跳过{img_skip} 失败{img_fail} | {(time.time()-t0)/60:.1f}min")

    (RAW / "image_manifest.json").write_text(
        json.dumps(meta_out, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"\n[OK] 图片：新增 {img_saved}，跳过 {img_skip}，失败 {img_fail}")
    print(f"    清单 {RAW/'image_manifest.json'}")


if __name__ == "__main__":
    main()
