"""锦州文章下载（复用已建索引，跳过列表阶段）。

用途：jinzhou_deep.py 的列表阶段（96 页）耗时长且易被中断，
本脚本直接读取已生成的 article_index.json（1919 条）下载文章正文。
幂等：已存在的 HTML 自动跳过。
"""
from __future__ import annotations

import hashlib
import json
import os
import ssl
import time
import urllib.request
from pathlib import Path

for k in ("HTTP_PROXY", "HTTPS_PROXY", "http_proxy", "https_proxy", "ALL_PROXY", "all_proxy"):
    os.environ.pop(k, None)

ROOT = next(p for p in Path(__file__).resolve().parents if (p / "AgriScope").is_dir() and (p / "data").is_dir())
RAW = ROOT / "data/raw" / "prices" / "jinzhou_deep"
HTML = RAW / "html"
HTML.mkdir(parents=True, exist_ok=True)

CTX = ssl.create_default_context()
CTX.check_hostname = False
CTX.verify_mode = ssl.CERT_NONE
UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")


def get(url: str, timeout: int = 25, retries: int = 3) -> str:
    last = None
    for a in range(retries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": UA})
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
            time.sleep(1.5 * (a + 1))
    raise last


def main() -> None:
    idx = json.loads((RAW / "article_index.json").read_text(encoding="utf-8"))
    print(f"索引 {len(idx)} 条")
    todo = []
    for it in idx:
        aid = hashlib.md5(it["url"].encode()).hexdigest()[:16]
        if not (HTML / f"{aid}.html").exists():
            todo.append((it, aid))
    print(f"待下载 {len(todo)} 篇（已存在 {len(idx)-len(todo)} 篇）")

    t0 = time.time()
    ok = fail = 0
    for i, (it, aid) in enumerate(todo, 1):
        try:
            (HTML / f"{aid}.html").write_text(get(it["url"]), encoding="utf-8")
            ok += 1
        except Exception as exc:
            fail += 1
            if fail <= 8:
                print(f"  [FAIL] {it['url']}: {exc}")
            continue
        time.sleep(0.25)
        if i % 200 == 0:
            print(f"  进度 {i}/{len(todo)} | 成功{ok} 失败{fail} | {(time.time()-t0)/60:.1f}min")
    print(f"\n[OK] 锦州文章下载完成：成功 {ok}，失败 {fail}，共 {len(list(HTML.glob('*.html')))} 篇")


if __name__ == "__main__":
    main()
