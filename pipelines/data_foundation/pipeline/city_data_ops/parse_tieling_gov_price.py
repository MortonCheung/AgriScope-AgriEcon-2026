"""铁岭县域政府零售价格：调兵山市发改局 + 开原市发改局 原始件解析为 30 列统一 schema。

原始件（本轮下载，未修改）：
  raw/price/diaobingshan_fgj/*.html   调兵山市发改局·主要农副产品价格监测（月度）
  raw/price/kaiyuan_fgj/*.pdf         开原市发改局·元旦节前"菜篮子米袋子"价格（省发改委转载）

禁止编造：价格数字全部以正则从原始文本中匹配，且逐条断言 "数值+元" 能在原文定位；
         不手工键入、不插值。标签经产品词表后缀匹配归一，避免前缀噪声。
单位：元/500克 或 元/斤 → price_per_kg = 价格 × 2；元/5升、无单位 → price_per_kg 留空。

用法：python3 parse_tieling_gov_price.py
"""

from __future__ import annotations

import csv
import html
import re
from datetime import datetime
from pathlib import Path

RAW = Path(next(p for p in Path(__file__).resolve().parents if (p / "AgriScope").is_dir() and (p / "data").is_dir())) / "data/raw/web_captures/tieling/price"
STAGING = Path(next(p for p in Path(__file__).resolve().parents if (p / "AgriScope").is_dir() and (p / "data").is_dir())) / "city_data/tieling/sources/staged/price/gov"
NOW = datetime.now().isoformat(timespec="seconds")

FIELDS = ["city", "county", "market_name", "store_name", "platform", "crop_raw", "crop_standard",
          "sku_name", "specification", "package_size", "price_original", "unit_original",
          "price_per_kg", "price_level", "observation_date", "observation_time", "frequency",
          "source_type", "source_name", "source_url", "source_id", "retrieval_time",
          "promotion_flag", "member_price_flag", "derived_flag", "quality_grade", "raw_file",
          "geo_level", "record_kind", "note"]

VOCAB = ["散装大米", "大米", "精粉", "面粉", "大豆调和油", "大豆油", "豆油", "玉米混等", "玉米",
         "鲜牛肉", "牛肉", "鲜羊肉", "羊肉", "猪肉去骨腰排肉", "猪肉去骨腰排", "猪肉去骨瘦肉",
         "去骨后腿肉", "去骨瘦肉", "去骨腰排肉", "去骨腰盘", "后腿肉", "腰排", "鸡蛋", "家鸡蛋",
         "白条鸡", "鲤鱼", "鲫鱼", "甘兰", "黄瓜", "角瓜", "绿茄子", "茄子", "芸豆", "尖椒",
         "西红柿", "菜花", "元椒", "鲜姜", "菠菜", "韭菜", "小白菜", "大白菜", "蒜苔", "土豆",
         "芹菜", "大葱", "大蒜", "鲜蘑", "洋葱", "青椒", "豆角", "葡萄", "香蕉", "苹果", "西瓜",
         "柑桔", "白梨", "梨"]
PORK = ("猪肉", "去骨", "后腿肉", "腰排", "腰盘", "瘦肉")

STD = {"鲜牛肉": "牛肉", "牛肉": "牛肉", "鲜羊肉": "羊肉", "羊肉": "羊肉", "家鸡蛋": "鸡蛋",
       "白条鸡": "鸡肉", "精粉": "面粉", "面粉": "面粉", "豆油": "豆油", "大豆油": "豆油",
       "大豆调和油": "豆油", "散装大米": "大米", "大米": "大米", "玉米混等": "玉米",
       "甘兰": "甘蓝", "元椒": "青椒", "绿茄子": "茄子", "鲜姜": "生姜", "柑桔": "柑橘"}


def std(name: str) -> str:
    if name in STD:
        return STD[name]
    if any(p in name for p in PORK):
        return "猪肉"
    return name


def per_kg(price: float, unit: str):
    return round(price * 2, 4) if unit in ("元/斤", "元/500克") else ""


def body_text(path: Path) -> str:
    t = path.read_text(encoding="utf-8", errors="ignore")
    t = re.sub(r"<script.*?</script>", "", t, flags=re.S)
    t = re.sub(r"<style.*?</style>", "", t, flags=re.S)
    t = html.unescape(re.sub("<[^>]+>", " ", t))
    return re.sub(r"\s+", "", t)


def label_products(raw: str) -> list[tuple[str, str]]:
    """把捕获串归一为 [(产品词表名, 规格)]。无法对入词表则丢弃（不产出噪声行）。"""
    l = raw
    for sep in "。：，；、":
        if sep in l:
            l = l.split(sep)[-1]
    l = re.sub(r"^(其中|目前|具体情况肉|据监测信息显示|监测数据显示|显示)+", "", l)
    l = l.replace("销售价格", "").replace("零售价格", "").replace("价格", "").replace("本期", "")
    l = re.sub(r"^(三种|两种|一种)", "", l)
    l = l.strip("为是的 均")
    if not l:
        return []
    spec = ""
    m = re.match(r"^(.*?)（(.*?)）(.*)$", l)
    if m:
        l, spec = (m.group(1) + m.group(3)).strip(), m.group(2)
    parts = [p for p in l.split("和") if p]
    if len(parts) > 1 and all(tail_product(p) for p in parts):
        return [(tail_product(p), spec) for p in parts]
    single = tail_product(l)
    return [(single, spec)] if single else []


def tail_product(s: str) -> str | None:
    s = s.strip(" 均")
    if not s:
        return None
    for v in sorted(VOCAB, key=len, reverse=True):
        if s.endswith(v):
            return v
    if any(p in s for p in PORK):
        return "猪肉"
    return None


PAT_A = re.compile(r"([\u4e00-\u9fa5A-Za-z（）()]{1,18}?)(?:销售)?(?:零售)?(?:价格)?(?:为|是)?约?"
                   r"(\d+(?:\.\d+)?)\s*元/(500克|斤|公斤|5升|升)")


def add(rows, text, path, county, market, name, spec, price, unit, odate, note,
        source_id, source_name):
    if not isinstance(price, str) or f"{price}元" not in text.replace(" ", ""):
        return
    rows.append(_row(path, county, market, name, spec, float(price), unit, odate, note,
                     source_id, source_name))


def rows_from_html(path: Path) -> list[dict]:
    t = body_text(path)
    mtime = re.search(r"时间：(\d{4}-\d{2}-\d{2})", t)
    odate = mtime.group(1) if mtime else None
    seg = t[t.find("来源：调兵山市发改局"):] if "来源：调兵山市发改局" in t else t
    sid, sname = "SRC-DBS-FGJ", "调兵山市发改局"
    rows: list[dict] = []
    if "本期每斤" in seg:
        _yangli_2023_05(rows, seg, path, odate, sid, sname)
        return rows
    for m in PAT_A.finditer(seg):
        price, unit = m.group(2), "元/" + m.group(3)
        for name, spec in label_products(m.group(1)):
            add(rows, seg, path, "调兵山市", "调兵山市贸易城", name, spec, price, unit,
                odate, f"原文：{m.group(0)}", sid, sname)
    return rows


def _yangli_2023_05(rows, seg, path, odate, sid, sname):
    pairs = [(r"大米本期价格(\d+(?:\.\d+)?)元、面粉（精粉）本期价格(\d+(?:\.\d+)?)元、"
              r"豆油本期价格(\d+(?:\.\d+)?)元",
              [("大米", ""), ("精粉", ""), ("豆油", "")], "元"),
             (r"三种鲜猪肉（去骨腰盘、去骨后腿肉和去骨瘦肉）价格下降，本期每斤零售价分别为"
              r"(\d+(?:\.\d+)?)元、(\d+(?:\.\d+)?)元、(\d+(?:\.\d+)?)元",
              [("猪肉", "去骨腰盘"), ("猪肉", "去骨后腿肉"), ("猪肉", "去骨瘦肉")], "元/斤"),
             (r"鸡蛋本期每斤价格(\d+(?:\.\d+)?)元", [("鸡蛋", "")], "元/斤"),
             (r"牛肉、羊肉、白条鸡、鲤鱼、鲫鱼本期每斤价格分别为(\d+(?:\.\d+)?)元、"
              r"(\d+(?:\.\d+)?)元、(\d+(?:\.\d+)?)元、(\d+(?:\.\d+)?)元，(\d+(?:\.\d+)?)元",
              [("牛肉", ""), ("羊肉", ""), ("白条鸡", ""), ("鲤鱼", ""), ("鲫鱼", "")], "元/斤"),
             (r"大葱、大蒜、鲜姜、鲜蘑、蒜苔、土豆等六种蔬菜价格发生上涨，本期每斤价格分别为"
              r"(\d+(?:\.\d+)?)元、(\d+(?:\.\d+)?)元、(\d+(?:\.\d+)?)元、(\d+(?:\.\d+)?)元、"
              r"(\d+(?:\.\d+)?)元、(\d+(?:\.\d+)?)元",
              [("大葱", ""), ("大蒜", ""), ("鲜姜", ""), ("鲜蘑", ""), ("蒜苔", ""), ("土豆", "")],
              "元/斤"),
             (r"芸豆、西红柿本期每斤价格分别为(\d+(?:\.\d+)?)元、(\d+(?:\.\d+)?)元",
              [("芸豆", ""), ("西红柿", "")], "元/斤"),
             (r"柑桔、香蕉、白梨、苹果本期每斤价格分别为(\d+(?:\.\d+)?)元、(\d+(?:\.\d+)?)元、"
              r"(\d+(?:\.\d+)?)元、(\d+(?:\.\d+)?)元",
              [("柑桔", ""), ("香蕉", ""), ("白梨", ""), ("苹果", "")], "元/斤"),
             (r"西瓜价格“腰斩”，本期每斤价格为(\d+(?:\.\d+)?)元", [("西瓜", "")], "元/斤")]
    for pat, names, unit in pairs:
        m = re.search(pat, seg)
        if not m:
            continue
        for (name, spec), price in zip(names, m.groups()):
            add(rows, seg, path, "调兵山市", "调兵山市贸易城", name, spec, price, unit, odate,
                "原文：本期每斤价格；原文未逐条列名" if "每斤" in pat else f"原文：{m.group(0)}",
                sid, sname)


def rows_from_pdf(path: Path) -> list[dict]:
    import pypdf
    text = re.sub(r"\s+", "", "\n".join((p.extract_text() or "") for p in pypdf.PdfReader(str(path)).pages))
    odate = "2022-01-06"
    sid, sname = "SRC-KY-FGJ", "开原市发改局（辽宁省发改委转载）"
    rows: list[dict] = []
    for m in PAT_A.finditer(text):
        for name, spec in label_products(m.group(1)):
            add(rows, text, path, "开原市", "开原市农贸市场", name, spec, m.group(2),
                "元/" + m.group(3), odate, f"原文：{m.group(0)}", sid, sname)
    return rows


def _row(path, county, market, name, spec, price, unit, odate, note, source_id, source_name) -> dict:
    return {
        "city": "铁岭", "county": county, "market_name": market, "store_name": "",
        "platform": "gov_price_monitor", "crop_raw": name, "crop_standard": std(name),
        "sku_name": "", "specification": spec, "package_size": "",
        "price_original": price, "unit_original": unit, "price_per_kg": per_kg(price, unit),
        "price_level": "retail_market", "observation_date": odate, "observation_time": "",
        "frequency": "monthly", "source_type": "government", "source_name": source_name,
        "source_url": _url(path, source_id), "source_id": source_id, "retrieval_time": NOW,
        "promotion_flag": "", "member_price_flag": "", "derived_flag": "", "quality_grade": "B",
        "raw_file": f"data/raw/web_captures/tieling/price/{path.parent.name}/{path.name}",
        "geo_level": "county", "record_kind": "", "note": note,
    }


def _url(path: Path, source_id: str) -> str:
    m = re.search(r"_(\d{19})\.html$", path.name)
    if source_id == "SRC-DBS-FGJ" and m:
        return f"http://www.lndbss.gov.cn/diaobingshan/zfxxgk/fdzdgknr/qtfdxx/ffhjzdfx/{m.group(1)}/index.html"
    if source_id == "SRC-KY-FGJ":
        return "https://fgw.ln.gov.cn/fgw/articleFileDir/2022-01/06/4487360/P020220106600029608829.pdf"
    return ""


def main() -> None:
    rows: list[dict] = []
    for p in sorted((RAW / "diaobingshan_fgj").glob("*.html")):
        rows += rows_from_html(p)
    for p in sorted((RAW / "kaiyuan_fgj").glob("*.pdf")):
        rows += rows_from_pdf(p)
    seen, out = set(), []
    for r in rows:
        k = (r["county"], r["crop_raw"], r["specification"], r["observation_date"],
             r["price_original"], r["unit_original"])
        if k in seen:
            continue
        seen.add(k)
        out.append(r)
    out.sort(key=lambda x: (x["observation_date"] or "", x["county"], x["crop_raw"]))
    STAGING.mkdir(parents=True, exist_ok=True)
    with (STAGING / "tieling_price_gov_retail.csv").open("w", newline="", encoding="utf-8-sig") as fh:
        w = csv.DictWriter(fh, fieldnames=FIELDS)
        w.writeheader()
        w.writerows(out)
    print(f"[gov] rows={len(out)} -> tieling_price_gov_retail.csv")
    for r in out:
        print(f"  {r['observation_date']} {r['county']} {r['crop_raw']}/{r['crop_standard']} "
              f"{r['price_original']}{r['unit_original']} spec={r['specification']}")


if __name__ == "__main__":
    main()
