"""辽宁省农业农村厅「主要蔬菜产品价格简讯」——市场级节点解析（补齐旧格式）。

背景：
  蔬菜简讯存在两种正文格式：
    (A) 新格式（约2024起，区县级）：
        「价格较高的地区是朝阳双塔区5.00元/公斤，较低的地区是…」
        → 已由 collectors/lnnync_veg_weekly.py 解析入库。
    (B) 旧格式（约2021–2023，市场级）：
        「价格较高的地区是本溪市大河批发市场，7.00元/公斤，
           较低的地区是大连庄河市蔬菜批发市场，2.80元/公斤。」
        注意：市场名与价格之间**有逗号**，且个别为「元/公斤」缺「元」（如 0.70/公斤）。
        → 旧正则 [^，。]{2,12}? 直接跟数字，无法匹配带逗号的旧格式，
          导致 172 篇含「批发市场」的文章只解析出约 11 行。

本脚本只做一件事：
  复用 data/raw/prices/lnnync_veg_weekly/html/ 下**已下载的原始 HTML**，
  用兼容两种格式的宽松正则，抽取其中的**市场级节点**（名称以「市场」结尾），
  写入 city_data/reference/staging/lnnync_veg_market_nodes.csv。

  南关岭 = 大连果菜批发市场 = 大连棉麻有限公司果菜批发市场（甘井子区南关岭西洼街186号），
  因此「大连果菜批发市场」节点即南关岭市场观测；「大连双兴批发市场」为同市另一批发市场。

口径声明（与全项目一致）：
  - 市场级节点为**最高价/最低价地区**，非连续序列，严禁当作大连市价或南关岭连续价使用；
  - 不改写、不插值、不编造；仅原样解析。
"""
from __future__ import annotations

import hashlib
import json
import re
import html as _html
from pathlib import Path

import pandas as pd

ROOT = next(p for p in Path(__file__).resolve().parents if (p / "AgriScope").is_dir() and (p / "data").is_dir())
RAW = ROOT / "data/raw" / "prices" / "lnnync_veg_weekly"
HTML = RAW / "html"
STAGING = ROOT / "city_data/reference/staging"

# 兼容两种格式：市场名与价格间逗号可选；单位「元/公斤」的「元」可选
HI = re.compile(r"价格较高的地区是([^，。；]{2,24}?)[，,]?\s*([\d.]+)\s*元?\s*/\s*公斤")
LO = re.compile(r"较低的地区是([^，。；]{2,24}?)[，,]?\s*([\d.]+)\s*元?\s*/\s*公斤")
AVG = re.compile(r"批发均价为([\d.]+)\s*元?\s*/\s*公斤")


def clean(t: str) -> str:
    b = re.sub(r"<(script|style)[^>]*>.*?</\1>", "", t, flags=re.S)
    b = re.sub(r"<[^>]+>", " ", b)
    b = _html.unescape(b)
    return re.sub(r"\s+", " ", b)


def is_market(name: str) -> bool:
    n = re.sub(r"\s+", "", name)
    return n.endswith("市场") and ("地区" not in n) and ("价格" not in n) and len(n) <= 14


def norm_market(name: str) -> str:
    n = re.sub(r"\s+", "", name)
    n = re.sub(r"(批发市场)+", "批发市场", n)
    return n


def norm_crop(name: str) -> str:
    return re.sub(r"\s+", "", name)


def parse(txt: str, meta: dict, url: str) -> list[dict]:
    rows: list[dict] = []
    # 以【品种】切块
    idx = [m.start() for m in re.finditer(r"【[^】]+】", txt)]
    idx.append(len(txt))
    for i in range(len(idx) - 1):
        seg = txt[idx[i]:idx[i + 1]]
        cm = re.match(r"【([^】]+)】", seg)
        if not cm:
            continue
        crop = norm_crop(cm.group(1).strip())
        avg_m = AVG.search(seg)
        for kind, rx in (("market_extremum_high", HI), ("market_extremum_low", LO)):
            m = rx.search(seg)
            if not m:
                continue
            name = norm_market(m.group(1).strip())
            if not is_market(name):
                continue
            rows.append({
                "date": meta.get("date", ""),
                "iso_year": meta.get("iso_year"),
                "iso_week": meta.get("iso_week"),
                "crop": crop,
                "record_kind": kind,
                "market": name,
                "price": float(m.group(2)),
                "unit": "元/公斤",
                "province_wholesale_avg": float(avg_m.group(1)) if avg_m else None,
                "source_name": "辽宁省农业农村厅 主要蔬菜产品价格简讯",
                "source_url": url,
                "quality_grade": "B",
                "note": "省级简讯市场级极值节点（最高/最低价地区）；非连续价格，严禁当市场连续价使用",
            })
    return rows


def main() -> None:
    index = json.loads((RAW / "article_index.json").read_text(encoding="utf-8"))
    print(f"[OK] 文章索引 {len(index)} 篇")
    rows: list[dict] = []
    used = 0
    for it in index:
        url = it["url"]
        aid = hashlib.md5(url.encode()).hexdigest()[:16]
        f = HTML / f"{aid}.html"
        if not f.exists():
            continue
        used += 1
        rows += parse(clean(f.read_text(encoding="utf-8", errors="replace")), it, url)
    print(f"[OK] 实际读取原始 HTML {used} 篇，抽出市场级节点 {len(rows)} 行")
    if not rows:
        print("[WARN] 无市场级节点")
        return
    df = pd.DataFrame(rows)
    df = df.drop_duplicates(subset=["date", "crop", "record_kind", "market"])
    df = df.sort_values(["date", "crop", "record_kind"]).reset_index(drop=True)
    out = STAGING / "lnnync_veg_market_nodes.csv"
    df.to_csv(out, index=False, encoding="utf-8-sig")
    print(f"[OK] 写入 {out.name}：{len(df)} 行")
    print("\n按市场统计：")
    print(df.groupby("market").agg(n=("price", "size"),
                                   crops=("crop", "nunique"),
                                   d0=("date", "min"), d1=("date", "max")).to_string())
    ng = df[df["market"].str.contains("大连果菜批发市场")]
    print(f"\n大连果菜批发市场(=南关岭)节点：{len(ng)} 行")
    if len(ng):
        print(ng[["date", "crop", "record_kind", "price"]].to_string(index=False))


if __name__ == "__main__":
    main()
