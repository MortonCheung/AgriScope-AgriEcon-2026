"""提取辽宁统计年鉴「各地区 / 主要城市」宽表（手册第 6、26、27、33 节）。

涵盖此前遗漏或误判为不可得的数据：
  01-04/05/06/07  主要城市 气温 / 相对湿度 / 降水量 / 日照时数  ← 官方城市气象汇总
  04-04           各地区年末总户数及总人口
  09-05           各市居民消费价格分类指数（CPI，含粮食/食用油/菜类/畜肉类等）
  10-05 / 10-14   各地区城镇 / 农村常住居民人均可支配收入
  03-08           各地区生产总值

不同表的表头结构不同，这里用「表头行探测」+「地区行识别」通用处理：
  - 行首为市名 / 「全省」的行为数据行
  - 表头取数据行之前的最后 1~2 行（含月份、年份或指标名）
原值照录，不做任何换算或补齐。
"""
from __future__ import annotations

import json
import re
from pathlib import Path

import pandas as pd
import xlrd

ROOT = next(p for p in Path(__file__).resolve().parents if (p / "AgriScope").is_dir() and (p / "data").is_dir())
RAW = ROOT / "data/raw" / "production"
CURATED = ROOT / "city_data/reference/curated"
MARTS = ROOT / "city_data/reference/marts"
for d in (CURATED, MARTS):
    d.mkdir(parents=True, exist_ok=True)

TARGET_CITIES = ["沈阳", "铁岭", "朝阳", "锦州", "丹东", "大连"]
YEARBOOK_YEAR = {"yearbook_2018": 2017, "yearbook_2019": 2018, "yearbook_2020": 2019,
                 "yearbook_2021": 2020, "yearbook_2022": 2021, "yearbook_2023": 2022,
                 "yearbook_2024": 2023, "yearbook_2025": 2024, "yearbook_2026": 2025}

# 表标题关键词 → (输出表名, 单位提示)
SPECS = [
    (re.compile(r"主要城市.*平均气温|主要城市平均气温"), "city_climate_monthly", "temperature", "℃"),
    (re.compile(r"主要城市.*相对湿度"), "city_climate_monthly", "humidity", "%"),
    (re.compile(r"主要城市.*降水量"), "city_climate_monthly", "precipitation", "mm"),
    (re.compile(r"主要城市.*日照时数"), "city_climate_monthly", "sunshine_duration", "h"),
    (re.compile(r"各地区年末总户数及总人口"), "city_population", None, ""),
    (re.compile(r"各市居民消费价格分类指数"), "city_cpi", "cpi", "上年=100"),
    (re.compile(r"各地区城镇常住居民人均可支配收入"), "city_income", "urban_disposable_income", "元"),
    (re.compile(r"各地区农村常住居民人均可支配收入"), "city_income", "rural_disposable_income", "元"),
    (re.compile(r"各地区生产总值"), "city_gdp", "gdp", "亿元"),
]


def norm(s) -> str:
    return re.sub(r"\s+", "", str(s or "")).replace("　", "")


# 辽宁全部 14 个地级市。**必须全部识别**——否则非目标城市（本溪、抚顺、鞍山…）
# 会被误判成「表头行」，导致其后城市的表头探测一路错位（曾使锦州列名退化成数值）。
ALL_LIAONING_CITIES = ["沈阳", "大连", "鞍山", "抚顺", "本溪", "丹东", "锦州", "营口",
                       "阜新", "辽阳", "盘锦", "铁岭", "朝阳", "葫芦岛"]


def is_city(v: str) -> tuple[bool, str]:
    """判断首列是否为地区行（含非目标城市，用于表头行排除）。"""
    t = norm(v)
    # 必须先判「全省」：若先做 re.sub(r"[市省]$") 会把「全省」削成「全」，导致漏判。
    if t in ("全省", "辽宁省", "总计", "合计"):
        return True, "全省"
    t2 = re.sub(r"[市省]$", "", t)
    if t2 in ALL_LIAONING_CITIES:
        return True, t2
    return False, ""


def read(path: Path) -> list[list[str]]:
    sh = xlrd.open_workbook(str(path)).sheet_by_index(0)
    return [[str(sh.cell_value(r, c)).strip() for c in range(sh.ncols)] for r in range(sh.nrows)]


def find_header(rows: list[list[str]], data_row: int) -> list[str]:
    """从数据行往上找最近的两个**非空**表头行拼出列名。

    年鉴表常在表头与数据之间留空行（如 CPI 表的 row5 为空），
    直接取 data_row-1/-2 会拿到空行，导致列名退化成数值本身。
    """
    hdr_rows: list[list[str]] = []
    i = data_row - 1
    while i >= 0 and len(hdr_rows) < 2:
        row = rows[i]
        # 跳过空行，以及**数据行**（首列是城市/全省的行不能被当成表头，
        # 否则列名会退化成上一行的数值）
        is_data_row = bool(row) and is_city(row[0])[0]
        if any(norm(x) for x in row) and not is_data_row:
            hdr_rows.append(row)
        i -= 1
    hdr_rows.reverse()
    r1 = hdr_rows[0] if len(hdr_rows) >= 2 else []
    r0 = hdr_rows[-1] if hdr_rows else []
    n = max(len(r0), len(r1))
    cols: list[str] = []
    for c in range(n):
        parts = []
        for rr in (r1, r0):
            if c < len(rr):
                v = norm(rr[c])
                if v and v not in parts:
                    parts.append(v)
        cols.append("/".join(parts) if parts else f"col{c}")
    return cols


def main() -> None:
    rows_out = []
    index = []

    for yb in sorted(RAW.glob("yearbook_*")):
        if not yb.is_dir():
            continue
        yb_year = YEARBOOK_YEAR.get(yb.name)
        for path in sorted(yb.glob("*.xls")):
            try:
                rows = read(path)
            except Exception:
                continue
            if not rows:
                continue
            title = norm(rows[0][0]) if rows[0] else ""
            spec = None
            for pat, tname, ind, unit in SPECS:
                if pat.search(title):
                    spec = (tname, ind, unit)
                    break
            if spec is None:
                continue
            tname, ind, unit = spec

            # 找数据行：第一列是城市/全省
            for ri, r in enumerate(rows):
                if not r:
                    continue
                ok, city = is_city(r[0])
                if not ok:
                    continue
                # 识别全部城市是为了正确排除数据行；但只输出六城市 + 全省
                if city not in TARGET_CITIES and city != "全省":
                    continue
                cols = find_header(rows, ri)
                # 自表头探测年份（形如 2019年）
                years = []
                for c in cols:
                    m = re.search(r"(20\d{2})", c)
                    years.append(int(m.group(1)) if m else None)
                for ci in range(1, len(r)):
                    raw = norm(r[ci])
                    if raw in ("", "-", "—", "…", "..."):
                        continue
                    try:
                        v = float(raw.replace(",", ""))
                    except ValueError:
                        continue
                    colname = cols[ci] if ci < len(cols) else f"col{ci}"
                    # 清理年鉴表头的占位符（「#粮食」→「粮食」）
                    colname = colname.lstrip("#").strip() or colname
                    # 丢弃表头探测失败的列：列名若只是数字串（如「102.6/71.8」），
                    # 说明取到了数据行而非表头，此类列不可信，直接跳过。
                    probe = re.sub(r"(20\d{2})年?", "", colname).strip("/ ")
                    if not probe or re.fullmatch(r"[\d./]+", probe):
                        continue
                    # 该列对应的年份：优先列名中的年份，其次年鉴卷年
                    y = years[ci] if ci < len(years) and years[ci] else yb_year
                    rows_out.append({
                        "yearbook_volume": yb_year,
                        "year": y,
                        "city": city,
                        "table": tname,
                        "indicator": ind or colname,
                        "column_label": colname,
                        "value": v,
                        "unit_raw": unit,
                        "source_file": f"{yb.name}/{path.name}",
                        "source": "辽宁省统计局 辽宁统计年鉴",
                    })
            index.append({"yearbook": yb.name, "file": path.name, "title": title,
                          "table": tname, "indicator": ind})

    (CURATED / "yearbook_wide_tables.json").write_text(
        json.dumps(index, ensure_ascii=False, indent=1), encoding="utf-8")

    df = pd.DataFrame(rows_out)
    if df.empty:
        print("[WARN] 未提取到宽表数据")
        return
    df.to_parquet(MARTS / "fact_yearbook_wide.parquet", index=False)
    df.to_csv(MARTS / "fact_yearbook_wide.csv", index=False, encoding="utf-8-sig")
    print(f"[OK] fact_yearbook_wide {len(df)} 行")
    print(df.groupby(["table", "indicator"]).size().to_string())

    # 单独导出官方城市气候（与再分析对照用）
    clim = df[df["table"] == "city_climate_monthly"]
    if not clim.empty:
        clim.to_parquet(MARTS / "fact_city_climate_official.parquet", index=False)
        clim.to_csv(MARTS / "fact_city_climate_official.csv", index=False, encoding="utf-8-sig")
        print(f"[OK] fact_city_climate_official {len(clim)} 行（年鉴官方城市气象汇总）")


if __name__ == "__main__":
    main()
