"""扫描辽宁省发改委 fxyc（分析预测/监测预警）栏目全部页，筛选丹东城市级价格文章。

来源：https://fgw.ln.gov.cn/fgw/xxgk/jgjc/fxyc/
分页 URL：/fgw/xxgk/jgjc/fxyc/57426d9f-{n}.shtml
注：旧版枚举脚本 lnfgw_fxyc_enum.py 的正则只匹配时间戳式URL(20\\d{17})，
    漏掉了旧式ID(如 A62B5CE...) 的丹东文章，本脚本使用宽松正则。

输出：
  data/raw/prices/dandong/lnfgw_fxyc_dandong_index.json   （丹东文章索引）
  data/raw/prices/dandong/html/*.html                     （原文落盘）
"""
from __future__ import annotations

import hashlib
import json
import re
import ssl
import time
import urllib.request
from pathlib import Path

ROOT = next(p for p in Path(__file__).resolve().parents if (p / "AgriScope").is_dir() and (p / "data").is_dir())
RAW_DIR = ROOT / "data/raw" / "prices" / "dandong"
HTML_DIR = RAW_DIR / "html"
HTML_DIR.mkdir(parents=True, exist_ok=True)

CTX = ssl.create_default_context()
CTX.check_hostname = False
CTX.verify_mode = ssl.CERT_NONE
UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36"

# 宽松正则：匹配 fxyc 栏目内任意文章链接（时间戳式 20\d{17} 或旧式ID）
ART_RE = re.compile(
    r'href="([^"]*?/fgw/xxgk/jgjc/fxyc/([0-9A-F]{8,32})/index\.shtml)"[^>]*title="([^"]{4,120})"'
)


def get(url: str, retries: int = 3) -> str:
    last = None
    for a in range(retries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": UA})
            with urllib.request.urlopen(req, timeout=25, context=CTX) as r:
                return r.read().decode("utf-8", "ignore")
        except Exception as exc:
            last = exc
            time.sleep(2 * (a + 1))
    raise last


def main() -> None:
    all_arts = []
    for p in range(1, 80):
        url = f"https://fgw.ln.gov.cn/fgw/xxgk/jgjc/fxyc/57426d9f-{p}.shtml"
        try:
            html = get(url)
        except Exception as exc:
            print(f"  [FAIL] 第{p}页: {exc}")
            continue
        recs = ART_RE.findall(html)
        for u, aid, t in recs:
            all_arts.append({"article_id": aid, "title": t.strip(),
                             "url": "https://fgw.ln.gov.cn" + u})
        print(f"  [OK] 第{p}页 {len(recs)}条 (累计{len(all_arts)})")
        time.sleep(0.6)

    # 去重
    seen, uniq = set(), []
    for a in all_arts:
        if a["url"] in seen:
            continue
        seen.add(a["url"])
        uniq.append(a)
    uniq.sort(key=lambda x: x["url"])

    # 筛选丹东
    dd = [a for a in uniq if "丹东" in a["title"]]
    print(f"\n[OK] 栏目共 {len(uniq)} 篇，其中标题含「丹东」 {len(dd)} 篇")
    for a in dd:
        print("   -", a["title"])

    # 下载丹东文章原文
    meta = []
    for a in dd:
        f = HTML_DIR / f"{a['article_id']}.html"
        if not f.exists():
            try:
                req = urllib.request.Request(a["url"], headers={"User-Agent": UA})
                with urllib.request.urlopen(req, timeout=30, context=CTX) as r:
                    f.write_bytes(r.read())
            except Exception as exc:
                print(f"  [FAIL] {a['title'][:30]}: {exc}")
                continue
            time.sleep(0.8)
        meta.append({**a, "raw_file": str(f.relative_to(ROOT))})
        print(f"  [OK] 已落盘 {f.name}  {a['title'][:36]}")

    out = RAW_DIR / "lnfgw_fxyc_dandong_index.json"
    out.write_text(json.dumps(meta, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"\n[OK] {len(meta)} 篇丹东文章索引 → {out.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
