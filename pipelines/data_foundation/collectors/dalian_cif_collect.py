"""下载大连商务预报「生活必需品动态」全部文章并解析批发价格表与供应量。

来源：大连市商务局·大连商务预报
  https://cif.mofcom.gov.cn/newsite/html/dalian/index.html
文章含：
  - 蔬菜批发价格汇总统计表（品种×双兴×南关岭×批发价+涨幅，含日均上市量）
  - 价格监测简报（半月报）
  - 农副产品价格日监测报告

输出：
  data/raw/prices/dalian_cif/html/{hash}.html
  city_data/reference/staging/dalian_cif_prices.csv
"""
from __future__ import annotations

import hashlib
import json
import re
import ssl
import time
import urllib.request
from datetime import datetime
from pathlib import Path

import pandas as pd

ROOT = next(p for p in Path(__file__).resolve().parents if (p / "AgriScope").is_dir() and (p / "data").is_dir())
RAW = ROOT / "data/raw" / "prices" / "dalian_cif"
HTML_DIR = RAW / "html"
HTML_DIR.mkdir(parents=True, exist_ok=True)
STAGING = ROOT / "city_data/reference/staging"
STAGING.mkdir(parents=True, exist_ok=True)

CTX = ssl.create_default_context()
CTX.check_hostname = False
CTX.verify_mode = ssl.CERT_NONE
UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36"

ARTICLES = [
    ("2026-09-14", "我市主要生活必需品价格监测简报（9月上半月）", "/newsite/html/dalian/html/24511242/2026/9/14/1789346572839.html"),
    ("2026-08-28", "蔬菜批发价格汇总统计表（8月26日）", "/newsite/html/dalian/html/24511242/2026/8/28/1787895491584.html"),
    ("2026-08-11", "我市蔬菜价格小幅上涨，鸡蛋价格回落", "/newsite/html/dalian/html/24511242/2026/8/11/1786412630507.html"),
    ("2026-08-05", "我市伏天蛋价小幅上涨，蔬菜价格小幅回落", "/newsite/html/dalian/html/24511242/2026/8/5/1785896271195.html"),
    ("2026-07-31", "我市猪肉微降，鸡蛋蔬菜价格上涨", "/newsite/html/dalian/html/24511242/2026/7/31/1785460953703.html"),
    ("2026-07-31", "受“巴威”影响，我市上周肉蛋菜价格小幅上涨", "/newsite/html/dalian/html/24511242/2026/7/27/1785117409589.html"),
    ("2026-07-31", "上周我市农副产品价格以降为主", "/newsite/html/dalian/html/24511242/2026/7/27/1785117285552.html"),
    ("2026-07-31", "我市肉价微涨，鸡蛋蔬菜价格继续回落", "/newsite/html/dalian/html/24511242/2026/7/27/1785117301682.html"),
    ("2026-07-31", "我市肉价小幅上涨，鸡蛋蔬菜价格小幅下降", "/newsite/html/dalian/html/24511242/2026/7/27/1785117317020.html"),
    ("2026-07-27", "打响生活必需品防汛保供“发令枪”", "/newsite/html/dalian/html/24511242/2026/7/27/1785117391265.html"),
    ("2026-07-27", "我市主要农副产品价格日监测情况报告", "/newsite/html/dalian/html/24511242/2026/7/27/1785117379339.html"),
]


def http_get_bytes(url: str, retries: int = 3) -> bytes:
    last = None
    for a in range(retries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": UA})
            with urllib.request.urlopen(req, timeout=30, context=CTX) as r:
                return r.read()  # 原始字节，不做解码（页面可能 GBK）
        except Exception as exc:
            last = exc
            time.sleep(2 * (a + 1))
    raise last


def decode_html(raw: bytes) -> str:
    for enc in ("gbk", "gb18030", "utf-8"):
        try:
            t = raw.decode(enc)
            return t
        except Exception:
            continue
    return raw.decode("gbk", "replace")


def parse_wholesale_table(html: str) -> list[dict]:
    """解析蔬菜批发价格汇总统计表 → 品种×市场价格观测 + 上市量。"""
    rows = []
    tables = re.findall(r"<table.*?</table>", html, re.S | re.I)
    for tb in tables:
        trs = re.findall(r"<tr.*?</tr>", tb, re.S | re.I)
        for tr in trs:
            cells = [re.sub(r"<[^>]+>", "", c).strip()
                     for c in re.findall(r"<t[dh][^>]*>(.*?)</t[dh]>", tr, re.S | re.I)]
            cells = [c for c in cells if c]
            if len(cells) >= 6 and cells[0].isdigit():
                rows.append({
                    "no": cells[0], "product": cells[1],
                    "shuangxing": cells[2], "nanguanling": cells[3],
                    "prev_price": cells[4], "price": cells[5], "pct": cells[6] if len(cells) > 6 else "",
                })
    return rows


def parse_supply_text(html: str) -> list[dict]:
    """提取上市量/供应量文本观测（如：日均蔬菜上市量为830吨）。"""
    text = re.sub(r"<[^>]+>", " ", html)
    text = re.sub(r"\s+", "", text)
    out = []
    pat = re.compile(r"([0-9.]+)\s*(吨|万吨|公斤|千克|斤)[^。；]{0,30}?(上市量|成交量|交易量|供应量|到货量|库存量|日均上市)")
    for m in pat.finditer(text):
        out.append({"value": m.group(1), "unit": m.group(2), "metric": m.group(3)})
    # 反向：上市量为830吨
    pat2 = re.compile(r"(上市量|成交量|交易量|供应量|到货量|库存量)[^0-9。；]{0,10}([0-9.]+)\s*(吨|万吨|公斤|千克|斤)")
    for m in pat2.finditer(text):
        out.append({"metric": m.group(1), "value": m.group(2), "unit": m.group(3)})
    return out


def extract_main(html: str) -> str:
    html = re.sub(r"<script.*?</script>", "", html, flags=re.S | re.I)
    html = re.sub(r"<style.*?</style>", "", html, flags=re.S | re.I)
    return html


def parse_tables(html: str) -> list[dict]:
    """解析 HTML 中的价格表格 → (market, product, price, unit)。"""
    rows = []
    tables = re.findall(r"<table.*?</table>", html, re.S | re.I)
    for tb in tables:
        trs = re.findall(r"<tr.*?</tr>", tb, re.S | re.I)
        for tr in trs:
            cells = [re.sub(r"<[^>]+>", "", c).strip() for c in re.findall(r"<t[dh][^>]*>(.*?)</t[dh]>", tr, re.S | re.I)]
            cells = [c for c in cells if c]
            if len(cells) < 2:
                continue
            rows.append(cells)
    return rows


def main() -> None:
    metas, parsed_rows = [], []
    for date, title, path in ARTICLES:
        url = "https://cif.mofcom.gov.cn" + path
        h = hashlib.md5(url.encode()).hexdigest()[:12]
        f = HTML_DIR / f"{h}.html"
        if not f.exists():
            try:
                raw = http_get_bytes(url)
                f.write_bytes(raw)  # 保存原始字节，绝不中途转码
            except Exception as exc:
                print(f"  [FAIL] {title[:24]}: {exc}")
                continue
            time.sleep(0.8)
        html = decode_html(f.read_bytes())
        tables = parse_tables(html)
        wholesale = parse_wholesale_table(html)
        supply = parse_supply_text(html)
        parsed_rows.append({"date": date, "title": title, "url": url,
                            "file": f.name, "tables": tables,
                            "wholesale": wholesale, "supply": supply})
        metas.append({"date": date, "title": title, "url": url, "file": f.name})
        tag = f"批发{len(wholesale)}行/供应{len(supply)}条" if wholesale or supply else f"表格{len(tables)}个"
        print(f"  [OK] {date} {title[:24]} {tag}")

    (RAW / "article_meta.json").write_text(json.dumps(metas, ensure_ascii=False, indent=1), encoding="utf-8")
    (RAW / "parsed_tables.json").write_text(json.dumps(parsed_rows, ensure_ascii=False, indent=1, default=str), encoding="utf-8")
    print(f"\n[OK] 保存 {len(metas)} 篇到 {RAW}")


if __name__ == "__main__":
    main()
