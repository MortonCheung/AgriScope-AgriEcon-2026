"""解析锦州价格图片 OCR 文本 → 结构化价格。

==========================================================================
【数据来源与不可回避的三个坑】（务必先读）
==========================================================================
锦州菜篮子每日发布文章，价格表以 PNG 图片发布。全量核对结果：

坑 1 —— **图片非每日更新**
    1590 篇日度文章 → 唯一图片仅 598 张，(图,日期) 对 1586 个，平均复用 2.65 天。
    2020 年为真日度(1.00x)，2021 年起约每 3 天换一张表(2.7x~3.6x)。
    → 本脚本按**唯一图**解析一次，再前向展开到引用日期，并用 is_repeat 标记重复日。
    → 绝不可当成"每天独立观测"：那会把同一价格复制到连续多日，使波动率被严重低估。

坑 2 —— **版式三代不同，口径不可混用**
    版式A(2020-07~2021初): 「类别 | 品种 | <日期>」→ 仅**单列价格**(全市均价口径)
    版式B(2021~2022):      3 监测点，OCR 错字密集(西椅/瓜/可萄/谷燕/鸿盛)
    版式C(2022末~至今):    3 监测点，质量最好(香橙源超市/科技路市场/V+优果超市)
    → 用 price_scope 区分 'city_avg' / 'market'；监测点名做归一化。

坑 3 —— **早期存在小数点丢失**
    例：版式A 中「西红柿 25」「菜花 25」，而全期该品种单位数在 2~5 元/斤。
    → 用**同品种全期单位数**做量级校验，疑似丢小数点者 ÷10 并标 decimal_fixed=True。

==========================================================================
质量等级 quality_grade = B（机器 OCR 转录，非官方结构化数据）
原图全部保留在 data/raw/prices/jinzhou_deep/images/，任何可疑值必须回原图核对。
单位：元/斤 = 元/500g → price_per_kg = ×2
"""
from __future__ import annotations

import json
import re
import statistics
from collections import Counter, defaultdict
from pathlib import Path

import pandas as pd

ROOT = next(p for p in Path(__file__).resolve().parents if (p / "AgriScope").is_dir() and (p / "data").is_dir())
RAW = ROOT / "data/raw" / "prices" / "jinzhou_deep"
OCR = RAW / "ocr"
STAGING = ROOT / "city_data/reference/staging"
MARTS = ROOT / "city_data/reference/marts"
STAGING.mkdir(parents=True, exist_ok=True)
MARTS.mkdir(parents=True, exist_ok=True)

# ---------------------------------------------------------------- 归一化表
# 类别列（表格左侧合并单元格，OCR 后散落成独立行）
CATEGORY_TOKENS = set("""蔬菜 水果 肉蛋奶 水产品 蔬 菜 水 果 肉 蛋 奶 产 类別 炎别 类别 品
禽 海鲜 水产 鲜肉 果菜 菜类 果类 肉类 蛋类 奶类 水產 類別""".split())

# 品种归一：早期名 / 后期名 / OCR 变体 → 标准名
CROP_CANON = {
    # 蔬菜
    "豆角": "豆角", "架豆王": "架豆王", "豆王": "架豆王",
    "西红柿": "西红柿", "西 椅": "西红柿", "西红杮": "西红柿", "蕃茄": "西红柿",
    "黄瓜": "黄瓜", "尖椒": "尖椒", "青椒": "尖椒",
    "土豆": "土豆", "新土豆": "土豆",
    "茄子（紫）": "紫茄子", "紫茄子": "紫茄子", "茄子": "紫茄子", "茄子(紫)": "紫茄子",
    "大白菜": "大白菜", "白菜": "大白菜", "芹菜": "芹菜", "菜花": "菜花",
    "胡萝卜": "胡萝卜", "胡萝": "胡萝卜", "胡萝 ": "胡萝卜",
    "大葱": "大葱", "葱": "大葱",
    # 水果
    "苹果": "苹果", "苹果（富士）": "苹果", "梨": "梨", "梨 ": "梨",
    "葡萄": "葡萄", "柑橘": "柑橘", "桔子": "柑橘", "橘子": "柑橘",
    "香蕉": "香蕉", "蕉": "香蕉",
    # 肉蛋奶
    "鲜猪肉": "猪肉", "五花猪肉": "猪肉", "猪肉": "猪肉",
    "鲜牛肉": "牛肉", "牛肉": "牛肉",
    "鲜羊肉": "羊肉", "羊肉": "羊肉",
    "鲜鸡肉": "鸡肉", "鸡胸肉": "鸡肉", "鸡肉": "鸡肉",
    "鸡蛋": "鸡蛋", "鸿盛": "鸡蛋",          # 2021 期 OCR 严重错字，已在原图核对
    "牛奶": "牛奶", "鲜牛奶": "牛奶",
    # 水产品
    "带鱼": "带鱼", "鲤鱼": "鲤鱼", "燕鱼": "燕鱼",
}

# 监测点归一（含 2021 期错字；均已在原图核对）
MARKET_CANON = {
    "香橙源超市": "香橙源超市", "香橙源生鲜超市": "香橙源超市", "各橙源生鲜超市": "香橙源超市",
    "香橙源生鮮超市": "香橙源超市", "香橙源生鲜起市": "香橙源超市", "香橙源": "香橙源超市",
    "科技路市场": "科技路市场", "科技市场": "科技路市场", "科技路": "科技路市场",
    "V+优果超市": "V+优果超市", "V+优果生鲜超市": "V+优果超市", "V+优超市": "V+优果超市",
    "+优果超市": "V+优果超市", "优果超市": "V+优果超市", "V＋优果超市": "V+优果超市",
    "果真新鲜": "果真新鲜", "果袌新鲜": "果真新鲜", "果真新鮮": "果真新鲜", "果真": "果真新鲜",
}

NULLISH = {"无", "？", "?", "-", "—", "/", "无货", "", "一", "－"}


def clean_num(s: str) -> float | None:
    """清洗 OCR 数字：去空格、去尾部句点、剥离非数字字符。"""
    if s is None:
        return None
    t = str(s).strip()
    if t in NULLISH:
        return None
    t = t.replace(" ", "").replace("　", "")
    t = t.rstrip(".。、,，")
    t = re.sub(r"[^\d.]", "", t)
    if not t or t == ".":
        return None
    # 多个小数点 → 只保留第一个
    if t.count(".") > 1:
        head, _, tail = t.partition(".")
        t = head + "." + tail.replace(".", "")
    try:
        v = float(t)
    except ValueError:
        return None
    return v if v > 0 else None


def crop_of(cell: str) -> tuple[str, str] | None:
    """从单元格提取品种：返回 (标准名, 原始名) 或 None。"""
    m = re.match(r"^([\u4e00-\u9fa5A-Za-z（）()＋+ ]{1,12}?)\s*[（(]?\s*元?\s*[/／]?\s*(?:斤|袋|个|盒|kg|KG|克|g)?\s*[）)〉]?\s*$", cell)
    if not m:
        return None
    raw = m.group(1).strip()
    if not raw or raw in CATEGORY_TOKENS:
        return None
    # 精确匹配优先，其次包含匹配（解决「胡萝 」这类残缺）
    if raw in CROP_CANON:
        return CROP_CANON[raw], raw
    for k, v in CROP_CANON.items():
        if k and (raw == k or raw.startswith(k) or k.startswith(raw)) and len(raw) >= 2:
            return v, raw
    return None


def market_of(cell: str) -> str | None:
    c = cell.strip()
    if c in MARKET_CANON:
        return MARKET_CANON[c]
    for k, v in MARKET_CANON.items():
        if k in c or c in k:
            if len(c) >= 2:
                return v
    return None


def detect_header(parts: list[str]) -> tuple[list[str] | None, str]:
    """识别表头。

    返回 (监测点列表, 版式标记)：
      (['香橙源超市','科技路市场','V+优果超市'], 'C')   —— 版式B/C
      ([], 'A')                                          —— 版式A（仅全市均价，第3列是日期）
      (None, '')                                         —— 非表头行
    """
    if not any(("品种" in p) or ("品 种" in p) for p in parts):
        return None, ""
    tail = parts[1:]
    # 去掉"品种"本身
    tail = [p for p in tail if "品种" not in p]
    if tail and re.search(r"\d{4}\s*年|\d{1,2}\s*月|日$", tail[0]):
        return [], "A"          # 第3列是日期 → 单列均价版式
    mk = [market_of(p) for p in tail]
    mk = [m for m in mk if m]
    if len(mk) >= 2:
        return mk, "C"
    # 表头没认全，但确实是表头行：用出现过的监测点，缺位留待数据行补齐
    if mk:
        return mk, "C"
    return [], "A"


def parse_image(txt: str) -> tuple[list[dict], dict]:
    """解析单张图的 OCR 文本 → [(market, crop_canon, crop_raw, price, scope)]"""
    rows: list[dict] = []
    stats = Counter()
    markets: list[str] = []
    layout = ""
    for ln in txt.split("\n"):
        if not ln.strip():
            continue
        parts = [p.strip() for p in ln.split("\t") if p.strip()]
        if not parts:
            continue

        hdr, lay = detect_header(parts)
        if hdr is not None:
            if lay == "C" and len(hdr) >= 2:
                markets, layout = hdr, "C"
            elif lay == "A" and not markets:
                layout = layout or "A"
            continue

        # 类别行（单独出现的「蔬」「菜」「肉蛋奶」等）→ 跳过
        if len(parts) == 1 and parts[0] in CATEGORY_TOKENS:
            continue

        # 数据行：定位品种单元格
        crop_cell, nums_raw = None, []
        if parts[0] in CATEGORY_TOKENS and len(parts) >= 2:
            crop_cell, nums_raw = parts[1], parts[2:]
        else:
            crop_cell, nums_raw = parts[0], parts[1:]

        got = crop_of(crop_cell)
        if not got:
            stats["品种未识别"] += 1
            continue
        canon, raw = got
        nums = [clean_num(p) for p in nums_raw]
        nums = [n for n in nums if n is not None]
        if not nums:
            stats["无有效价格"] += 1
            continue

        scope = "market" if markets else "city_avg"
        if markets:
            if len(nums) == len(markets):
                pairs = list(zip(markets, nums))
            else:
                # 列数不匹配：按序左对齐，另记 warning（不丢弃，但下游需谨慎）
                stats["列数不匹配"] += 1
                pairs = list(zip(markets, nums))
        else:
            # 版式A：单列均价（可能 OCR 拆出多列，取第一个非空）
            pairs = [("全市均价", nums[0])]

        for mk, v in pairs:
            rows.append({"market_name": mk, "crop": canon, "crop_raw": raw,
                         "price": v, "price_scope": scope, "layout": layout or "A"})
    return rows, dict(stats)


def fix_decimals(recs: list[dict]) -> tuple[int, int]:
    """修正 OCR 小数点丢失。

    实测两种形态（均已回原图确认）：
      ÷10  型：「2.5」→「25」        —— 主要出现在早期版式A
      ÷100 型：「1.69」→「169」      —— 单元格内小数点被吞，数字连写
    判据：以**同品种全期中位数**为锚。若值 > 中位数×5，依次尝试 ÷10/÷100/÷1000，
    取第一个落回 [中位数×0.3, 中位数×3] 的候选。
    仍无法归位的离群值保留原值但标 decimal_suspect=True，下游用 price_usable 过滤。
    """
    by_crop: dict[str, list[float]] = defaultdict(list)
    for r in recs:
        by_crop[r["crop"]].append(r["price"])
    med = {c: statistics.median(vs) for c, vs in by_crop.items() if len(vs) >= 20}

    fixed = suspect = 0
    for r in recs:
        r["decimal_fixed"] = False
        r["decimal_suspect"] = False
        m = med.get(r["crop"])
        if not m:
            continue
        v = r["price"]
        if v <= m * 5:
            continue
        best = None
        for f in (10, 100, 1000):
            cand = v / f
            if m * 0.3 <= cand <= m * 3:
                best = round(cand, 4)
                break
        if best is not None:
            r["price"] = best
            r["decimal_fixed"] = True
            fixed += 1
        else:
            r["decimal_suspect"] = True
            suspect += 1
    return fixed, suspect


def main() -> None:
    groups = json.loads((RAW / "image_groups.json").read_text(encoding="utf-8"))
    print(f"唯一图片 {len(groups)} 张")

    recs: list[dict] = []
    warn_total = Counter()
    no_txt = 0
    for g in groups:
        iid = g["image_id"]
        f = OCR / f"{iid}.txt"
        if not f.exists():
            no_txt += 1
            continue
        rows, st = parse_image(f.read_text(encoding="utf-8", errors="replace"))
        for k, v in st.items():
            warn_total[k] += v
        for r in rows:
            recs.append({**r, "image_id": iid,
                         "date_first": g["date_first"], "date_last": g["date_last"],
                         "n_days_referenced": g["n_days_referenced"],
                         "suspect_span": g["suspect_span"],
                         "dates": g["dates"]})

    print(f"解析记录 {len(recs)} 条（按唯一图，未展开日期）")
    print(f"缺失 OCR 文本 {no_txt} 张；解析告警 {dict(warn_total)}")

    fixed, suspect = fix_decimals(recs)
    print(f"小数点修正 {fixed} 条；仍疑似异常 {suspect} 条")

    # ---- 展开到引用日期（前向填充语义），并标记重复日
    expanded = []
    for r in recs:
        for d in r["dates"]:
            expanded.append({
                "date": d,
                "is_repeat": d != r["date_first"],
                "image_id": r["image_id"],
                "n_days_referenced": r["n_days_referenced"],
                "city": "锦州", "district": None, "geo_level": r["price_scope"],
                "market_name": r["market_name"],
                "crop": r["crop"], "crop_raw": r["crop_raw"],
                "price": r["price"], "unit_raw": "元/斤",
                "price_per_kg": round(r["price"] * 2, 4),
                "price_type": "retail", "price_scope": r["price_scope"],
                "layout": r["layout"],
                "frequency": "irregular_official",   # 官方不定期更新（非每日）
                "source_id": "SRC-JZ-CLZ-OCR",
                "source_name": "锦州市菜篮子信息发布平台（图片经 macOS Vision OCR 转录）",
                "quality_grade": "B",
                "decimal_fixed": r["decimal_fixed"],
                "decimal_suspect": r["decimal_suspect"],
                "suspect_span": r["suspect_span"],
            })
    df = pd.DataFrame(expanded).drop_duplicates(
        subset=["date", "market_name", "crop"])
    df = df.sort_values(["date", "market_name", "crop"]).reset_index(drop=True)
    # price_usable：建模可用值。量级异常的记录置空，宁缺勿错。
    #   高端：decimal_suspect（÷10/÷100 都无法归位的离群）
    #   低端：低于同品种中位数 1/6（实测 3 条，疑 OCR 把 1.19 读成 0.19）
    med = df.groupby("crop")["price"].median()
    ratio = df["price"] / df["crop"].map(med)
    df["outlier_low"] = ratio < (1 / 6)
    df["outlier_high"] = df["decimal_suspect"]
    df["price_usable"] = df["price"].where(~(df["outlier_low"] | df["outlier_high"]), other=None)

    df.to_csv(STAGING / "jinzhou_price_ocr.csv", index=False, encoding="utf-8-sig")
    df.to_parquet(MARTS / "fact_price_jinzhou_daily.parquet", index=False)
    print(f"\n[OK] fact_price_jinzhou_daily: {len(df)} 条")
    print(f"     日期 {df['date'].min()} ~ {df['date'].max()}，{df['date'].nunique()} 天")
    print(f"     唯一图 {df['image_id'].nunique()} 张；重复日记录 {int(df['is_repeat'].sum())} 条")
    print(f"     price_usable 非空 {int(df['price_usable'].notna().sum())} 条"
          f"（置空 {int(df['price_usable'].isna().sum())} 条：高端 {int(df['outlier_high'].sum())}"
          f" + 低端 {int(df['outlier_low'].sum())}）")
    print(f"     监测点 {sorted(df['market_name'].unique())}")
    print(f"     品种 {df['crop'].nunique()} 种：{sorted(df['crop'].unique())}")
    print(f"     口径 {df.groupby('price_scope').size().to_dict()}")
    print(f"     版式 {df.groupby('layout').size().to_dict()}")

    # ---- 每张唯一图一条（去重视图，供建模直接用，避免重复观测偏误）
    one = df[~df["is_repeat"]].copy()
    one.to_csv(STAGING / "jinzhou_price_ocr_unique.csv", index=False, encoding="utf-8-sig")
    print(f"\n[OK] 去重视图(每图首次发布日)：{len(one)} 条")


if __name__ == "__main__":
    main()
