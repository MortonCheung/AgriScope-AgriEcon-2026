"""解析六城市/省级农产品价格原始数据 → 规范价格表。

三个来源，各自独立解析、各自保留原始字段：
  A. 沈阳市菜篮子平台（结构化 JSON，日度，城市级）—— 最高价值
     marketType: 1=批发价格 2=超市零售 3=集市零售
  B. 辽宁省发改委「每日价格」（HTML 表格，日度，省级：全省14市平均价）
     14 种农副产品 + 16 种蔬菜
  C. 大连市政府价格文章（叙述文本，周度/月度，城市级）

全部保留 raw 值，price_standard 为换算列（元/公斤），不做插值、不补值。
"""
from __future__ import annotations

import json
import re
from pathlib import Path

import pandas as pd

ROOT = next(p for p in Path(__file__).resolve().parents if (p / "AgriScope").is_dir() and (p / "data").is_dir())
RAW = ROOT / "data/raw" / "prices"
CURATED = ROOT / "city_data/reference/curated"
MARTS = ROOT / "city_data/reference/marts"
for d in (CURATED, MARTS):
    d.mkdir(parents=True, exist_ok=True)

MARKET_TYPE = {"1": "wholesale", "2": "retail", "3": "retail"}
MARKET_TYPE_CN = {"1": "批发价格", "2": "超市零售", "3": "集市零售"}


def to_per_kg(price: float, unit: str) -> float | None:
    """统一换算到元/公斤；无法判定的单位返回 None（不猜）。"""
    u = (unit or "").replace(" ", "")
    if u in ("元/500g", "元/500克", "元/500g克"):
        return price * 2.0
    if u in ("元/kg", "元/公斤", "元/千克"):
        return price
    if u == "元/5升" or u == "元/5L":
        return None      # 体积单位，不可换算为重量单价
    if u == "元/500ml":
        return None
    return None


# ---------------- A. 沈阳（结构化 JSON） ----------------
def parse_shenyang() -> pd.DataFrame:
    d = RAW / "shenyang_clz"
    if not d.exists():
        return pd.DataFrame()
    rows = []
    for f in sorted(d.glob("*.json")):
        try:
            j = json.loads(f.read_text(encoding="utf-8"))
        except Exception:
            continue
        ds = f.stem.split("_")[0]
        mt = f.stem.split("_mt")[-1]
        for it in (j.get("data") or []):
            price = it.get("price")
            try:
                price = float(price)
            except (TypeError, ValueError):
                continue
            unit = it.get("unit") or ""
            rows.append({
                "date": ds,
                "province": "辽宁省",
                "city": "沈阳",
                "district": it.get("regionName") or "",
                "market_id": None,
                "market_name": MARKET_TYPE_CN.get(mt, ""),
                "crop_raw": it.get("productName"),
                "variety": it.get("grade") or "",
                "price_type": MARKET_TYPE.get(mt, "unknown"),
                "price": price,
                "unit_raw": unit,
                "price_per_kg": to_per_kg(price, unit),
                "volume": it.get("volume"),
                "source_id": "SRC-SY-CLZ",
                "source_name": "沈阳市发展和改革委员会 菜篮子信息发布平台（价格监测局）",
                "source_url": "https://fgw.shenyang.gov.cn/wjgz/clzxxfbpt/",
                "raw_file": str(f.relative_to(ROOT)),
                "quality_grade": "A",
            })
    return pd.DataFrame(rows)


# ---------------- B. 辽宁省发改委（HTML 表格） ----------------
def parse_liaoning_fgw() -> pd.DataFrame:
    d = RAW / "liaoning_fgw_daily"
    if not d.exists():
        return pd.DataFrame()
    rows = []
    for f in sorted(d.glob("20*.html")):
        ds = f.stem
        try:
            t = f.read_bytes().decode("gbk", "replace")
        except Exception:
            continue
        # 定位标题行「名称/规格/单位/平均价格」之后的数据行
        for tb in re.findall(r"<table.*?</table>", t, re.S):
            trs = re.findall(r"<tr.*?</tr>", tb, re.S)
            for r in trs:
                cells = [re.sub(r"<[^>]+>", "", c).strip().replace("\n", "")
                         for c in re.findall(r"<t[dh].*?</t[dh]>", r, re.S)]
                if len(cells) < 4:
                    continue
                if cells[0] in ("名称", "品类", ""):
                    continue
                name, spec, unit, price_s = cells[0], cells[1], cells[2], cells[3]
                try:
                    price = float(price_s)
                except ValueError:
                    continue
                if price <= 0:
                    continue
                rows.append({
                    "date": ds,
                    "province": "辽宁省",
                    "city": None,          # 原文注明「全省十四个市平均价」→ 省级
                    "district": None,
                    "market_id": None,
                    "market_name": "辽宁省14市平均价",
                    "crop_raw": name,
                    "variety": spec,
                    "price_type": "retail",   # 栏目为「每日价格」监测均价
                    "price": price,
                    "unit_raw": unit,
                    "price_per_kg": to_per_kg(price, unit),
                    "volume": None,
                    "source_id": "SRC-LN-FGW-DAILY",
                    "source_name": "辽宁省发展和改革委员会 每日价格监测",
                    "source_url": "https://fgw.ln.gov.cn/fgw/xxgk/jgjc/mrjg/index.shtml",
                    "raw_file": str(f.relative_to(ROOT)),
                    "quality_grade": "A",
                })
    df = pd.DataFrame(rows)
    if not df.empty:
        df = df.drop_duplicates(subset=["date", "crop_raw", "variety"])
    return df


# ---------------- C. 大连（叙述文本） ----------------
DL_PAT = re.compile(r"([\u4e00-\u9fa5]{2,6}?)价格为每500克[（(]下同[）)]?\s*([0-9.]+)\s*元")
DL_PAT2 = re.compile(r"([\u4e00-\u9fa5]{2,6}?)价格为\s*([0-9.]+)\s*元")


def parse_dalian() -> pd.DataFrame:
    jl = RAW / "大连_articles" / "articles.jsonl"
    if not jl.exists():
        return pd.DataFrame()
    rows = []
    for line in jl.open(encoding="utf-8"):
        if not line.strip():
            continue
        r = json.loads(line)
        txt = r.get("raw_text", "")
        # 仅从明确写「价格为每500克(下同)」的段落提取，避免误抓百分比
        for m in DL_PAT.finditer(txt):
            name, val = m.group(1).strip(), m.group(2)
            try:
                price = float(val)
            except ValueError:
                continue
            if price <= 0:
                continue
            rows.append({
                "date": (r.get("publish_month") or "") + "-01",   # 仅精确到月，标注精度
                "province": "辽宁省",
                "city": "大连",
                "district": None,
                "market_id": None,
                "market_name": "大连市发展改革研究中心监测均价",
                "crop_raw": name,
                "variety": "",
                "price_type": "retail",
                "price": price,
                "unit_raw": "元/500克",
                "price_per_kg": price * 2,
                "volume": None,
                "source_id": "SRC-DL-ARTICLE",
                "source_name": "大连市人民政府 / 市发展改革研究中心 农副产品价格发布",
                "source_url": r.get("url", ""),
                "raw_file": r.get("raw_file", ""),
                "quality_grade": "B",
                "date_precision": "month",
                "title": r.get("title", ""),
            })
    df = pd.DataFrame(rows)
    if not df.empty:
        df = df.drop_duplicates(subset=["date", "crop_raw", "title"])
    return df


def main() -> None:
    frames = []
    sy = parse_shenyang()
    print(f"[OK] 沈阳（结构化日度）: {len(sy)} 条")
    if not sy.empty:
        frames.append(sy)
    ln = parse_liaoning_fgw()
    print(f"[OK] 辽宁省级（每日价格）: {len(ln)} 条")
    if not ln.empty:
        frames.append(ln)
    dl = parse_dalian()
    print(f"[OK] 大连（文章，月度精度）: {len(dl)} 条")
    if not dl.empty:
        frames.append(dl)

    if not frames:
        print("[WARN] 无价格数据")
        return
    df = pd.concat(frames, ignore_index=True)
    df.to_parquet(MARTS / "fact_price_city.parquet", index=False)
    df.to_csv(MARTS / "fact_price_city.csv", index=False, encoding="utf-8-sig")
    print(f"\n[OK] fact_price_city {len(df)} 条")
    print(df.groupby(["source_id", "city"], dropna=False).size().to_string())
    if not sy.empty:
        print("\n沈阳覆盖：")
        print(f"  日期 {sy['date'].min()} ~ {sy['date'].max()}，{sy['date'].nunique()} 天")
        print(f"  商品 {sy['crop_raw'].nunique()} 种，价格类型 {sorted(sy['price_type'].unique())}")
    if not ln.empty:
        print("\n省级覆盖：")
        print(f"  日期 {ln['date'].min()} ~ {ln['date'].max()}，{ln['date'].nunique()} 天")
        print(f"  商品 {ln['crop_raw'].nunique()} 种")


if __name__ == "__main__":
    main()
