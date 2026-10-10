"""枚举辽宁省发改委「分析预测/监测预警」栏目全部文章（跨 2021-2026）。

来源：https://fgw.ln.gov.cn/fgw/xxgk/jgjc/fxyc/
分页 URL：/fgw/xxgk/jgjc/fxyc/57426d9f-{n}.shtml（共 79 页）
用途：筛选 大连/铁岭/锦州/朝阳/丹东 城市级价格监测文章（月度综述/日监测/周报）。
输出：data/raw/prices/lnfgw_fxyc_index.json
"""
from __future__ import annotations

import json
import re
import ssl
import time
import urllib.request
from pathlib import Path

ROOT = next(p for p in Path(__file__).resolve().parents if (p / "AgriScope").is_dir() and (p / "data").is_dir())
OUT = ROOT / "data/raw" / "prices" / "lnfgw_fxyc_index.json"

CTX = ssl.create_default_context()
CTX.check_hostname = False
CTX.verify_mode = ssl.CERT_NONE
UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36"

ARTICLE_RE = re.compile(
    r'href="([^"]*?/fgw/xxgk/jgjc/fxyc/(20\d{17})/index\.shtml)"[^>]*>([^<]{6,80})</a>\s*<span[^>]*>([0-9-]+)</span>'
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
        recs = ARTICLE_RE.findall(html)
        for u, ts, t, d in recs:
            all_arts.append({"ts": ts, "date": d, "title": t.strip(),
                             "url": "https://fgw.ln.gov.cn" + u})
        print(f"  [OK] 第{p}页 {len(recs)}条 (累计{len(all_arts)})")
        time.sleep(0.5)

    # 去重
    seen, uniq = set(), []
    for a in all_arts:
        if a["ts"] in seen:
            continue
        seen.add(a["ts"])
        uniq.append(a)
    uniq.sort(key=lambda x: x["ts"])

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(uniq, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"\n[OK] 共 {len(uniq)} 篇文章 → {OUT}")
    print(f"时间范围: {uniq[0]['date']} ~ {uniq[-1]['date']}")

    # 按城市筛选统计
    import collections
    cities = {"大连": 0, "铁岭": 0, "锦州": 0, "朝阳": 0, "丹东": 0, "沈阳": 0}
    for a in uniq:
        for c in cities:
            if c in a["title"]:
                cities[c] += 1
    print("标题含城市统计:", dict(cities))


if __name__ == "__main__":
    main()
