"""解析 大连市农业农村局「12316 金农热线」农产品周报 → 三层价格 staging。

======================================================================
【来源实况（先读，决定了解析方式与可信度）】
来源栏目：agri.dl.gov.cn
  col4139「农产品价格监测分析」——「大连市农产品一周价格涨跌第 N 周」
  col4141「大连市主要农产品产地价格」——「大连市主要农产品产地价格表第 N 周」
两栏合计 554 + 421 = 975 篇，覆盖 2016-07 ~ 2026-09。

三层价格的**载体完全不同**：

  (1) 产地价 farm_gate —— 来自 col4141
      正文为空，**整张价格表以 PNG 图片发布**（每期 1~2 张）。
      表结构：序号|产品大类|产品小类|产品名称|产地收购均价（元/斤）|价格区间（元/斤）
      每期约 44 个品种。→ 必须 OCR 后解析（quality_grade=B，机器转录）。
      极少数期（2022 前后）图片 src 为编辑器遗留的 blob: 伪地址，静态 HTML 无真实地址
      → 该期无图，如实缺失，不编造。

  (2) 批发价 wholesale / 零售价 retail_market —— 来自 col4139
      正文为**叙述文本**：按 粮油/肉蛋奶/蔬菜/水产/水果 分类，每类给
        「平均批发价/平均零售价/平均产地价」的**类别均价**，
        以及「升降较明显」的**个别品种**具体价。
      **不存在**逐品种全量清单（全量品种表在本栏目从未以文本或表格发布）。
      → 只能解析出「类别均价 + 个别品种」两类记录，覆盖度有限，如实反映。
      col4139 内嵌图片经全量抽样确认为 Chart 走势图，不含表格数据，不参与解析。

【单位口径（有据，非假设）】
  · col4141 表头自述「产地收购均价（元/斤）」→ price_per_kg = 值 × 2。
  · col4139 早期文章正文显式给出单位（每500g（下同）/ 元/公斤 / 元/5升）→ 按显式单位换算。
  · col4139 现代文章正文**不写单位**，但可交叉验证为「元/公斤」：
      2026 第 38 周叙述「尖椒 4.04、甘蓝 2、茄子 2.98」
      与同周 col4141 产地表「尖椒 2.02、甘蓝 1.00、茄子 1.49 元/斤」×2 完全吻合（6/6）。
      且栏目自带的自动分析段落自述口径为「元每公斤」。
      → 现代叙述文本按 元/公斤 处理（quality_grade=B）。
      例外：名称含「油」「粉」者为包装规格（如 桶装花生油 元/5升、富强粉 袋装），
      叙述未标单位时无法换算 → unit_original 记「未标注」、price_per_kg 留空（quality_grade=C）。

【产出】city_data/reference/staging/dalian_12316_prices.csv
  字段：date / city / market_name / crop_raw / crop_standard / price_original /
        unit_original / price_per_kg / price_level / source_id / source_name /
        source_url / raw_file / quality_grade
  price_level ∈ {wholesale, retail_market, farm_gate}
  不做插值、不补齐、不推断缺失价格；解析不出的期次如实留空并计数。
"""
from __future__ import annotations

import json
import re
from collections import Counter
from html import unescape
from pathlib import Path

import pandas as pd

ROOT = next(p for p in Path(__file__).resolve().parents if (p / "AgriScope").is_dir() and (p / "data").is_dir())
RAW = ROOT / "data/raw" / "prices" / "dalian_12316"
STAGING = ROOT / "city_data/reference/staging"
STAGING.mkdir(parents=True, exist_ok=True)

SOURCE_ID = "SRC-DL-12316"
SOURCE_NAME = "大连市农业农村局 12316金农热线 农产品价格周报"
CITY = "大连"

MARKET_NAME = {
    "wholesale": "大连市农副产品批发价（12316金农热线）",
    "retail_market": "大连市农副产品零售价（12316金农热线）",
    "farm_gate": "大连市农产品产地价（12316金农热线）",
}

# 4141 两种价格表的「产品大类 / 产品小类」列取值——本身不是品种；
# OCR 列错位时会被误取为名称，故显式剔除（玉米/花生除外：它们同时也是真实品种，不剔除）。
NON_CROP = {"叶类菜", "茄果类", "瓜类", "根茎花类", "豆类", "葱蒜类", "羊类", "猪类", "牛类",
            "鸡类", "薯类", "稻类", "仁果类", "核果类", "浆果类", "家畜", "家禽",
            "粮食作物", "油料作物", "食用菌", "大类", "小类"}

# ---------------------------------------------------------------- 品种归一
# 仅收录来源中确实出现过、且同义关系明确的别名（保守归一，不做猜测性合并）。
# 含 OCR 形近字变体（与 parsers/jinzhou_ocr_parser.py 的 CROP_CANON 同一处理原则）。
CROP_ALIAS = {
    "西红柿": "番茄", "西红杮": "番茄", "番茄（西红柿）": "番茄", "番加": "番茄",
    "茄子（紫）": "紫茄子", "茄子_紫": "紫茄子", "茄子(紫)": "紫茄子",
    "茄子（青）": "青茄子", "茄子(青)": "青茄子",
    "豆王": "架豆王", "土豆": "马铃薯",
    "蒜苔": "蒜薹", "青椒": "尖椒", "洋葱": "圆葱", "葱头": "圆葱",
    "五花猪肉": "猪肉", "鲜猪肉": "猪肉",
    "牛腩": "牛肉", "鲜牛肉": "牛肉", "鲜羊肉": "羊肉", "鲜鸡肉": "鸡肉",
    "鲜奶": "牛奶", "桶装花生油": "花生油", "桔子": "橘子", "柑橘": "橘子",
    "妮娜皇后": "葡萄（妮娜皇后）", "萝": "萝卜", "胡萝": "胡萝卜",
    "生采": "生菜", "油采": "油菜", "采豆": "菜豆", "波采": "菠菜", "沺菜": "油菜",
    "卜架鸡": "下架鸡", "小怱": "小葱", "合鲍菇": "杏鲍菇", "太豆": "大豆",
    "巨蜂葡萄": "巨峰葡萄", "西蓝花": "西兰花", "地瓜": "甘薯", "黄豆": "大豆",
    "水黄瓜": "黄瓜", "地黄瓜": "黄瓜", "早黄瓜": "旱黄瓜", "番薯": "甘薯",
}
# 繁/异体字机械归一（非释义性改动）
CHAR_FIX = str.maketrans({"黃": "黄", "苹": "苹"})

# 类别标签（作为「类别均价」记录保留，crop_raw 即类别名）
CATEGORIES = {"粮油", "肉蛋奶", "蔬菜", "水产品", "水产", "水果"}
CATEGORY_NORM = {"水产品": "水产"}

# 包装/规格类商品：叙述未标单位时不能按 元/公斤 处理
# 判据：名称以「油/粉」结尾（花生油、豆油、色拉油、富强粉、标准粉、面粉）或「桶装」开头。
# 注意「油菜」以「菜」结尾，不是油品，不能被误判。
def is_packaged(name: str) -> bool:
    n = re.sub(r"\s+", "", name or "")
    return n.endswith("油") or n.endswith("粉") or n.startswith("桶装")


def norm_crop(name: str) -> str:
    n = re.sub(r"\s+", "", name or "").translate(CHAR_FIX)
    n = n.strip("（）() 、,，").rstrip("的")
    return CROP_ALIAS.get(n, n)


def to_per_kg(price: float, unit: str) -> float | None:
    u = (unit or "").replace(" ", "")
    if u in ("元/斤", "元/500克", "元/500g", "元/500G"):
        return round(price * 2, 4)
    if u in ("元/公斤", "元/千克", "元/kg", "元/KG"):
        return round(price, 4)
    return None            # 元/5升、未标注等一律不换算（不猜）


# ---------------------------------------------------------------- 工具
def content_html(t: str) -> str:
    m = re.search(r"ContentStart(.*?)ContentEnd", t, re.S)
    return m.group(1) if m else ""


def clean_text(html: str) -> str:
    b = re.sub(r"<(script|style)[^>]*>.*?</\1>", "", html, flags=re.S | re.I)
    b = re.sub(r"<br\s*/?>", "\n", b, flags=re.I)
    b = re.sub(r"</(p|div|tr|li|h[1-6])>", "\n", b, flags=re.I)
    b = re.sub(r"<[^>]+>", "", b)
    b = unescape(b).replace("\u3000", " ").replace("\xa0", " ")
    return re.sub(r"\s+", " ", b).strip()


def clean_num(s: str) -> float | None:
    t = re.sub(r"[^\d.]", "", str(s or ""))
    if not t:
        return None
    if t.count(".") > 1:
        head, _, tail = t.partition(".")
        t = head + "." + tail.replace(".", "")
    try:
        v = float(t)
    except ValueError:
        return None
    return v if v > 0 else None


def split_names(s: str) -> list[str]:
    return [x for x in re.split(r"[、，,和及]", s) if x.strip()]


def split_nums(s: str) -> list[float]:
    out = []
    for x in re.split(r"[、，,和及]", s):
        v = clean_num(x)
        if v is not None:
            out.append(v)
    return out


# ======================================================================
# A. col4141 价格表（OCR 文本）—— 两种版式，必须分别解析
# ----------------------------------------------------------------------
#   版式 S（近期，约 2023 起）「汇总表」：
#        序号|产品大类|产品小类|产品名称|产地收购均价（元/斤）|价格区间（元/斤）
#        → 只有产地收购均价 → price_level = farm_gate
#   版式 D（早期，约 2018-2022）「明细库表」：
#        序号|产品名称|价格|价格单位|价格类型|价格区域|价格时间
#        价格类型 ∈ {收购价, 批发价, 零售价}，价格单位逐行给出（元/斤、元/穗…）
#        → 同一张图同时含 收购价(farm_gate) / 批发价(wholesale) / 零售价(retail_market)
#   两种版式的图都很窄（约 860~1550px），版式 D 尤其长（可达 8500px），
#   采集器已按纵向切片 OCR（见 collectors/dalian_12316_download.py）。
# ----------------------------------------------------------------------
TYPES = {"收购价": "farm_gate", "产地价": "farm_gate",
         "批发价": "wholesale", "零售价": "retail_market"}
RE_RANGE = re.compile(r"^\d+(?:\.\d+)?\s*[-~—－]\s*\d+(?:\.\d+)?$")
RE_UNIT_TOK = re.compile(r"^元\s*/\s*(斤|公斤|千克|kg|KG|500g|500克|穗|个|袋|盒|吨|只)$")
UNIT_MAP = {"斤": "元/斤", "公斤": "元/公斤", "千克": "元/千克", "kg": "元/kg", "KG": "元/kg",
            "500g": "元/500克", "500克": "元/500克", "穗": "元/穗", "个": "元/个",
            "袋": "元/袋", "盒": "元/盒", "吨": "元/吨", "只": "元/只"}
# 明显的 OCR 形近错字（已回原图核对）
OCR_FIX = {"千玉米": "干玉米"}


def _tokens(line: str) -> list[str]:
    toks = [t.strip() for t in line.split("\t") if t.strip()]
    if len(toks) < 2:
        toks2 = [t.strip() for t in re.split(r"\s{2,}", line) if t.strip()]
        if len(toks2) > len(toks):
            toks = toks2
    return toks


def _is_region(t: str) -> bool:
    if len(t) > 12:
        return True
    if re.search(r"[省市区县镇乡村街道]", t):
        return True
    if "/" in t and re.search(r"[\u4e00-\u9fa5]", t):
        return True
    return False


def _clean_name(t: str) -> str:
    t = re.sub(r"[（(][^）)]*[）)]?", "", t)
    t = t.strip().strip("，,、。；; 　")
    return OCR_FIX.get(t, t)


def parse_summary(lines: list[str]) -> tuple[list[tuple[str, float, str, str]], str, Counter]:
    """版式 S：名称/产地收购均价/价格区间。返回 rows=[(名称, 价, 单位, level)]。"""
    rows, stats = [], Counter()
    unit = "元/斤"
    for ln in lines:
        if "均价" in ln and "元/公斤" in ln.replace(" ", ""):
            unit = "元/公斤"
        t = [x.strip() for x in ln.split("\t") if x.strip()]
        if len(t) < 4:
            t2 = [x.strip() for x in re.split(r"\s{2,}", ln) if x.strip()]
            if len(t2) > len(t):
                t = t2
        if len(t) < 4:
            stats["列数不足"] += 1
            continue
        plain = "".join(t)
        if "产品名称" in plain or "产品大类" in plain:
            continue
        qi = next((i for i, x in enumerate(t) if RE_RANGE.match(x.replace(" ", ""))), None)
        if qi is None or qi < 2:
            stats["无区间/名称列"] += 1
            continue
        avg = clean_num(t[qi - 1])
        name = _clean_name(re.sub(r"[（(].*?[)）]", "", t[qi - 2]))
        if avg is None:
            stats["均价非数值"] += 1
            continue
        if name in CATEGORIES or name in CATEGORY_NORM:
            stats["名称为类别"] += 1
            continue
        if not valid_crop(name):
            stats["名称残缺或非法"] += 1
            continue
        rows.append((name, avg, unit, "farm_gate"))
    return rows, unit, stats


def parse_detail(lines: list[str]) -> tuple[list[tuple[str, float, str, str]], str, Counter]:
    """版式 D：序号/产品名称/价格/价格单位/价格类型/价格区域/价格时间。"""
    rows, stats = [], Counter()
    buf: list[str] = []
    for ln in lines:
        toks = _tokens(ln)
        if not toks:
            continue
        joined = "".join(toks)
        if "价格类型" in joined and ("产品名称" in joined or "价格单位" in joined):
            buf = []                      # 表头（切片重叠处会重复出现）
            continue
        buf += toks
        types_in = [i for i, t in enumerate(buf) if t in TYPES]
        if not types_in:
            if len(buf) > 60:
                buf = buf[-60:]
            continue
        ti = types_in[-1]
        level = TYPES[buf[ti]]
        seg = buf[:ti]
        # 价格单位
        ui = next((i for i in range(len(seg) - 1, -1, -1) if RE_UNIT_TOK.match(seg[i])), None)
        unit = UNIT_MAP[RE_UNIT_TOK.match(seg[ui]).group(1)] if ui is not None else None
        # 价格：优先取「单位」紧前一个数值，否则取段内最后一个数值（排除序号）
        pi = None
        if ui is not None and ui - 1 >= 0 and clean_num(seg[ui - 1]) is not None:
            pi = ui - 1
        else:
            cand = [i for i in range(len(seg)) if clean_num(seg[i]) is not None]
            if cand:
                pi = cand[-1]
        if pi is None:
            stats["无价格"] += 1
            buf = []
            continue
        price = clean_num(seg[pi])
        # 名称：紧前一个 token（跳过区域/日期/单位）
        name = None
        j = pi - 1
        while j >= 0:
            s = seg[j].strip()
            if RE_UNIT_TOK.match(s) or _is_region(s) or re.fullmatch(r"\d{4}-\d{2}-\d{2}", s) or clean_num(s) is not None:
                j -= 1
                continue
            name = _clean_name(s)
            break
        buf = []
        if price is None:
            stats["价格为非数值"] += 1
            continue
        if not name or name in CATEGORIES or name in CATEGORY_NORM:
            stats["名称为类别或缺失"] += 1
            continue
        if not valid_crop(name):
            stats["名称残缺或非法"] += 1
            continue
        if unit is None:
            stats["无单位(默认元/斤)"] += 1
            unit = "元/斤"
        rows.append((name, price, unit, level))
    return rows, "", stats


def parse_price_table_ocr(txt: str):
    """自动判型：返回 (rows=[(名称,价,单位,level)], stats)。"""
    lines = [x for x in txt.splitlines() if x.strip()]
    head = "".join(lines[:15]).replace(" ", "")
    if "价格类型" in head or "价格单位" in head:
        rows, _, st = parse_detail(lines)
        return rows, st
    rows, _, st = parse_summary(lines)
    return rows, st


def build_price_tables(index: list[dict]) -> tuple[list[dict], Counter]:
    rows: list[dict] = []
    stats: Counter = Counter()
    for art in index:
        if art["column"] != "4141":
            continue
        ocr_files = [(im["file"], RAW / "ocr" / f"{im['image_id']}.txt")
                     for im in art.get("images", []) if im.get("file") and im.get("image_id")]
        if not ocr_files or all(not f.exists() for _, f in ocr_files):
            stats["无OCR文本(该期无可用图片)"] += 1
            continue
        got = 0
        for raw_file, f in ocr_files:
            if not f.exists():
                continue
            pairs, st = parse_price_table_ocr(f.read_text(encoding="utf-8", errors="replace"))
            for k, v in st.items():
                stats[k] += v
            for name, price, unit, level in pairs:
                rows.append({
                    "date": art["date"], "city": CITY,
                    "market_name": MARKET_NAME[level],
                    "crop_raw": name, "crop_standard": norm_crop(name),
                    "price_original": price, "unit_original": unit,
                    "price_per_kg": to_per_kg(price, unit),
                    "price_level": level,
                    "source_id": SOURCE_ID, "source_name": SOURCE_NAME,
                    "source_url": art["url"], "raw_file": raw_file,
                    "quality_grade": "B",
                })
                got += 1
        if got == 0:
            stats["该期解析0行"] += 1
    return rows, stats


# ======================================================================
# B. col4139 叙述文本（批发 / 零售 / 产地）
# ======================================================================
# 自动生成的分析段落（内含**其它周次**的行情数字，必须剔除，避免日期错配）
RE_AUTO_SECTION = re.compile(r"大连市[\u4e00-\u9fa5]{2,6}类产品\s*\d{4}\s*-\s*\d{1,2}\s*周至")
# 类别块切分（允许「粮油（6升2降1平）：」这类带括号说明）
RE_CAT = re.compile(r"(粮油|肉蛋奶|蔬菜|水产品|水产|水果)\s*(?:（[^）]{0,20}）)?\s*[：:]")
# 层级标记：平均批发价 / 平均批发价格 / 平均零售价 …
RE_LEVEL = re.compile(r"平均(批发|零售|产地|收购)(?:价|价格)(?:为|是|:)?\s*([\d.]+)\s*元(?:/(公斤|千克|kg|500g|500克|斤))?")
# 个别品种：…有A、B，价格为 p1、p2 元 …
RE_MOVER = re.compile(r"有([^。；;]{2,90}?)[，,]?\s*价格(?:分别)?为\s*([^。；;]{1,90}?)\s*元")
# 早期格式：A，B平均零售价格每500g（下同）分别为 x 元和 y 元
RE_EARLY_LIST = re.compile(
    r"((?:[\u4e00-\u9fa5]{2,10}[、，,和])+[\u4e00-\u9fa5]{2,10}?)\s*平均(批发|零售|产地)价[格]?"
    r"\s*(?:每500[gG克]{1,3}（下同）)?\s*(?:分别)?为?\s*"
    r"([\d.]+(?:\s*元?\s*[、和，,]?\s*[\d.]+\s*元?)*)"
    r"(?:\s*/\s*(公斤|千克|500g|500克|5升|斤))?"
)
# 早期单品种：X（的）价格为 y 元；名字首字排除功能词，避免把「上升较为明显的是大豆」整段当成品种
_ECN = r"(?:(?![的是为有较明显品种类监测本周升降涨跌幅度其中分别都平均上下])[\u4e00-\u9fa5])"
RE_EARLY_SINGLE = re.compile(
    rf"({_ECN}{{2,10}}?)的?价格为\s*([\d.]+)\s*元(?:/(公斤|千克|kg|500g|500克|5升|斤))?"
)
RE_EARLY_PAIR = re.compile(
    r"([\u4e00-\u9fa5]{2,8}?)[、和]([\u4e00-\u9fa5]{2,8}?)的?价格(?:分别)?为\s*([\d.]+)\s*元和\s*([\d.]+)\s*元"
)

LEVEL_MAP = {"批发": "wholesale", "零售": "retail_market", "产地": "farm_gate", "收购": "farm_gate"}
UNIT_CANON = {"公斤": "元/公斤", "千克": "元/千克", "kg": "元/kg",
              "500g": "元/500克", "500克": "元/500克", "斤": "元/斤", "5升": "元/5升"}


def _row(art, crop, level, price, unit, grade):
    return {
        "date": art["date"], "city": CITY, "market_name": MARKET_NAME[level],
        "crop_raw": crop, "crop_standard": norm_crop(crop),
        "price_original": price, "unit_original": unit,
        "price_per_kg": to_per_kg(price, unit),
        "price_level": level, "source_id": SOURCE_ID, "source_name": SOURCE_NAME,
        "source_url": art["url"], "raw_file": art["html"], "quality_grade": grade,
    }


# 非品种名的功能词（防止把「平均零售」「监测」等误当品种）
BAD_SUBSTR = ("平均", "价格", "监测", "本周", "环比", "同比", "上涨", "下降", "分别",
              "其中", "升降", "幅度", "以上", "数据", "分析", "预测", "预计", "主要",
              "农副", "农产品", "品种", "市场", "元", "%", "％", "持平和",
              "批发", "零售", "产地", "收购", "斤", "品", "和")


# 单字品种（来源中确实出现）——避免被长度校验误杀
SINGLE_OK = {"梨", "桃", "杏", "枣", "蒜", "姜", "葱", "藕", "柚"}


def valid_crop(name: str) -> bool:
    n = (name or "").strip().strip("，,、。；; ").rstrip("的").translate(CHAR_FIX)
    if n in NON_CROP:
        return False
    if n in SINGLE_OK or n in CROP_ALIAS:
        return True
    if not re.search(r"[\u4e00-\u9fa5]", n):        # 品种名必须含汉字（滤掉纯拉丁噪声）
        return False
    if not (2 <= len(n) <= 12):
        return False
    if not re.fullmatch(r"[\u4e00-\u9fa5A-Za-z0-9_＋+（）()·]{2,12}", n):
        return False
    return not any(b in n for b in BAD_SUBSTR)


def _unit_grade(crop: str, explicit_unit: str | None) -> tuple[str, str]:
    """返回 (unit_original, quality_grade)。explicit_unit 为空表示正文未标单位。"""
    if explicit_unit:
        return explicit_unit, "B"
    if is_packaged(crop):
        return "未标注", "C"          # 包装规格商品（含「粮油」类别：混装油品，单位不可比），无法按 元/公斤 处理
    return "元/公斤", "B"             # 经同周 col4141 产地表交叉验证（见模块 docstring）


def build_narrative(art: dict, stats: Counter) -> list[dict]:
    t = Path(ROOT / art["html"]).read_text(encoding="utf-8", errors="replace")
    text = clean_text(content_html(t))
    text = RE_AUTO_SECTION.split(text)[0]          # 剔除自动生成的多周行情段
    if not text:
        stats["正文为空"] += 1
        return []

    rows: list[dict] = []
    default_unit = "元/500克" if re.search(r"每500[gG克]{1,3}（下同）", text) else None

    marks = [(m.start(), m.group(1)) for m in RE_CAT.finditer(text)]
    blocks = []
    for i, (pos, cat) in enumerate(marks):
        end = marks[i + 1][0] if i + 1 < len(marks) else len(text)
        blocks.append((CATEGORY_NORM.get(cat, cat), pos, text[pos:end]))
    if not blocks:
        blocks = [("", 0, text)]

    def level_at(block_seg: str, block_off: int, lvl_marks, pos_in_seg: int):
        """返回该位置所属层级标记 (level, unit)；无标记则 (None, None)。"""
        cur = None
        for lm in lvl_marks:
            if lm.start() <= pos_in_seg:
                unit = UNIT_CANON.get(lm.group(3)) if lm.group(3) else default_unit
                cur = (LEVEL_MAP[lm.group(1)], unit)
        return cur if cur else (None, None)

    for cat, off, seg in blocks:
        lvl_marks = list(RE_LEVEL.finditer(seg))

        # (a) 类别均价行
        for lm in lvl_marks:
            lvl = LEVEL_MAP[lm.group(1)]
            avg = clean_num(lm.group(2))
            unit = UNIT_CANON.get(lm.group(3)) if lm.group(3) else default_unit
            if cat and avg is not None:
                u, g = _unit_grade(cat, unit)
                rows.append(_row(art, cat, lvl, avg, u, g))
                stats["类别均价行"] += 1

        # (b) 个别品种（有 A、B，价格为 p1、p2 元），层级取最近的先行层级标记
        for mm in RE_MOVER.finditer(seg):
            names, nums = split_names(mm.group(1)), split_nums(mm.group(2))
            lvl, unit = level_at(seg, off, lvl_marks, mm.start())
            if lvl is None:
                lvl, unit = "retail_market", default_unit
                stats["个别品种无层级标记"] += 1
            if not names or not nums:
                continue
            if len(nums) == len(names):
                pairs = list(zip(names, nums))
            elif len(nums) == 1:
                pairs = [(names[0], nums[0])]
            else:
                stats["名称/数值数不匹配"] += 1
                continue
            for nm, pr in pairs:
                if not valid_crop(nm):
                    stats["品种名无效"] += 1
                    continue
                u, g = _unit_grade(nm, unit)
                rows.append(_row(art, nm.strip(), lvl, pr, u, g))
                stats["个别品种行"] += 1

        # (c) 早期格式：A，B平均零售价格…分别为 x 元和 y 元（自带层级）
        for m in RE_EARLY_LIST.finditer(seg):
            names, lvl = split_names(m.group(1)), LEVEL_MAP[m.group(2)]
            unit = UNIT_CANON.get(m.group(4)) if m.group(4) else default_unit
            nums = split_nums(m.group(3))
            if len(names) == len(nums):
                for nm, pr in zip(names, nums):
                    if not valid_crop(nm):
                        stats["品种名无效"] += 1
                        continue
                    u, g = _unit_grade(nm, unit)
                    rows.append(_row(art, nm.strip(), lvl, pr, u, g))
                    stats["早期列表行"] += 1

        # (d) 早期单品种：X价格为 y 元（层级取最近先行层级标记）
        for m in RE_EARLY_SINGLE.finditer(seg):
            nm = m.group(1)
            if not valid_crop(nm):
                stats["品种名无效"] += 1
                continue
            pr = clean_num(m.group(2))
            if pr is None:
                continue
            unit = UNIT_CANON.get(m.group(3)) if m.group(3) else None
            lvl, lu = level_at(seg, off, lvl_marks, m.start())
            unit = unit or lu or default_unit
            if lvl is None:
                lvl = "retail_market"
            u, g = _unit_grade(nm, unit)
            rows.append(_row(art, nm, lvl, pr, u, g))
            stats["早期单品行"] += 1

        # (e) 早期配对：A和B的价格分别为 x 元和 y 元
        for m in RE_EARLY_PAIR.finditer(seg):
            lvl, lu = level_at(seg, off, lvl_marks, m.start())
            unit = lu or default_unit
            if lvl is None:
                lvl = "retail_market"
            for nm, pr in ((m.group(1), clean_num(m.group(3))), (m.group(2), clean_num(m.group(4)))):
                if pr is None or not valid_crop(nm):
                    stats["品种名无效"] += 1
                    continue
                u, g = _unit_grade(nm, unit)
                rows.append(_row(art, nm, lvl, pr, u, g))
                stats["早期配对行"] += 1
    return rows


# ======================================================================
def main() -> None:
    index = json.loads((RAW / "article_index.json").read_text(encoding="utf-8"))
    print(f"文章索引 {len(index)} 篇"
          f"（col4139 {sum(1 for a in index if a['column']=='4139')} / "
          f"col4141 {sum(1 for a in index if a['column']=='4141')}）")

    stats: Counter = Counter()
    rows: list[dict] = []

    fg, fg_stats = build_price_tables(index)
    rows += fg
    print(f"[A] col4141 价格表（图片 OCR，汇总表+明细库表两版式）→ {len(fg)} 行；{dict(fg_stats)}")

    narr = []
    for art in index:
        if art["column"] != "4139" or not art.get("html"):
            continue
        narr += build_narrative(art, stats)
    rows += narr
    print(f"[B] col4139 叙述文本（批发/零售/产地）→ {len(narr)} 行；{dict(stats)}")

    if not rows:
        print("[WARN] 无解析结果")
        return

    df = pd.DataFrame(rows)
    # 去重键含 price_original：col4141 早期明细表按「价格区域」逐条发布，
    # 同一(日期,层级,品种)可能存在多个**真实不同**的区域价，保留而不做合并（不编造）。
    df = df.drop_duplicates(subset=["date", "price_level", "market_name", "crop_raw",
                                    "price_original", "unit_original"])
    df = df.sort_values(["date", "price_level", "crop_raw"]).reset_index(drop=True)

    # ---- OCR 量级质控（只标记、不改值）----
    # 图片 OCR 偶发小数点丢失（如「4.14」识成「414」），会产生远超同品种量级的离群值。
    # 与 parsers/jinzhou_ocr_parser.py 同一问题。此处**不修改数值**（避免编造），
    # 仅把同(层级,品种)中位数 8 倍之外的 OCR 行降级为 quality_grade=C，
    # 供下游按 quality_grade 过滤。叙述文本行不参与。
    ocr = df["raw_file"].str.endswith((".png", ".jpg"))
    med = (df[ocr & df["price_per_kg"].notna()]
           .groupby(["price_level", "crop_standard"])["price_per_kg"]
           .agg(["median", "size"]))
    med = med[med["size"] >= 15]["median"]
    key = pd.MultiIndex.from_arrays([df["price_level"], df["crop_standard"]])
    m = pd.Series(med.reindex(key).to_numpy(), index=df.index)
    ratio = df["price_per_kg"] / m
    flag = ocr & ((ratio > 8) | (ratio < 1 / 8))
    df.loc[flag, "quality_grade"] = "C"
    print(f"[QC] OCR 量级离群（同层同品种中位数8倍外）标记为 C：{int(flag.sum())} 行")

    cols = ["date", "city", "market_name", "crop_raw", "crop_standard", "price_original",
            "unit_original", "price_per_kg", "price_level", "source_id", "source_name",
            "source_url", "raw_file", "quality_grade"]
    df = df[cols]
    out = STAGING / "dalian_12316_prices.csv"
    df.to_csv(out, index=False, encoding="utf-8-sig")

    print(f"\n[OK] 写入 {out.relative_to(ROOT)}：{len(df)} 行")
    print(f"     日期范围 {df['date'].min()} ~ {df['date'].max()}，"
          f"{df['date'].nunique()} 个发布日")
    print(f"     city={sorted(df['city'].unique())}")
    print("\n按 price_level：")
    print(df.groupby("price_level").agg(
        行数=("price_level", "size"),
        品种数=("crop_standard", "nunique"),
        起始=("date", "min"), 结束=("date", "max")).to_string())
    print("\n各层品种数（剔除类别均价标签后）：")
    for lvl, g in df.groupby("price_level"):
        items = set(g.loc[~g["crop_raw"].isin(set(CATEGORIES) | set(CATEGORY_NORM)), "crop_standard"])
        print(f"  {lvl:14s} 品种 {len(items)} 种；含类别标签去重 {g['crop_standard'].nunique()}")
    print("\nquality_grade：", df.groupby("quality_grade").size().to_dict())
    print("unit_original：", df.groupby("unit_original").size().to_dict())
    print("price_per_kg 非空：", int(df["price_per_kg"].notna().sum()), "/", len(df))


if __name__ == "__main__":
    main()
