"""下载大连发改委周度价格监测文章原始 HTML 并解析为结构化周度价格。

输入: data/raw/prices/dalian_dfgw_weekly/article_index.json
输出:
  data/raw/prices/dalian_dfgw_weekly/html/{hash}.html     原始HTML
  data/raw/prices/dalian_dfgw_weekly/article_meta.json    文章元数据+提取的价格观测
  city_data/reference/staging/dalian_price_weekly.csv                    结构化周度价格观测
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
RAW = ROOT / "data/raw" / "prices" / "dalian_dfgw_weekly"
HTML_DIR = RAW / "html"
HTML_DIR.mkdir(parents=True, exist_ok=True)
STAGING = ROOT / "city_data/reference/staging"
STAGING.mkdir(parents=True, exist_ok=True)

CTX = ssl.create_default_context()
CTX.check_hostname = False
CTX.verify_mode = ssl.CERT_NONE
UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")


def http_get(url: str, retries: int = 3, timeout: int = 30) -> str:
    last = None
    for a in range(retries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": UA})
            with urllib.request.urlopen(req, timeout=timeout, context=CTX) as r:
                return r.read().decode("utf-8", "ignore")
        except Exception as exc:
            last = exc
            time.sleep(2 * (a + 1))
    raise last


def extract_text(html: str) -> str:
    """抽取文章正文文本（去掉 script/style/tag）。"""
    html = re.sub(r"<script.*?</script>", "", html, flags=re.S | re.I)
    html = re.sub(r"<style.*?</style>", "", html, flags=re.S | re.I)
    # 主内容区域
    m = re.search(r'id="Zoom"[^>]*>(.*?)</div>', html, re.S)
    if not m:
        m = re.search(r'class="article"[^>]*>(.*?)</div>', html, re.S)
    body = m.group(1) if m else html
    text = re.sub(r"<[^>]+>", "\n", body)
    text = re.sub(r"&nbsp;?", " ", text)
    text = re.sub(r"\n{2,}", "\n", text)
    return text.strip()


# 大连周报正文中出现的商品名（规范化，含别名）
GOODS = {
    "粳米": "粳米", "面粉": "面粉", "特一粉": "面粉", "桶装花生油": "花生油", "花生油": "花生油",
    "桶装大豆油": "大豆油", "大豆油": "大豆油", "猪精瘦肉": "猪精瘦肉", "猪肉": "猪肉",
    "牛肉": "牛肉", "羊肉": "羊肉", "鸡肉": "鸡肉", "鸡蛋": "鸡蛋", "白条鸡": "白条鸡",
    "大白菜": "大白菜", "白菜": "大白菜", "土豆": "土豆", "黄瓜": "黄瓜", "茄子": "茄子",
    "西红柿": "西红柿", "番茄": "西红柿", "青椒": "青椒", "尖椒": "尖椒", "芸豆": "芸豆",
    "菠菜": "菠菜", "韭菜": "韭菜", "芹菜": "芹菜", "甘蓝": "甘蓝", "油菜": "油菜",
    "青萝卜": "青萝卜", "萝卜": "萝卜", "冬瓜": "冬瓜", "蒜薹": "蒜薹", "蒜苔": "蒜薹",
    "豆角": "豆角", "圆葱": "圆葱", "葱头": "圆葱", "西葫芦": "西葫芦", "茭瓜": "西葫芦",
    "生菜": "生菜", "大葱": "大葱", "生姜": "生姜", "大蒜": "大蒜", "菜花": "菜花",
}
_GOODS_PAT = "|".join(sorted(GOODS.keys(), key=len, reverse=True))


def parse_observations(text: str, article_date: str) -> list[dict]:
    """从周报正文解析 商品→价格 观测。

    正文格式：
      「粳米价格为每500克（下同）3.08元…；桶装花生油价格为152.39元/5升…
       鸡蛋价格为5.91元…；监测的15种蔬菜…平均价格为3.02元」
    """
    obs = []

    def add(name, val, unit=""):
        obs.append({
            "article_date": article_date,
            "product_raw": name,
            "product_standard": GOODS.get(name, name),
            "price_raw": val,
            "currency": "元",
            "unit_raw": f"元/{unit}" if unit.startswith(("5升", "500克", "500g", "公斤", "千克", "斤", "吨")) else (unit or "元/500克（周报默认）"),
        })

    # 1) 带单位的价格：{商品}价格为…数字元/单位（支持每500克（下同））
    pat1 = re.compile(
        rf"({_GOODS_PAT})[\u4e00-\u9fff]{{0,8}}?价格?(?:为|价)?\s*"
        r"(?:每500克（下同）|每500g（下同）|每500克|每500g|每公斤)?\s*"
        r"([\d.]+)\s*元(?:/(5升|500克|500g|公斤|千克|斤|袋|吨))?"
    )
    for mm in pat1.finditer(text):
        g = mm.groups()
        if len(g) != 3:
            continue
        name, val, unit = g
        add(name, val, unit or "")
    # 2) 平均价：平均价格为3.02元 / 平均批发价格
    pat2 = re.compile(r"([\d.]+)\s*种(?:蔬菜|商品)?[^。；]{0,20}?平均(?:批发)?价格为?\s*([\d.]+)\s*元")
    for m in pat2.finditer(text):
        n, val = m.groups()
        add(f"{n}种蔬菜均价", val)
    return obs


def main() -> None:
    idx = json.load(open(RAW / "article_index.json", encoding="utf-8"))
    # 按 URL 去重
    seen, arts = set(), []
    for a in idx:
        if a["url"] in seen:
            continue
        seen.add(a["url"])
        arts.append(a)

    meta, all_obs = [], []
    for i, a in enumerate(arts, 1):
        h = hashlib.md5(a["url"].encode()).hexdigest()[:12]
        f = HTML_DIR / f"{h}.html"
        if not f.exists():
            try:
                html = http_get(a["url"])
                f.write_text(html, encoding="utf-8")
            except Exception as exc:
                print(f"  [FAIL] {a['date']} {a['title'][:30]}: {exc}")
                continue
            time.sleep(0.8)
        text = extract_text(f.read_text(encoding="utf-8"))
        obs = parse_observations(text, a["date"])
        all_obs.extend(obs)
        meta.append({**a, "file": f.name, "obs_count": len(obs)})
        if i % 10 == 0:
            print(f"  进度 {i}/{len(arts)} | 累计观测 {len(all_obs)}")

    (RAW / "article_meta.json").write_text(
        json.dumps(meta, ensure_ascii=False, indent=1), encoding="utf-8")

    if all_obs:
        df = pd.DataFrame(all_obs)
        df["product_standard"] = df["product_raw"]
        df["city"] = "大连"
        df["source_id"] = "SRC-DL-FGW-WEEKLY"
        df["source_name"] = "大连市发展改革研究中心·农副产品价格监测周报"
        df["source_url"] = "https://www.dl.gov.cn/col/col1190/index.html"
        df["fetch_time"] = datetime.now().isoformat(timespec="seconds")
        df["parser_version"] = "dalian_price_weekly_v1"
        df["quality_grade"] = "B"
        df.to_csv(STAGING / "dalian_price_weekly.csv", index=False, encoding="utf-8-sig")
        print(f"\n[OK] 解析观测 {len(all_obs)} 条 → city_data/reference/staging/dalian_price_weekly.csv")
        print(f"商品种类: {df['product_raw'].nunique()}")
        print(df.groupby("product_raw").size().sort_values(ascending=False).head(30).to_string())


if __name__ == "__main__":
    main()
