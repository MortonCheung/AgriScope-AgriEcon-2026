"""商务部「大连商务预报」采集（大连批发价 + 上市量，市场级）。

来源：https://cif.mofcom.gov.cn/newsite/html/dalian/index.html
      （此前判定"商务部不可达"指的是 nc.mofcom.gov.cn；cif.mofcom.gov.cn 实际可达）
发布：大连市商务局
编码：**GBK**

内容（样例）：
  蔬菜批发价格汇总统计表（单位：元/公斤）
  序号 品种 双兴 南关岭 8.19批发价格 8.26批发价格 涨幅
  → **两个批发市场逐品种批发价** + 周环比
  → 正文另含「日均蔬菜上市量为830吨」

入口：index.html（最新若干条）+ listPage?blockid=24511242（每页10条）
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import ssl
import time
import urllib.request
from pathlib import Path

for k in ("HTTP_PROXY", "HTTPS_PROXY", "http_proxy", "https_proxy", "ALL_PROXY", "all_proxy"):
    os.environ.pop(k, None)

ROOT = next(p for p in Path(__file__).resolve().parents if (p / "AgriScope").is_dir() and (p / "data").is_dir())
RAW = ROOT / "data/raw" / "prices" / "dalian_mofcom"
HTML = RAW / "html"
HTML.mkdir(parents=True, exist_ok=True)

CTX = ssl.create_default_context()
CTX.check_hostname = False
CTX.verify_mode = ssl.CERT_NONE
# cif.mofcom.gov.cn 的 TLS 配置较旧，Python 默认安全级别会握手失败
CTX.set_ciphers("DEFAULT@SECLEVEL=1")
try:
    CTX.minimum_version = ssl.TLSVersion.TLSv1
except Exception:
    pass
UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")
BASE = "https://cif.mofcom.gov.cn"
ENTRY = BASE + "/newsite/html/dalian/index.html"
LIST = BASE + "/newsite/content/content/front/listPage?blockid=%d"
BLOCKIDS = [24511242, 24511240, 24511241]

ART_RE = re.compile(r'href="(/newsite/html/dalian/html/\d+/\d{4}/\d{1,2}/\d{1,2}/\d+\.html)"')


def get(url: str, timeout: int = 30, retries: int = 3) -> str:
    last = None
    for a in range(retries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": UA, "Referer": ENTRY})
            with urllib.request.urlopen(req, timeout=timeout, context=CTX) as r:
                raw = r.read()
            return raw.decode("gbk", "replace")
        except Exception as exc:
            last = exc
            time.sleep(1.5 * (a + 1))
    raise last


def main() -> None:
    urls: list[str] = []
    for u in [ENTRY] + [LIST % b for b in BLOCKIDS]:
        try:
            h = get(u)
        except Exception as exc:
            print(f"  [列表] {u} 失败 {exc}")
            continue
        got = [BASE + x for x in ART_RE.findall(h)]
        urls += got
        print(f"  [列表] {u.split('?')[-1][:28]} -> {len(got)} 条")
        time.sleep(0.4)
    seen, uniq = set(), []
    for u in urls:
        if u not in seen:
            seen.add(u); uniq.append(u)
    print(f"[OK] 去重后 {len(uniq)} 篇")

    saved = skip = fail = 0
    for u in uniq:
        aid = hashlib.md5(u.encode()).hexdigest()[:16]
        f = HTML / f"{aid}.html"
        if f.exists():
            skip += 1
            continue
        try:
            f.write_text(get(u), encoding="utf-8")
            saved += 1
        except Exception:
            fail += 1
        time.sleep(0.3)
    print(f"[OK] 大连商务预报：新增 {saved}，跳过 {skip}，失败 {fail}")

    (RAW / "urls.json").write_text(json.dumps(uniq, ensure_ascii=False, indent=1), encoding="utf-8")


if __name__ == "__main__":
    main()
