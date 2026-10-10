"""大连市「发展改革研究中心」农副产品周度价格监测报告采集（P0 城市级价格）。

来源：大连市人民政府门户
  民生热点  col1190 (unitid=43955, 1619 条)
  百姓日常  col1437 (unitid=46037,  639 条)
接口：/module/web/jpage/dataproxy.jsp?page={n}&columnid={id}&unitid={uid}...
文章：https://www.dl.gov.cn/art/{yyyy}/{m}/{d}/art_{col}_{id}.html

周报标题特征：肉蛋菜价格 / 农副产品价格 / 菜篮子 / 蔬菜价格 / 鸡蛋价格 / 价格运行
本脚本枚举两栏目全部文章 → 筛选价格监测周报 → 下载原始 HTML 落盘 data/raw/prices/dalian_dfgw_weekly/。
"""
from __future__ import annotations

import json
import re
import ssl
import time
import urllib.request
from pathlib import Path

ROOT = next(p for p in Path(__file__).resolve().parents if (p / "AgriScope").is_dir() and (p / "data").is_dir())
RAW = ROOT / "data/raw" / "prices" / "dalian_dfgw_weekly"
RAW.mkdir(parents=True, exist_ok=True)

CTX = ssl.create_default_context()
CTX.check_hostname = False
CTX.verify_mode = ssl.CERT_NONE
UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")

COLUMNS = {
    "col1190": {"columnid": 1190, "unitid": "43955", "total": 1619},
    "col1437": {"columnid": 1437, "unitid": "46037", "total": 639},
}
PAGE_SIZE = 100

# 价格监测周报标题特征（排除非价格栏目杂文）
PRICE_RE = re.compile(
    r"价格|菜价|菜篮|农副|粮油|肉蛋|蛋价|肉价|蔬菜|鸡蛋|猪肉|肉菜|民生商品|生活必需品"
)

ARTICLE_RE = re.compile(
    r'href="(https://www\.dl\.gov\.cn/art/[^"]+)"[^>]*>.*?'
    r'<div class="desc">([^<]+)</div>.*?\[([0-9-]+)\]', re.S
)


def http_get(url: str, retries: int = 3, timeout: int = 30) -> str:
    last = None
    for a in range(retries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": UA,
                "Referer": "https://www.dl.gov.cn/col/col1190/index.html"})
            with urllib.request.urlopen(req, timeout=timeout, context=CTX) as r:
                return r.read().decode("utf-8", "ignore")
        except Exception as exc:
            last = exc
            time.sleep(2 * (a + 1))
    raise last


def list_column(col_id: str) -> list[dict]:
    cfg = COLUMNS[col_id]
    pages = (cfg["total"] + PAGE_SIZE - 1) // PAGE_SIZE
    out = []
    for p in range(1, pages + 1):
        url = (f"https://www.dl.gov.cn/module/web/jpage/dataproxy.jsp"
               f"?page={p}&webid=1&path=https://www.dl.gov.cn/"
               f"&columnid={cfg['columnid']}&sourceContentType=1"
               f"&unitid={cfg['unitid']}&webname=%25E5%25A4%25A7%25E8%25BF%259E%25E5%25B8%2582%25E4%25BA%25BA%25E6%25B0%2591%25E6%2594%25BF%25E5%25BA%259C"
               f"&permissiontype=0")
        try:
            raw = http_get(url)
        except Exception as exc:
            print(f"  [FAIL] {col_id} 第{p}页: {exc}")
            continue
        recs = ARTICLE_RE.findall(raw)
        if not recs:
            print(f"  [WARN] {col_id} 第{p}页无记录（可能页面未按预期返回）")
        for u, t, d in recs:
            if PRICE_RE.search(t.strip()):
                out.append({"url": u, "title": t.strip(), "date": d, "column": col_id})
        print(f"  [OK] {col_id} 第{p}/{pages}页 {len(recs)}条, 命中{len(out)}")
        time.sleep(0.6)
    return out


def main() -> None:
    all_articles = []
    for col in COLUMNS:
        print(f"== 枚举 {col} ==")
        all_articles.extend(list_column(col))

    # 去重
    seen, unique = set(), []
    for a in all_articles:
        if a["url"] in seen:
            continue
        seen.add(a["url"])
        unique.append(a)
    unique.sort(key=lambda x: x["date"], reverse=True)

    manifest = RAW / "article_index.json"
    manifest.write_text(json.dumps(unique, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"\n[OK] 命中价格监测文章 {len(unique)} 篇 → {manifest}")
    print(f"时间范围: {unique[-1]['date']} ~ {unique[0]['date']}")


if __name__ == "__main__":
    main()
