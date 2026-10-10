"""标准化：行政区划 / 产品名 / 单位 / 涨跌百分比。

核心铁律（施工手册第十二、十三、十八节）：
- location_raw 永远保留原文，标准化只是新增字段，绝不覆盖原文。
- 沈北新区等市辖区只能归属沈阳市，绝不能被提升为独立城市。
- 原始价格与原始单位永久保留；standard_price 只是额外换算列。
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

import yaml

from . import PROJECT_ROOT

CONFIG_DIR = PROJECT_ROOT / "config"

with (CONFIG_DIR / "locations.yaml").open(encoding="utf-8") as fh:
    LOC = yaml.safe_load(fh)
with (CONFIG_DIR / "products.yaml").open(encoding="utf-8") as fh:
    PROD = yaml.safe_load(fh)

PROVINCE: str = LOC["province"]
CITIES: dict = LOC["cities"]
MARKET_SUFFIXES: list[str] = sorted(LOC.get("market_suffixes", []), key=len, reverse=True)
REGION_SUFFIXES: list[str] = LOC.get("region_suffixes", [])
UNIT_CONVERSION: dict = PROD.get("unit_conversion", {})

# ---- 行政区划索引 -------------------------------------------------------
# city_lookup: 城市全名与别名 → 标准市名（"沈阳市"/"沈阳" → "沈阳市"）
CITY_LOOKUP: dict[str, str] = {}
for city, meta in CITIES.items():
    CITY_LOOKUP[city] = city
    for alias in meta.get("aliases", []) or []:
        CITY_LOOKUP[alias] = city
CITY_KEYS: list[str] = sorted(CITY_LOOKUP, key=len, reverse=True)
CITY_STEMS: list[str] = sorted({c[:-1] if c.endswith("市") else c for c in CITIES}, key=len, reverse=True)

# county_lookup: (市名, 区县全名/去后缀名) → 标准区县名
COUNTY_LOOKUP: dict[tuple[str, str], str] = {}
COUNTY_TO_CITY: dict[str, str] = {}
for city, meta in CITIES.items():
    for d in meta.get("districts", []) or []:
        COUNTY_LOOKUP[(city, d)] = d
        COUNTY_TO_CITY[d] = city
        stem = re.sub(r"(市|县|区|旗)$", "", d)
        if stem and stem != d:
            COUNTY_LOOKUP[(city, stem)] = d
            COUNTY_TO_CITY.setdefault(stem, d)
COUNTY_KEYS: list[str] = sorted({d for d in COUNTY_TO_CITY}, key=len, reverse=True)


@dataclass
class Location:
    location_raw: str
    geo_level: str          # country / province / city / county / district / market / unknown
    province: str | None
    city: str | None
    county: str | None
    market: str | None = None  # 从原文剥离出的市场名（历史文章常写作「XX农贸市场」）


def _strip_suffixes(text: str) -> tuple[str, str | None]:
    """剥离市场名后缀，返回 (剩余行政区部分, 市场名)。"""
    market = None
    for suf in MARKET_SUFFIXES:
        if text.endswith(suf):
            market = text
            text = text[: -len(suf)]
            break
    for suf in REGION_SUFFIXES:
        if text.endswith(suf):
            text = text[: -len(suf)]
    return text.strip(), market


def _match_city(text: str) -> str | None:
    """在文本中匹配地级市（支持「沈阳」「沈阳市」两种写法），取最长匹配。"""
    for key in CITY_KEYS:
        if key in text:
            return CITY_LOOKUP[key]
    return None


def _match_county(text: str, city: str | None) -> str | None:
    """在文本中匹配区县。优先限定在已识别城市下匹配，其次全局匹配（用于只有区县的写法）。"""
    if city:
        candidates = [d for (c, k), d in COUNTY_LOOKUP.items() if c == city]
        for d in sorted(candidates, key=len, reverse=True):
            if d in text:
                return d
        for (c, k), d in COUNTY_LOOKUP.items():
            if c == city and k in text:
                return d
    for k in COUNTY_KEYS:
        if k in text:
            return COUNTY_TO_CITY[k]
    return None


def normalize_location(raw: str, default_city: str | None = None) -> Location:
    """把正文中的地点原文解析为层级化的省/市/区县。

    示例（来自真实正文）：
        沈阳市            → city=沈阳,              geo_level=city
        沈阳市沈北新区     → city=沈阳, county=沈北新区, geo_level=district
        铁岭市昌图县       → city=铁岭, county=昌图县,  geo_level=county
        鞍山台安县农贸市场 → city=鞍山, county=台安县,  market=鞍山台安县农贸市场
        阜新地区          → city=阜新,               geo_level=city
    """
    raw = (raw or "").strip()
    if not raw:
        return Location(raw, "unknown", None, None, None)

    # 国家级 / 省级
    if raw.startswith("全国") or raw in ("全国", "全国平均"):
        return Location(raw, "country", None, None, None)

    core, market = _strip_suffixes(raw)

    if any(x in core for x in (PROVINCE, "全省", "全省平均")) and len(core) <= 6:
        return Location(raw, "province", PROVINCE, None, None, market)

    city = _match_city(core)
    remainder = core
    if city:
        # 必须按「市名出现的位置」切除一次，不能再用市名主干二次替换：
        # 否则「辽阳市辽阳县」会被削成「县」、「铁岭市铁岭县」削成「县」，区县信息丢失。
        pos = core.find(city)
        if pos >= 0:
            remainder = core[:pos] + core[pos + len(city):]
        else:
            stem = city[:-1] if city.endswith("市") else city
            pos = core.find(stem)
            if pos >= 0:
                remainder = core[:pos] + core[pos + len(stem):]
    county = _match_county(remainder, city)

    if not city and county:  # 只写了区县（如「瓦房店旺角…」）
        city = COUNTY_TO_CITY.get(county)

    if not city and default_city:
        city = default_city
        county = _match_county(core, city)

    # 手册规范：city 为不含「市」后缀的市名（沈阳 / 铁岭 / 大连）
    city_short = city[:-1] if city and city.endswith("市") else city

    if county:
        level = "district" if county.endswith("区") else "county"
        return Location(raw, level, PROVINCE, city_short, county, market)
    if city:
        return Location(raw, "city", PROVINCE, city_short, None, market)
    if market:
        return Location(raw, "market", None, None, None, market)
    return Location(raw, "unknown", PROVINCE if "辽宁" in raw else None, None, None, market)


# ---- 产品标准化 ---------------------------------------------------------
PRODUCT_LOOKUP: dict[str, tuple[str, str]] = {}   # (category_key, alias) → (标准名, None)
for cat_key, block in PROD.get("categories", {}).items():
    for std_name, meta in (block.get("products") or {}).items():
        for alias in [std_name] + list(meta.get("aliases") or []):
            PRODUCT_LOOKUP[(cat_key, alias)] = (std_name, None)
        for v in meta.get("variants") or []:
            PRODUCT_LOOKUP[(cat_key, v)] = (std_name, v)


def normalize_product(name: str, category_key: str) -> tuple[str, str | None]:
    """返回 (product, product_variant)。

    只在确有同义关系时合并（西红柿→番茄、土豆→马铃薯）；
    原文区分的品种（长粒水稻/短粒水稻、干玉米/湿玉米）保留在 product_variant。
    """
    name = (name or "").strip()
    if not name:
        return "", None
    if (category_key, name) in PRODUCT_LOOKUP:
        return PRODUCT_LOOKUP[(category_key, name)]
    for (ck, alias), val in PRODUCT_LOOKUP.items():
        if ck == category_key and alias and alias in name:
            return val
    # 未在词典中：若残串含标点/数字/「价格」等，说明它并不是产品名（例如
    # 「沈阳价格为2080元」这类城市价格行），必须返回空交由调用方继承上文产品名，
    # 否则会把正文片段误当成产品名写入数据。
    cleaned = re.sub(r"^(辽宁|省内|全省)", "", name)
    if not cleaned or re.search(r"[，,。；;、0-9]|价格|均价|为", cleaned):
        return "", None
    return cleaned, None


# ---- 单位与价格 ---------------------------------------------------------
def convert_price(price: float | None, unit: str | None) -> tuple[float | None, str | None]:
    """把原始价格换算到统一单位「元/公斤」。无法换算的单位返回 (None, None)。"""
    if price is None or not unit:
        return None, None
    factor = UNIT_CONVERSION.get(unit)
    if factor is None:
        return None, None
    return round(price * factor, 6), "元/公斤"


# ---- 涨跌幅 -------------------------------------------------------------
_PCT_NUM = re.compile(r"([\d.]+)\s*%")

# 方向词表（按中心词匹配，前缀修饰如「小幅/微幅/明显/有所」自动被包含）
UP_WORDS = ("上涨", "上升", "增长", "增加", "涨幅", "微涨", "涨")
DOWN_WORDS = ("下降", "回落", "下跌", "下滑", "降低", "微降", "降", "缩减")
FLAT_WORDS = ("持平",)


def parse_change_pct(text: str, kind: str) -> float | None:
    """解析环比/同比涨跌幅为「百分点」数值。

    规则（手册第十七节）：上涨=正数，下降=负数，持平=0，缺失=None。

    关键约束：kind 的取值必须**紧邻**目标涨跌词。
    例如「环比下降0.43%，同比上涨16.44%」中，求「环比」时绝不能越过「同比」
    去捕获「上涨16.44%」——早期版本正是这样把 mom 误算成 16.44 的。
    兼容历史写法「环比持平（-0.35%）」：括号给出实际数值时以括号为准。
    """
    if not text or not kind:
        return None
    idx = text.find(kind)
    if idx == -1:
        return None
    seg = text[idx + len(kind): idx + len(kind) + 40]

    # 截断到另一个维度之前，避免跨「同比」取值
    other = "同比" if kind == "环比" else "环比"
    oi = seg.find(other)
    if oi != -1:
        seg = seg[:oi]

    # 窗口需容纳「持平（-0.35%）」这类完整写法（含括号共 11 字符）
    paren = re.search(r"[（(]\s*(-?[\d.]+)\s*%\s*[)）]", seg[:12])
    if paren:
        try:
            return float(paren.group(1))
        except ValueError:
            pass

    # 涨跌同义词：正文实际出现过「回落/下跌/下滑/微降/上升/增加」等写法，
    # 且常带修饰（小幅/微幅/明显/有所），统一按中心词判定方向。
    cands: list[tuple[int, int]] = []
    for w in UP_WORDS:
        p = seg.find(w)
        if p >= 0:
            cands.append((p, 1))
    for w in DOWN_WORDS:
        p = seg.find(w)
        if p >= 0:
            cands.append((p, -1))
    for w in FLAT_WORDS:
        p = seg.find(w)
        if p >= 0:
            cands.append((p, 0))
    if not cands:
        return None
    pos, sign = min(cands)
    m = _PCT_NUM.search(seg[pos:])
    if not m:
        return 0.0 if sign == 0 else None
    try:
        return sign * float(m.group(1))
    except ValueError:
        return None
