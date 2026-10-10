"""正文结构化解析（施工手册第九～二十二节）。

解析策略：**DOM 定位 → 章节切分 → 产品锚点 → 价格锚点 → 上下文语义分类**

为什么不是「一个巨大正则扫全文」：
历史文章（2021—2026）存在十余种价格句式，例如
    【大米】平均价格为4.48元/公斤                （2021—2024）
    【大米】批发均价为4.52元/公斤                （2025—2026）
    辽宁大豆收购均价为每公斤4.50元               （2024，单位倒装）
    最高收购价格出现在辽阳文圣区，为3.02元/公斤    （最高价地点在前）
    最高价格为3.10元/公斤，出现在辽阳灯塔         （最高价地点在后）
    最高价格为鞍山铁西区每公斤5.00元              （2023，地点+倒装单位）
    其中，沈阳市1750.00元/吨，鞍山市1750.00元/吨  （农资城市列举）
因此采用「先扫描所有价格锚点，再依据锚点前后文判定 record_type / 地点 / 涨跌」的分层方案，
对句式变化鲁棒，且每个数字都能回溯到原句（source_text，审计字段）。
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Iterable

from . import PROJECT_ROOT, get_logger
from .normalize import (
    CITIES,
    COUNTY_TO_CITY,
    PROVINCE,
    Location,
    convert_price,
    normalize_location,
    normalize_product,
    parse_change_pct,
)

log = get_logger("crawler.parser")

PARSED_CSV = PROJECT_ROOT / "data" / "intermediate" / "parsed_records.csv"
ERROR_CSV = PROJECT_ROOT / "logs" / "parser_errors.csv"

# ---- 正文结构 -----------------------------------------------------------
SECTION_RE = re.compile(r"^\s*([一二三四五六七八九十]+)\s*、\s*(.+)$")

MARKET_PRICE_KW = ("市场价格", "本周省内主要粮油品种市场价格", "市场行情")
PRODUCTION_PRICE_KW = ("产地价格",)
ANALYSIS_KW = ("市场分析", "市场概况", "近期产地市场概况")
OUTLOOK_KW = ("后期走势", "后期预测", "走势预测")

# 周次：「2026年第37周」/「辽宁省内第10周」/「2024年辽宁省内第26周」
WEEK_RE = re.compile(r"(?:(\d{4})\s*年)?\s*第\s*(\d{1,2})\s*周")
# 统计周期：「本周（2026年9月7日至2026年9月11日）」，兼容「至/-/—/~」与跨年简写
# 注意：2021 年蔬菜类早期文章正文写作「上周（2021年02月25日至2021年03月03日）」，
# 与后期的「本周（……）」并存，两者指的都是该期统计周期，必须同时覆盖。
PERIOD_RE = re.compile(
    r"(?:本周|上周|本期|本月)\s*[（(]?\s*(\d{4})\s*年\s*(\d{1,2})\s*月\s*(\d{1,2})\s*日?\s*"
    r"(?:至|-|—|~|～)\s*(?:(\d{4})\s*年)?\s*(\d{1,2})\s*月\s*(\d{1,2})\s*日?\s*[)）]?"
)

# 产品块标签：「【大米】」「【大 米】」（2022 年存在字间空格）
BRACKET_RE = re.compile(r"[【\[]\s*([^】\]]{1,20}?)\s*[】\]]")

# 价格锚点：正向「4.50元/公斤」与倒装「每公斤4.50元」
PRICE_FWD_RE = re.compile(r"(\d+(?:\.\d+)?)\s*元\s*/\s*(公斤|千克|斤|吨|kg|百公斤|袋|亩)")
PRICE_REV_RE = re.compile(r"每\s*(公斤|千克|斤|吨|百公斤)\s*(\d+(?:\.\d+)?)\s*元")

HIGH_KW = ("较高", "最高", "最高价")
LOW_KW = ("较低", "最低", "最低价")
# 「国产」在农资类正文中即全国口径：如「【国产豆粕】平均价格4134元/吨」与后句
# 「辽宁豆粕价格为4134.0元/吨」相对，前者是全国价、后者是省级价。
NATIONAL_KW = ("全国", "国产")
PROVINCE_KW = (PROVINCE, "全省", "省内", "辽宁")

# 价格类型关键词 → price_type
PRICE_TYPE_KW = (
    ("批发", "wholesale"),
    ("零售", "retail"),
    ("收购", "purchase"),
    ("出厂", "factory"),
    ("平均", "average"),
)

# 品种变体（手册第十四节：长粒水稻/短粒水稻、干玉米/湿玉米 必须保留差异）
VARIANT_TERMS = ["长粒水稻", "短粒水稻", "长粒稻谷", "短粒稻谷", "干玉米", "湿玉米"]
# 区块内用于定位产品归属的词表：变体词优先（更长），再产品别名
from .normalize import PRODUCT_LOOKUP  # noqa: E402  (避免循环导入，放在模块底部逻辑使用)


def _term_table(category_key: str) -> list[tuple[str, str, str | None]]:
    """返回 [(词, 标准产品名, 变体)]，按词长降序，供块内最长匹配。"""
    rows: list[tuple[str, str, str | None]] = []
    for v in VARIANT_TERMS:
        rows.append((v, v.replace("水稻", "").replace("稻谷", "").replace("玉米", ""), None))
    # 变体 → (product, variant)
    variant_map = {
        "长粒水稻": ("水稻", "长粒"),
        "短粒水稻": ("水稻", "短粒"),
        "长粒稻谷": ("水稻", "长粒"),
        "短粒稻谷": ("水稻", "短粒"),
        "干玉米": ("玉米", "干玉米"),
        "湿玉米": ("玉米", "湿玉米"),
    }
    rows = [(v, variant_map[v][0], variant_map[v][1]) for v in VARIANT_TERMS]
    seen = set()
    for (ck, alias), (std, _v) in PRODUCT_LOOKUP.items():
        if ck != category_key or alias in seen:
            continue
        seen.add(alias)
        rows.append((alias, std, None))
    return sorted(rows, key=lambda r: len(r[0]), reverse=True)


@dataclass
class PriceRecord:
    article_id: str
    year: int | None
    week: int | None
    period_start: str
    period_end: str
    publication_date: str
    category: str
    category_key: str
    product: str
    product_variant: str | None
    province: str | None
    city: str | None
    county: str | None
    location_raw: str
    geo_level: str
    record_type: str
    price_type: str
    price: float | None
    original_unit: str | None
    standard_price: float | None
    standard_unit: str | None
    mom_change_pct: float | None
    yoy_change_pct: float | None
    national_price: float | None
    provincial_price: float | None
    source_text: str
    source_url: str


@dataclass
class ParsedArticle:
    article_id: str
    category: str
    category_key: str
    year: int | None
    week: int | None
    period_start: str
    period_end: str
    publication_date: str
    title: str
    market_analysis: str
    future_outlook: str
    source_url: str
    parse_status: str
    records: list[PriceRecord] = field(default_factory=list)
    error_type: str = ""
    raw_text: str = ""


# ---- 文章级元信息 -------------------------------------------------------
def parse_week_year(title: str, publication_date: str) -> tuple[int | None, int | None]:
    """标题兼容三代写法：
        2026年第37周辽宁省主要粮油产品价格简讯          → (2026, 37)
        2024年辽宁省内第26周主要农资产品市场价格简讯      → (2024, 26)
        辽宁省内第10周主要粮油品种市场价格简讯            → (年份取发布日期, 10)
    """
    m = WEEK_RE.search(title or "")
    if not m:
        return None, None
    year = int(m.group(1)) if m.group(1) else None
    week = int(m.group(2))
    if year is None and publication_date:
        year = int(publication_date[:4])
    return year, week


def parse_period(text: str) -> tuple[str, str]:
    """优先保存正文明确写出的统计周期（手册第十节：周次不能代替真实统计日期）。"""
    m = PERIOD_RE.search(text or "")
    if not m:
        return "", ""
    y1, m1, d1 = int(m.group(1)), int(m.group(2)), int(m.group(3))
    y2 = int(m.group(4)) if m.group(4) else y1
    m2, d2 = int(m.group(5)), int(m.group(6))
    return f"{y1:04d}-{m1:02d}-{d1:02d}", f"{y2:04d}-{m2:02d}-{d2:02d}"


def classify_section(heading: str) -> str:
    h = heading or ""
    if any(k in h for k in PRODUCTION_PRICE_KW):
        return "production_price"
    if any(k in h for k in MARKET_PRICE_KW):
        return "market_price"
    if any(k in h for k in OUTLOOK_KW):
        return "outlook"
    if any(k in h for k in ANALYSIS_KW):
        return "analysis"
    return "other"


# ---- 价格锚点 -----------------------------------------------------------
@dataclass
class Anchor:
    start: int
    end: int
    price: float
    unit: str


def normalize_number_spaces(text: str) -> str:
    """修正常见的排版空格：正文出现「2960 .00元/吨」这类数字与小数点之间的空格。
    若不处理，正则只会捕获「00元/吨」，把价格错解析成 0。"""
    text = re.sub(r"(\d)\s+\.", r"\1.", text)
    text = re.sub(r"\.\s+(\d)", r".\1", text)
    return text


def find_price_anchors(text: str) -> list[Anchor]:
    text = normalize_number_spaces(text)
    anchors: list[Anchor] = []
    for m in PRICE_FWD_RE.finditer(text):
        anchors.append(Anchor(m.start(), m.end(), float(m.group(1)), f"元/{m.group(2)}"))
    for m in PRICE_REV_RE.finditer(text):
        unit = f"元/{m.group(1)}"
        # 倒装写法「每公斤4.50元」在原文中不出现「元/公斤」，但语义单位一致
        anchors.append(Anchor(m.start(), m.end(), float(m.group(2)), unit))
    anchors.sort(key=lambda a: a.start)
    # 去重（同一位置可能被两个正则同时命中？不会，但保险）
    out: list[Anchor] = []
    for a in anchors:
        if out and a.start < out[-1].end:
            continue
        out.append(a)
    return out


def _split_multi_location(raw: str) -> list[str]:
    """「沈阳、锦州、铁岭等地区」→ 拆成多个地点，各自生成记录。"""
    raw = re.sub(r"等地[区]?$|等$", "", raw.strip())
    parts = [p.strip() for p in re.split(r"[、,，/]|和|与", raw) if p.strip()]
    return parts or [raw]


def _clean_loc_candidate(s: str) -> str:
    s = (s or "").strip()
    s = re.sub(r"^[是为,，；;。:：\s]+", "", s)
    s = re.sub(r"^其中[:：，,]?", "", s)
    s = re.sub(r"[（(].*?[)）]", "", s)
    s = re.sub(r"^(?:价格|收购价格|平均价格|最高价格|最低价格|出厂价|出厂价)", "", s)
    s = re.sub(r"^出现(?:在)?", "", s)
    # 「其中：沈阳价格为X」→ 去掉引导词与尾部「价格」，保留「沈阳」
    s = re.sub(r"(?:价格|均价)$", "", s)
    s = re.sub(r"(?:等地[区]?|地区|区域)$", "", s) if len(s) > 4 else s
    s = re.sub(r"[，,；;。、]+$", "", s)
    return s.strip()


def _detect_price_type(prefix: str, fallback: str = "unknown") -> str:
    for kw, val in PRICE_TYPE_KW:
        if kw in prefix:
            return val
    return fallback


def _detect_record_type(ctx: str, has_location: bool, geo_level: str) -> str:
    """依据锚点前的上下文判定记录类型（手册第十五节取值域）。

    极值判定取「上下文中最后出现」的方向词，而不是「任意出现」：
    「最低价出现在A，为X。最高价为Y」这类句子里两个方向词都出现，
    必须按离价格更近的那个（即更靠后的）来判定。
    """
    if any(k in ctx for k in NATIONAL_KW):
        return "national_avg"
    hpos = max([ctx.rfind(k) for k in HIGH_KW] or [-1])
    lpos = max([ctx.rfind(k) for k in LOW_KW] or [-1])
    if hpos >= 0 and hpos > lpos:
        return "province_high"
    if lpos >= 0 and lpos > hpos:
        return "province_low"
    if geo_level in ("city", "county", "district"):
        return "city_price" if geo_level == "city" else "county_price"
    if any(k in ctx for k in PROVINCE_KW):
        return "province_avg"
    return "province_avg" if not has_location else "other"


VERB_TAIL = ("为", "是", "达", "至", "到", ":", "：")
# 正文中「出现在X」与「出现X」两种写法都存在（后者缺少「在」）
APPEAR_RE = re.compile(r"出现(?:在)?")


def _locate_before(prefix: str) -> str:
    """从锚点前的文本中提取地点候选。

    两种句式必须分开处理（否则地点会被动词吃掉或残留动词）：
      A.「全国出厂均价为{price}」「最高价出现在阜新市蔬菜批发市场，为{price}」
         —— 锚点紧接在「为/是」之后，地点在动词**之前**
      B.「价格较高的地区是丹东市东港市{price}」「其中，沈阳市{price}」
         —— 地点在分隔符**之后**、紧贴价格
    """
    p = (prefix or "").strip()
    if not p:
        return ""
    if p[-1] in VERB_TAIL:  # 句式 A
        core = p[:-1]
        if APPEAR_RE.search(core):
            after = core[list(APPEAR_RE.finditer(core))[-1].end():]
            # 「出现在锦州地区；最低价格为…」——该「出现在」属于上一句，
            # 当前价格的地点在价格之后（交给 _locate_after），此处必须返回空。
            if re.search(r"[；;。]", after):
                return ""
            return _clean_loc_candidate(after)
        best = 0
        for m in re.finditer(r"[，,。；;、]", core):
            best = max(best, m.end())
        return _clean_loc_candidate(core[best:] or core)
    # 句式 B
    best = 0
    for m in re.finditer(r"[，,。；;、]|是|为|出现|在", p):
        best = max(best, m.end())
    return _clean_loc_candidate(p[best:])


def _scope_loc(cand: str) -> str:
    """把含范围词的候选归到国家级/省级原文表述（如「全国出厂均价」→「全国」）。"""
    if not cand:
        return ""
    if "全国" in cand:
        return "全国"
    if any(k in cand for k in ("辽宁省", "全省", "省内", "辽宁")):
        return PROVINCE
    return cand


def _locate_after(suffix: str) -> str:
    """「最高价格为3.10元/公斤，出现在辽阳灯塔」——地点在价格之后。

    必须先截断到当前句：**不能跨句搜索**。
    否则「批发均价为6.20元/公斤，环比…。最高价出现在阜新市蔬菜批发市场，为10.00元/公斤」
    会把下一句的「阜新市蔬菜批发市场」错安到 6.20 这条全省均价上。
    """
    cut = min([x for x in (suffix.find("。"), suffix.find("；"), suffix.find(";")) if x >= 0]
              or [len(suffix)])
    suffix = suffix[:cut]
    m = APPEAR_RE.search(suffix)
    if m:
        # 若「出现」之前已经出现另一个价格，说明该「出现在X」描述的是下一个价格，
        # 不能归属给当前价格。例：
        #   「长粒水稻平均收购价为2.89元/公斤，…，最高价格为3.04元/公斤，出现在沈阳新民」
        #   —— 「沈阳新民」属于 3.04，不属于 2.89。
        before = suffix[: m.start()]
        if PRICE_FWD_RE.search(before) or PRICE_REV_RE.search(before):
            return ""
        tail = suffix[m.end(): m.end() + 20]
        cut = min([x for x in (tail.find("。"), tail.find("；"), tail.find("，")) if x >= 0] or [len(tail)])
        return _clean_loc_candidate(tail[:cut])
    return ""


def parse_price_block(
    block: str,
    *,
    article_id: str,
    category: str,
    category_key: str,
    year: int | None,
    week: int | None,
    period_start: str,
    period_end: str,
    publication_date: str,
    source_url: str,
    default_product: str,
    default_variant: str | None,
    section: str,
) -> list[PriceRecord]:
    """在一个产品块内解析出全部价格记录。"""
    block = normalize_number_spaces(block)
    terms = _term_table(category_key)
    anchors = find_price_anchors(block)
    if not anchors:
        return []

    # 术语位置表（最长匹配、互不重叠），用于判定每个价格归属哪个产品/品种
    marks: list[tuple[int, str, str, str | None]] = []
    used = [False] * len(block)
    for term, std, variant in terms:
        i = 0
        while True:
            idx = block.find(term, i)
            if idx == -1:
                break
            if not any(used[idx: idx + len(term)]):
                marks.append((idx, term, std, variant))
                for j in range(idx, idx + len(term)):
                    used[j] = True
            i = idx + 1
    marks.sort(key=lambda m: m[0])

    # 块级价格类型（用于高低价记录继承）
    block_price_type = _detect_price_type(block[: anchors[0].start] if anchors else block, "unknown")
    provincial_price = None
    national_price = None

    out: list[PriceRecord] = []
    prev_end = 0
    for a in anchors:
        prefix = block[prev_end: a.start]
        suffix = block[a.end: a.end + 40]
        prev_end = a.end

        # 产品归属：锚点之前最近的术语
        product, variant = default_product, default_variant
        for idx, term, std, var in marks:
            if idx < a.start:
                product, variant = std, var
            else:
                break

        # 地点：优先锚点前，其次锚点后（「最高价格为X，出现在Y」句式）
        loc_raw = _scope_loc(_locate_before(prefix))
        loc = normalize_location(loc_raw) if loc_raw else Location("", "unknown", None, None, None)
        if loc.geo_level == "unknown" and not loc.market:
            # 候选串不是有效行政区（常是「产品名+均价」残留）→ 视为无地点，按语义归省级/国家级
            loc_raw2 = _scope_loc(_locate_after(suffix))
            if loc_raw2:
                loc_raw, loc = loc_raw2, normalize_location(loc_raw2)
            else:
                loc_raw, loc = "", Location("", "unknown", None, None, None)

        # 窗口需足够宽以容纳「…同比下降25.84%。最高价出现在阜新市蔬菜批发市场，为」
        # 这类句式，否则方向词被截断，极值记录会被误判成普通城市价。
        ctx = prefix[-60:]
        price_type = _detect_price_type(prefix[-30:], block_price_type)
        record_type = _detect_record_type(ctx, loc.geo_level not in ("unknown", ""), loc.geo_level)
        if loc.geo_level in ("unknown", ""):
            loc = (
                Location("全国", "country", None, None, None)
                if record_type == "national_avg"
                else Location(PROVINCE, "province", PROVINCE, None, None)
            )

        # 涨跌：优先取锚点之后本句内的描述
        tail = block[a.end: a.end + 60]
        cut = min([x for x in (tail.find("。"), tail.find("；"), tail.find(";")) if x >= 0] or [len(tail)])
        tail = tail[:cut]
        mom = parse_change_pct(tail, "环比")
        yoy = parse_change_pct(tail, "同比")
        if mom is None and yoy is None and record_type in ("province_avg", "national_avg"):
            # 政府简讯常在省级价后省略涨跌（涨跌写在同产品前一句，如全国价句）。
            # 仅对省级/国家级均价做此回溯，高低价与市县级价格绝不继承，避免张冠李戴。
            mom = parse_change_pct(prefix[-80:], "环比")
            yoy = parse_change_pct(prefix[-80:], "同比")

        std_price, std_unit = convert_price(a.price, a.unit)
        source_text = block.strip()

        if record_type == "national_avg":
            national_price = a.price
        if record_type == "province_avg":
            provincial_price = a.price

        # 多地点拆分（如「出现在沈阳、锦州、铁岭等地区」）
        locs = _split_multi_location(loc_raw) if "、" in loc_raw else [loc_raw]
        for one in locs:
            one_loc = normalize_location(_scope_loc(one)) if one != loc_raw else loc
            if one_loc.geo_level in ("unknown", "") and not one_loc.market:
                # 候选串里只有产品/动词（如「谷子平均收购价」）→ 该价格实为省级口径
                if record_type == "national_avg":
                    one_loc = Location("全国", "country", None, None, None)
                else:
                    one_loc = Location(PROVINCE, "province", PROVINCE, None, None)
            out.append(
                PriceRecord(
                    article_id=article_id,
                    year=year,
                    week=week,
                    period_start=period_start,
                    period_end=period_end,
                    publication_date=publication_date,
                    category=category,
                    category_key=category_key,
                    product=product,
                    product_variant=variant,
                    province=one_loc.province,
                    city=one_loc.city,
                    county=one_loc.county,
                    location_raw=one_loc.location_raw or one,
                    geo_level=one_loc.geo_level,
                    record_type=record_type,
                    price_type=price_type,
                    price=a.price,
                    original_unit=a.unit,
                    standard_price=std_price,
                    standard_unit=std_unit,
                    mom_change_pct=mom,
                    yoy_change_pct=yoy,
                    national_price=national_price if record_type == "national_avg" else None,
                    provincial_price=provincial_price if record_type != "national_avg" else None,
                    source_text=source_text,
                    source_url=source_url,
                )
            )
    return out


def split_blocks(text: str) -> list[tuple[str, str]]:
    """把正文按「【产品】」切成块，返回 [(块标签, 块文本)]。"""
    matches = list(BRACKET_RE.finditer(text))
    if not matches:
        return [("", text)]
    blocks: list[tuple[str, str]] = []
    if matches[0].start() > 0:
        blocks.append(("", text[: matches[0].start()]))
    for i, m in enumerate(matches):
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        label = re.sub(r"\s+", "", m.group(1))
        blocks.append((label, m.group(0) + text[m.end(): end]))
    return blocks


def parse_article(rec: dict) -> ParsedArticle:
    """解析一篇已下载的文章（输入来自 articles.jsonl 的一条记录）。"""
    raw_text = rec.get("raw_text", "") or ""
    title = rec.get("title", "") or ""
    pub = rec.get("publication_date", "") or ""
    cat = rec.get("category", "")
    cat_key = rec.get("category_key", "")
    aid = rec.get("article_id", "")
    url = rec.get("url", "")

    year, week = parse_week_year(title, pub)
    period_start, period_end = parse_period(raw_text)
    if year is None and period_start:
        year = int(period_start[:4])

    lines = [ln.strip() for ln in raw_text.split("\n") if ln.strip()]
    section = "other"
    market_parts: list[str] = []
    outlook_parts: list[str] = []
    records: list[PriceRecord] = []
    # 跨段落继承产品名：城市价格常单独成行（无【】标签），需继承上文【产品】
    current_prod, current_var = "", None

    for line in lines:
        m = SECTION_RE.match(line)
        if m:
            heading = m.group(2)
            section = classify_section(heading)
            if section in ("analysis", "outlook"):
                # 保留标题本身，便于人工阅读
                (market_parts if section == "analysis" else outlook_parts).append(line)
            continue

        if section in ("market_price", "production_price"):
            for label, block in split_blocks(line):
                if not block.strip():
                    continue
                if label:
                    cur_prod, cur_var = normalize_product(label, cat_key)
                    if cur_prod:
                        current_prod, current_var = cur_prod, cur_var
                prod, variant = current_prod, current_var
                if not prod:
                    # 无【】标签且尚无产品（如独立的城市价格行「沈阳价格为2080元/吨，抚顺…」）
                    # 时，才尝试从块首猜测；猜不出则保持空，避免正文片段当产品名。
                    prod, variant = normalize_product(block[:12], cat_key)
                    if prod:
                        current_prod, current_var = prod, variant
                got = parse_price_block(
                    block,
                    article_id=aid,
                    category=cat,
                    category_key=cat_key,
                    year=year,
                    week=week,
                    period_start=period_start,
                    period_end=period_end,
                    publication_date=pub,
                    source_url=url,
                    default_product=prod,
                    default_variant=variant,
                    section=section,
                )
                records.extend(got)
        elif section == "analysis":
            market_parts.append(line)
        elif section == "outlook":
            outlook_parts.append(line)

    if not records:
        status = "failed"
        error = "no_price_record"
    elif not period_start or not period_end:
        status = "partial"
        error = "missing_period"
    elif any(r.product is None or r.product == "" for r in records):
        status = "partial"
        error = "missing_product"
    else:
        status = "success"
        error = ""

    return ParsedArticle(
        article_id=aid,
        category=cat,
        category_key=cat_key,
        year=year,
        week=week,
        period_start=period_start,
        period_end=period_end,
        publication_date=pub,
        title=title,
        market_analysis="\n".join(market_parts).strip(),
        future_outlook="\n".join(outlook_parts).strip(),
        source_url=url,
        parse_status=status,
        records=records,
        error_type=error,
        raw_text=raw_text,
    )


def record_to_row(r: PriceRecord) -> dict:
    return asdict(r)


def write_parse_errors(articles: list[ParsedArticle], path: Path = ERROR_CSV) -> None:
    """解析失败/异常文章全量留痕（手册第二十二节）。"""
    path.parent.mkdir(parents=True, exist_ok=True)
    rows = [a for a in articles if a.parse_status in ("failed", "partial", "unknown_format")]
    if not rows:
        path.write_text("", encoding="utf-8")
        return
    import csv

    with path.open("w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=["article_id", "url", "title", "error_type", "parse_status", "raw_text"])
        w.writeheader()
        for a in rows:
            w.writerow({
                "article_id": a.article_id,
                "url": a.source_url,
                "title": a.title,
                "error_type": a.error_type,
                "parse_status": a.parse_status,
                "raw_text": a.raw_text[:2000],
            })
