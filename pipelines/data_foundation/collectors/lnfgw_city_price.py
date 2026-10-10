"""通用：从辽宁省发改委监测预警栏目下载指定城市的价格监测文章并解析。

用法：python3 collectors/lnfgw_city_price.py 铁岭
来源：https://fgw.ln.gov.cn/fgw/xxgk/jgjc/fxyc/（文章索引在 data/raw/prices/lnfgw_fxyc_index.json）
输出：
  data/raw/prices/lnfgw_{city}/html/*.html
  city_data/reference/staging/{city}_price_lnfgw.csv
"""
from __future__ import annotations

import hashlib
import json
import re
import ssl
import sys
import time
import urllib.request
from datetime import datetime
from pathlib import Path

import pandas as pd

ROOT = next(p for p in Path(__file__).resolve().parents if (p / "AgriScope").is_dir() and (p / "data").is_dir())
STAGING = ROOT / "city_data/reference/staging"
STAGING.mkdir(parents=True, exist_ok=True)

CTX = ssl.create_default_context()
CTX.check_hostname = False
CTX.verify_mode = ssl.CERT_NONE
UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36"

GOODS = {
    "粳米": "粳米", "大米": "大米", "面粉": "面粉", "特一粉": "面粉", "标准粉": "面粉",
    "散装大豆油": "大豆油", "桶装大豆油": "大豆油", "大豆油": "大豆油",
    "桶装花生油": "花生油", "花生油": "花生油", "猪肉": "猪肉", "猪精瘦肉": "猪精瘦肉",
    "精瘦肉": "猪精瘦肉", "肋条肉": "猪肉", "带皮后腿肉": "猪肉", "牛肉": "牛肉",
    "羊肉": "羊肉", "鸡肉": "鸡肉", "鸡蛋": "鸡蛋", "鲤鱼": "鲤鱼", "带鱼": "带鱼",
    "牛奶": "牛奶", "大白菜": "大白菜", "白菜": "大白菜", "土豆": "土豆", "黄瓜": "黄瓜",
    "茄子": "茄子", "西红柿": "西红柿", "青椒": "青椒", "尖椒": "尖椒", "芸豆": "芸豆",
    "菠菜": "菠菜", "韭菜": "韭菜", "芹菜": "芹菜", "甘蓝": "甘蓝", "油菜": "油菜",
    "萝卜": "萝卜", "蒜薹": "蒜薹", "蒜苔": "蒜薹", "豆角": "豆角", "菜花": "菜花",
    "胡萝卜": "胡萝卜", "冬瓜": "冬瓜", "圆葱": "圆葱", "葱头": "圆葱", "西葫芦": "西葫芦",
    "生菜": "生菜", "大葱": "大葱", "生姜": "生姜", "大蒜": "大蒜", "茭瓜": "西葫芦",
}
_GOODS_PAT = "|".join(sorted(GOODS.keys(), key=len, reverse=True))


def get_bytes(url: str, retries: int = 3) -> bytes:
    last = None
    for a in range(retries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": UA})
            with urllib.request.urlopen(req, timeout=30, context=CTX) as r:
                return r.read()
        except Exception as exc:
            last = exc
            time.sleep(2 * (a + 1))
    raise last


def decode(raw: bytes) -> str:
    for enc in ("utf-8", "gbk", "gb18030"):
        try:
            return raw.decode(enc)
        except Exception:
            continue
    return raw.decode("utf-8", "ignore")


def extract_main(html: str) -> str:
    html = re.sub(r"<script.*?</script>", "", html, flags=re.S | re.I)
    html = re.sub(r"<style.*?</style>", "", html, flags=re.S | re.I)
    m = re.search(r'<div class="TRS_Editor">(.*?)</div>\s*</div>', html, re.S)
    if not m:
        m = re.search(r'<div class="TRS_Editor">(.*)', html, re.S)
    body = m.group(1) if m else html
    text = re.sub(r"<[^>]+>", "", body)
    text = text.replace("&nbsp;", " ").replace("\xa0", " ")
    return re.sub(r"\n{2,}", "\n", text).strip()


def parse_obs(text: str, article_date: str) -> list[dict]:
    obs = []

    def add(name, val, unit=""):
        obs.append({"article_date": article_date, "product_raw": name,
                    "product_standard": GOODS.get(name, name), "price_raw": val,
                    "unit_raw": f"元/{unit}" if unit.startswith(("5升", "500克", "500g", "公斤", "千克", "斤", "吨")) else (unit or "元/500克(默认)")})

    for mm in re.finditer(r"([\u4e00-\u9fff、]+(?:大豆油|花生油|猪肉|牛肉|羊肉|鸡肉|鸡蛋|蔬菜|带鱼|鲤鱼)[\u4e00-\u9fff、]*?)价格分别为\s*([\d.]+元(?:/5升)?(?:、[\d.]+元(?:/5升)?)+)", text):
        names = [n.strip() for n in re.split(r"[、，]", mm.group(1)) if n.strip()]
        prices = re.findall(r"([\d.]+)\s*元(?:/(5升))?", mm.group(2))
        for nm, (val, u) in zip(names, prices):
            add(nm, val, f"元/{u}" if u else "")
    for mm in re.finditer(
            rf"({_GOODS_PAT})[\u4e00-\u9fff]{{0,8}}?价格?(?:为|价)?\s*"
            r"(?:每500克（下同）|每500g（下同）|每500克|每500g|每公斤)?\s*"
            r"([\d.]+)\s*元(?:/(5升|500克|500g|公斤|千克|斤|吨))?", text):
        g = mm.groups()
        if len(g) != 3:
            continue
        name, val, unit = g
        add(name, val, unit or "")
    for m in re.finditer(r"(\d+)\s*种(?:蔬菜|监测蔬菜)[^。；]{0,15}?平均(?:零售)?价格为?\s*([\d.]+)\s*元", text):
        add(f"{m.group(1)}种蔬菜均价", m.group(2))
    return obs


def main(city: str) -> None:
    idx = json.load(open(ROOT / "data/raw/prices/lnfgw_fxyc_index.json", encoding="utf-8"))
    sel = [a for a in idx if city in a["title"]]
    raw_dir = ROOT / "data/raw" / "prices" / f"lnfgw_{city}"
    html_dir = raw_dir / "html"
    html_dir.mkdir(parents=True, exist_ok=True)
    print(f"[{city}] 命中文章 {len(sel)} 篇")

    seen, all_obs, meta = set(), [], []
    for a in sel:
        if a["url"] in seen:
            continue
        seen.add(a["url"])
        h = hashlib.md5(a["url"].encode()).hexdigest()[:12]
        f = html_dir / f"{h}.html"
        if not f.exists():
            try:
                f.write_bytes(get_bytes(a["url"]))
            except Exception as exc:
                print(f"  [FAIL] {a['date']} {a['title'][:28]}: {exc}")
                continue
            time.sleep(0.7)
        text = extract_main(decode(f.read_bytes()))
        obs = parse_obs(text, a["date"])
        all_obs.extend(obs)
        meta.append({"date": a["date"], "title": a["title"], "url": a["url"], "file": f.name, "obs": len(obs)})
        print(f"  [OK] {a['date']} {a['title'][:30]} 观测{len(obs)}")

    (raw_dir / "article_meta.json").write_text(json.dumps(meta, ensure_ascii=False, indent=1), encoding="utf-8")
    if all_obs:
        df = pd.DataFrame(all_obs)
        df["city"] = city
        df["source_id"] = f"SRC-LN-FGW-{city}-PRICE"
        df["source_name"] = f"辽宁省发改委价格监测局·{city}价格监测"
        df["source_url"] = "https://fgw.ln.gov.cn/fgw/xxgk/jgjc/fxyc/"
        df["fetch_time"] = datetime.now().isoformat(timespec="seconds")
        df["parser_version"] = "lnfgw_city_price_v1"
        df["quality_grade"] = "B"
        out = STAGING / f"{city}_price_lnfgw.csv"
        df.to_csv(out, index=False, encoding="utf-8-sig")
        print(f"\n[OK] {len(all_obs)} 条观测 → {out}")
        print(df.groupby("product_standard").size().sort_values(ascending=False).head(20).to_string())
    else:
        print(f"\n[{city}] 无价格观测")


if __name__ == "__main__":
    main(sys.argv[1])
