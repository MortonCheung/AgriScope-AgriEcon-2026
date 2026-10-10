"""下载辽宁省发改委监测预警栏目中的大连价格监测文章并解析价格观测。

覆盖：
  - 大连市N月份主要商品价格监测情况综述（月度，24种农副产品）
  - 季度生产流通消费环节价格报告 / 专项分析
时间：2022-11 ~ 2024-10（列表枚举）+ 2021-2022（hex 文章，来自检索补充）
输出：
  data/raw/prices/lnfgw_dalian/html/{hash}.html
  city_data/reference/staging/dalian_price_monthly.csv（解析的月度价格观测）
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
RAW = ROOT / "data/raw" / "prices" / "lnfgw_dalian"
HTML_DIR = RAW / "html"
HTML_DIR.mkdir(parents=True, exist_ok=True)
STAGING = ROOT / "city_data/reference/staging"
STAGING.mkdir(parents=True, exist_ok=True)

CTX = ssl.create_default_context()
CTX.check_hostname = False
CTX.verify_mode = ssl.CERT_NONE
UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36"

# 补充的 2021-2022 hex 文章（经检索确认存在）
EXTRA = [
    ("2021-01-04", "大连市主要农副产品及药品价格稳定 供货充足", "42F3D119A58048ED8ADB928CD41329C6"),
    ("2021-01-04", "大连市主要农副产品价格总体环比微幅下降", "4BD06607097347D0B16082EA5C537150"),
    ("2021-01-05", "大连市节后肉蛋价格小幅下降 蔬菜价格小幅上涨", "A4ADC674B704452CA93C204C12137FB5"),
    ("2021-06-25", "大连地区5月份主要商品价格监测情况综述", "07F64ECFB4B94A73914E321A95184751"),
    ("2022-07-26", "大连市近期部分农副产品价格波动上行", "554CEF4C904146D3836E536B0D081243"),
]

GOODS = {
    "粳米": "粳米", "面粉": "面粉", "特一粉": "面粉", "散装大豆油": "大豆油",
    "桶装大豆油": "大豆油", "桶装花生油": "花生油", "花生油": "花生油",
    "猪肉": "猪肉", "猪精瘦肉": "猪精瘦肉", "牛肉": "牛肉", "羊肉": "羊肉",
    "鸡肉": "鸡肉", "鸡蛋": "鸡蛋", "鲤鱼": "鲤鱼", "带鱼": "带鱼",
    "牛奶": "牛奶", "大白菜": "大白菜", "白菜": "大白菜", "土豆": "土豆",
    "黄瓜": "黄瓜", "茄子": "茄子", "西红柿": "西红柿", "青椒": "青椒",
    "尖椒": "尖椒", "芸豆": "芸豆", "菠菜": "菠菜", "韭菜": "韭菜",
    "芹菜": "芹菜", "甘蓝": "甘蓝", "油菜": "油菜", "萝卜": "萝卜",
    "蒜薹": "蒜薹", "蒜苔": "蒜薹", "豆角": "豆角", "菜花": "菜花",
    "胡萝卜": "胡萝卜", "冬瓜": "冬瓜", "洋葱": "圆葱", "圆葱": "圆葱",
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


def parse_price_obs(text: str, period_date: str) -> list[dict]:
    """解析 大连月度综述中的价格模式（含列表式「分别为」）。"""
    obs = []

    def add(name, val, unit=""):
        unit = unit or "元/500克(默认)"
        obs.append({"period_date": period_date, "product_raw": name,
                    "product_standard": GOODS.get(name, name),
                    "price_raw": val, "unit_raw": f"元/{unit}" if unit.startswith(("5升", "500克", "500g", "公斤", "千克", "斤", "吨")) else unit})

    # 1) 列表式：猪肉、牛肉、鸡肉价格分别为11.25元、35.65元、9.77元
    for m in re.finditer(r"([\u4e00-\u9fff、]+(?:大豆油|花生油|猪肉|牛肉|羊肉|鸡肉|鸡蛋|蔬菜|带鱼|鲤鱼)[\u4e00-\u9fff、]*?)价格分别为\s*([\d.]+元(?:/5升)?(?:、[\d.]+元(?:/5升)?)+)", text):
        names = [n.strip() for n in re.split(r"[、，]", m.group(1)) if n.strip()]
        prices = re.findall(r"([\d.]+)\s*元(?:/(5升))?", m.group(2))
        for nm, (val, u) in zip(names, prices):
            add(nm, val, f"元/{u}" if u else "元/500克(默认)")
    # 2) 单商品：粳米零售价格为每500克（下同）3.25元；面粉价格为3.05元
    for mm in re.finditer(
            rf"({_GOODS_PAT})[\u4e00-\u9fff]{{0,8}}?价格?(?:为|价)?\s*"
            r"(?:每500克（下同）|每500g（下同）|每500克|每500g|每公斤)?\s*"
            r"([\d.]+)\s*元(?:/(5升|500克|500g|公斤|千克|斤|吨))?", text):
        g = mm.groups()
        if len(g) != 3:
            print(f"  [DEBUG] bad groups {len(g)} {g} ctx={text[max(0, mm.start()-30):mm.end()+30]!r}")
            continue
        name, val, unit = g
        if "价格分别为" in text[max(0, mm.start() - 30):mm.start()]:
            continue  # 已被列表式捕获
        add(name, val, f"元/{unit}" if unit else "元/500克(默认)")
    # 3) 蔬菜均价：N种蔬菜平均零售价格为X元 / 平均价格为X元
    for m in re.finditer(r"(\d+)\s*种(?:蔬菜|监测蔬菜)[^。；]{0,15}?平均(?:零售)?价格为?\s*([\d.]+)\s*元", text):
        add(f"{m.group(1)}种蔬菜均价", m.group(2))
    # 4) 上市量
    for m in re.finditer(r"蔬菜批发市场[^。；]{0,12}上市量为\s*([\d.]+)\s*(吨)", text):
        add("蔬菜上市量", m.group(1), m.group(2))
    return obs


def main() -> None:
    idx = json.load(open(ROOT / "data/raw/prices/lnfgw_fxyc_index.json", encoding="utf-8"))
    dalian = [a for a in idx if "大连" in a["title"]]
    # 补充 hex 文章
    for date, title, hexid in EXTRA:
        dalian.append({"date": date, "title": title,
                       "url": f"https://fgw.ln.gov.cn/fgw/xxgk/jgjc/fxyc/{hexid}/index.shtml"})
    seen = set()
    arts = []
    for a in dalian:
        if a["url"] in seen:
            continue
        seen.add(a["url"])
        arts.append(a)
    print(f"待下载 {len(arts)} 篇大连价格文章")

    all_obs = []
    meta = []
    for i, a in enumerate(arts, 1):
        h = hashlib.md5(a["url"].encode()).hexdigest()[:12]
        f = HTML_DIR / f"{h}.html"
        if not f.exists():
            try:
                raw = get_bytes(a["url"])
                f.write_bytes(raw)
            except Exception as exc:
                print(f"  [FAIL] {a['date']} {a['title'][:30]}: {exc}")
                continue
            time.sleep(0.7)
        html = decode(f.read_bytes())
        text = extract_main(html)
        obs = parse_price_obs(text, a["date"])
        all_obs.extend(obs)
        meta.append({"date": a["date"], "title": a["title"], "url": a["url"],
                     "file": f.name, "obs_count": len(obs)})
        if i % 10 == 0 or i == len(arts):
            print(f"  进度 {i}/{len(arts)} | 累计观测 {len(all_obs)}")

    (RAW / "article_meta.json").write_text(json.dumps(meta, ensure_ascii=False, indent=1), encoding="utf-8")
    if all_obs:
        df = pd.DataFrame(all_obs)
        df["city"] = "大连"
        df["source_id"] = "SRC-LN-FGW-DL-MONTHLY"
        df["source_name"] = "辽宁省发改委价格监测局·大连市价格监测综述"
        df["source_url"] = "https://fgw.ln.gov.cn/fgw/xxgk/jgjc/fxyc/"
        df["fetch_time"] = datetime.now().isoformat(timespec="seconds")
        df["parser_version"] = "lnfgw_dalian_v1"
        df["quality_grade"] = "B"
        df.to_csv(STAGING / "dalian_price_monthly.csv", index=False, encoding="utf-8-sig")
        print(f"\n[OK] 解析观测 {len(all_obs)} 条 → city_data/reference/staging/dalian_price_monthly.csv")
        print(f"商品种类: {df['product_standard'].nunique()}")
        print(df.groupby("product_standard").size().sort_values(ascending=False).head(25).to_string())


if __name__ == "__main__":
    main()
