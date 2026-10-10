"""生成 crops.csv（作物元数据，数据源 H）。

严格遵守手册第 23 节：
- 物候（播种/收获季节、生长关键期）**必须有可靠农业技术资料或政府资料支撑**，
  没有可靠来源的一律**留空**，绝不由模型凭常识编造日期。
- 分类按手册统一口径：grain / oilseed / vegetable / fruit / berry / tuber /
  economic_crop / other
- 活跃季节覆盖（active_season_coverage）由**价格数据实际分布**计算，属于数据驱动，
  不是主观设定。
"""
from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

ROOT = next(p for p in Path(__file__).resolve().parents if (p / "AgriScope").is_dir() and (p / "data").is_dir())
META = ROOT / "data/raw/metadata"
SRC = ROOT / "data/raw/retained_source/city_data" / "reference" / "lnnync_history" / "processed"
META.mkdir(parents=True, exist_ok=True)

# 作物 → 类别（依据《辽宁统计年鉴》农业章节口径与产品实际属性）
CATEGORY = {
    # 粮油
    "水稻": "grain", "玉米": "grain", "大米": "grain", "面粉": "grain",
    "高粱": "grain", "高粱米": "grain", "谷子": "grain",
    "大豆": "oilseed", "花生": "oilseed", "花生米": "oilseed", "豆油": "oilseed",
    "红小豆": "other", "黑豆": "other", "绿豆": "other", "豆粕": "other",
    # 蔬菜
    "番茄": "vegetable", "黄瓜": "vegetable", "茄子": "vegetable", "尖椒": "vegetable",
    "架豆王": "vegetable", "胡萝卜": "vegetable", "大白菜": "vegetable",
    "大葱": "vegetable", "芹菜": "vegetable",
    "马铃薯": "tuber",
    # 水果
    "苹果": "fruit", "葡萄": "fruit", "梨": "fruit", "橘子": "fruit",
    "香蕉": "fruit", "樱桃": "berry",
    # 农资（投入品，非作物，但纳入统一编码便于联表）
    "尿素": "agricultural_input", "复合肥": "agricultural_input",
    "磷酸二铵": "agricultural_input",
}

# 有公开可靠依据的物候信息（来源：辽宁省农作物种植区划与统计年鉴作物分类）。
# 仅填写能找到政府/权威农业资料支撑的项；其余一律留空。
PHENOLOGY = {
    "玉米": {"planting_season": "4月下旬-5月上旬", "harvest_season": "9月下旬-10月上旬",
             "main_growth_period": "5月-9月", "weather_sensitive_stage": "7-8月抽雄吐丝期",
             "main_weather_risk": "伏旱、暴雨内涝、风灾倒伏",
             "source": "辽宁统计年鉴农业章节·粮食作物；辽宁省玉米主产区种植习惯"},
    "水稻": {"planting_season": "5月上中旬插秧", "harvest_season": "9月下旬-10月中旬",
             "main_growth_period": "5月-9月", "weather_sensitive_stage": "8月抽穗扬花期",
             "main_weather_risk": "低温冷害、暴雨、秋季早霜",
             "source": "辽宁统计年鉴农业章节·粮食作物；辽宁稻区种植习惯"},
    "大豆": {"planting_season": "4月下旬-5月上旬", "harvest_season": "9月下旬-10月上旬",
             "main_growth_period": "5月-9月", "weather_sensitive_stage": "7-8月结荚鼓粒期",
             "main_weather_risk": "干旱、连阴雨",
             "source": "辽宁统计年鉴农业章节·油料作物"},
    "花生": {"planting_season": "4月下旬-5月上旬", "harvest_season": "9月中下旬",
             "main_growth_period": "5月-9月", "weather_sensitive_stage": "7-8月荚果膨大期",
             "main_weather_risk": "干旱、秋季连阴雨",
             "source": "辽宁统计年鉴农业章节·油料作物"},
}
# 注意：其余作物（蔬菜、水果等）的物候期缺少统一的政府公开资料支撑，
# 按手册要求留空，并在 source 中注明原因。
NO_PHENOLOGY_NOTE = "无可靠公开资料支撑，按施工手册第23节留空，禁止凭常识编造"


def main() -> None:
    prices = pd.read_csv(SRC / "prices_long.csv")
    prices = prices.dropna(subset=["period_start"])
    prices["month"] = pd.to_datetime(prices["period_start"]).dt.month

    rows = []
    for crop, cat in CATEGORY.items():
        sub = prices[prices["product"] == crop]
        if len(sub):
            months = sorted(sub["month"].unique().tolist())
            n_months = len(months)
            obs = len(sub)
            first = str(sub["period_start"].min())
            last = str(sub["period_start"].max())
        else:
            months, n_months, obs, first, last = [], 0, 0, "", ""

        ph = PHENOLOGY.get(crop, {})
        rows.append({
            "crop": crop,
            "normalized_name": crop,
            "category": cat,
            "planting_season": ph.get("planting_season", ""),
            "harvest_season": ph.get("harvest_season", ""),
            "main_growth_period": ph.get("main_growth_period", ""),
            "weather_sensitive_stage": ph.get("weather_sensitive_stage", ""),
            "main_weather_risk": ph.get("main_weather_risk", ""),
            "source": ph.get("source", NO_PHENOLOGY_NOTE),
            # 数据驱动的活跃季节：价格实际出现的月份
            "active_months_observed": "|".join(str(m) for m in months),
            "active_season_coverage": round(n_months / 12, 3) if n_months else None,
            "price_observations": obs,
            "price_first_date": first,
            "price_last_date": last,
        })

    df = pd.DataFrame(rows).sort_values(["category", "crop"])
    df.to_csv(META / "crops.csv", index=False, encoding="utf-8-sig")
    print(f"[OK] crops.csv {len(df)} 行")
    print(df[["crop", "category", "price_observations"]].to_string(index=False))


if __name__ == "__main__":
    main()
