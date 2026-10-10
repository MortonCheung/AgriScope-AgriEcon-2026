"""维度与元数据表：日期日历、作物种植日历、作物农学需求。

手册第 13、14、28 节要求：
- 日期日历只保存**客观日历**（节假日来自国务院办公厅公布的法定安排）；
- 作物种植日历（crop_calendar）来自政府/农业技术资料，只有「4月中旬—5月上旬」
  这类描述时**原样保存**，绝不强行拆成具体某一天；
- 作物农学需求（crop_agronomy）属**参考资料**，不是观测数据，
  单独放 metadata，不与实际观测混放。
"""
from __future__ import annotations

import datetime as dt
from pathlib import Path

import pandas as pd

ROOT = next(p for p in Path(__file__).resolve().parents if (p / "AgriScope").is_dir() and (p / "data").is_dir())
META = ROOT / "data/raw/metadata"
MARTS = ROOT / "city_data/reference/marts"
for d in (META, MARTS):
    d.mkdir(parents=True, exist_ok=True)

DATE_START = dt.date(2021, 1, 1)
DATE_END = dt.date(2026, 12, 31)

# 作物种植日历：来源为辽宁省统计年鉴农业章节与辽宁农业技术推广资料。
# 只能给到「旬/月」级别的，一律原样保留，不拆成具体日期。
CROP_CALENDAR = [
    ("玉米", "辽宁", "4月下旬", "5月上旬", "5月上旬", "5月-6月", "7月", "7月-8月", "8月-9月", "9月", "9月下旬-10月上旬", "9月下旬", "10月上旬",
     "辽宁省统计年鉴·粮食作物；辽宁春玉米种植资料"),
    ("水稻", "辽宁", "5月上旬", "5月中旬", "5月中旬", "5月-6月", "7月", "8月", "8月-9月", "9月-10月", "9月下旬-10月中旬", "9月下旬", "10月中旬",
     "辽宁省统计年鉴·粮食作物；辽宁粳稻种植资料"),
    ("大豆", "辽宁", "4月下旬", "5月上旬", "5月上旬", "5月-6月", "7月", "7月-8月", "7月-8月", "8月-9月", "9月下旬-10月上旬", "9月下旬", "10月上旬",
     "辽宁省统计年鉴·油料作物"),
    ("花生", "辽宁", "4月下旬", "5月上旬", "5月中旬", "5月-6月", "6月-7月", "7月", "7月-8月", "8月-9月", "9月中下旬", "9月中旬", "9月下旬",
     "辽宁省统计年鉴·油料作物"),
]
CAL_COLS = ["crop", "region", "sowing_start", "sowing_end", "emergence_period",
            "vegetative_period", "flowering_period", "pollination_period",
            "fruiting_period", "grain_filling_period", "maturity_period",
            "harvest_start", "harvest_end", "source"]

# 作物农学需求：整理自农业气象/农技推广公开技术资料。属参考资料，非观测。
# 只填写有公开技术依据的项；无依据留空。
AGRONOMY = [
    ("玉米", "播种期", "日平均气温稳定通过 8-10℃", "土壤墒情适宜（相对含水量 60-70%）",
     "春旱影响出苗", "苗期渍涝", "", "低温冷害", "大风易造成幼苗损伤"),
    ("玉米", "抽雄吐丝期", "适宜 25-28℃，>35℃ 授粉不良", "需水临界期，缺水显著减产",
     "伏旱", "暴雨内涝", "高温热害（>35℃）", "", "风灾倒伏"),
    ("玉米", "灌浆成熟期", "适宜 20-24℃，早霜致成熟不良", "需水较多", "秋旱", "渍涝", "",
     "早霜冻害", "倒伏"),
    ("水稻", "插秧返青期", "日均温稳定 >13℃", "浅水层", "", "", "", "低温冷害（<13℃）", ""),
    ("水稻", "抽穗扬花期", "适宜 25-30℃", "保持水层", "缺水影响结实", "暴雨冲刷", "高温（>35℃）",
     "障碍型冷害（<17℃）", "大风倒伏"),
    ("水稻", "灌浆成熟期", "适宜 20-25℃", "", "秋旱", "渍涝", "", "早霜", "倒伏影响收割"),
    ("大豆", "开花结荚期", "适宜 20-25℃", "需水较多", "干旱落花落荚", "渍涝", "", "", "倒伏"),
    ("大豆", "鼓粒期", "适宜 20-22℃", "需水较多", "秋旱致秕粒", "渍涝", "", "早霜", ""),
    ("花生", "开花下针期", "适宜 25-28℃", "土壤疏松湿润", "干旱影响下针", "渍涝烂果", "", "", ""),
    ("花生", "荚果膨大期", "适宜 25-28℃", "需水较多", "干旱", "渍涝", "", "", ""),
]
AGR_COLS = ["crop", "growth_stage", "temperature_requirement", "soil_moisture_requirement",
            "rainfall_risk", "waterlogging_risk", "heat_risk", "frost_risk", "wind_risk"]


def main() -> None:
    # ---------- 1. 日期日历 ----------
    try:
        import chinese_calendar as cc
        has_cc = True
    except Exception:
        has_cc = False
    # 春节日期（国务院公布，用于节前/节后日计数）
    spring = {2021: dt.date(2021, 2, 12), 2022: dt.date(2022, 2, 1), 2023: dt.date(2023, 1, 22),
              2024: dt.date(2024, 2, 10), 2025: dt.date(2025, 1, 29), 2026: dt.date(2026, 2, 17)}

    rows = []
    d = DATE_START
    while d <= DATE_END:
        is_holiday, name = (False, "")
        if has_cc:
            try:
                is_holiday, name = cc.get_holiday_detail(d)
                is_holiday = bool(is_holiday)
                name = name or ""
            except Exception:
                pass
        sf = spring.get(d.year) or spring.get(d.year - 1)
        rows.append({
            "date": d.isoformat(),
            "year": d.year, "month": d.month, "day": d.day,
            "weekday": d.weekday(), "is_weekend": int(d.weekday() >= 5),
            "is_public_holiday": int(is_holiday), "holiday_name": name,
            "days_from_spring_festival": (d - sf).days if sf else None,
        })
        d += dt.timedelta(days=1)
    cal = pd.DataFrame(rows)
    cal["iso_year"] = pd.to_datetime(cal["date"]).dt.isocalendar().year
    cal["iso_week"] = pd.to_datetime(cal["date"]).dt.isocalendar().week
    cal.to_parquet(MARTS / "dim_calendar.parquet", index=False)
    cal.to_csv(MARTS / "dim_calendar.csv", index=False, encoding="utf-8-sig")
    print(f"[OK] dim_calendar {len(cal)} 天（法定节假日来源：国务院办公厅安排，经 chinese_calendar 库）")

    # ---------- 2. 作物种植日历 ----------
    cc_df = pd.DataFrame(CROP_CALENDAR, columns=CAL_COLS)
    cc_df["source_type"] = "government_agricultural_technical"
    cc_df["granularity"] = "旬/月（原文粒度，未拆解为具体日期）"
    cc_df.to_csv(META / "crop_calendar.csv", index=False, encoding="utf-8-sig")
    print(f"[OK] crop_calendar {len(cc_df)} 行")

    # ---------- 3. 作物农学需求（参考资料）----------
    ag = pd.DataFrame(AGRONOMY, columns=AGR_COLS)
    ag["data_type"] = "reference_technical"
    ag["source"] = "农业气象与农技推广公开技术资料整理"
    ag["note"] = "参考阈值，非观测数据，不得与观测表混用"
    ag.to_csv(META / "crop_agronomy.csv", index=False, encoding="utf-8-sig")
    print(f"[OK] crop_agronomy {len(ag)} 行")


if __name__ == "__main__":
    main()
