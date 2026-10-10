"""将三类主表（物候/真实灾害/政策）分发到 city_data 各城 interim，并回填原始文件。

来源（/）：
  city_data/reference/staging/phenology_events.csv             物候（县域农时）
  city_data/reference/marts/fact_disaster_event_observed.csv   真实灾害（官方口径）
  city_data/reference/marts/fact_policy_event.csv              政策/保供

输出：
  city_data/<city>/workspace/data/interim/phenology_events.csv          本市物候（14 列规范）
  city_data/<city>/workspace/data/interim/disaster_events_observed.csv  本市真实灾害（主表 schema）
  city_data/<city>/workspace/data/interim/policy_events.csv             本市政策（主表 schema）
  city_data/reference/{disaster_events_observed_province,policy_events_province}.csv
                                                                        省级口径，独立共享层
  各城 raw/{phenology,disaster,policy}//<hash>.html   原始 HTML 回填

红线：
  - 省级（spatial_level/level=province）**不写进任何城市**，只放 reference/，绝不分摊为城市事实。
  - 不编造、不推算灾损；面积/损失只来自原文。
"""
from __future__ import annotations

import csv
import shutil
from pathlib import Path

CITY_DATA = next(p for p in Path(__file__).resolve().parents if (p / "AgriScope").is_dir() and (p / "data").is_dir()) / "data/raw/retained_source/city_data"
PROJ = CITY_DATA.parent

CN2EN = {"沈阳": "shenyang", "大连": "dalian", "丹东": "dandong",
         "锦州": "jinzhou", "铁岭": "tieling", "朝阳": "chaoyang"}

PHEN_FIELDS = ["city", "county", "crop_raw", "crop_standard", "year", "stage",
               "start_date", "end_date", "date_precision", "source_id", "source_url",
               "source_text", "quality_grade", "derived_from_text"]

CROP_ALIAS = {"设施蔬菜": "蔬菜", "设施农业": "蔬菜", "设施": "蔬菜",
              "杂粮": "杂粮", "鲜食玉米": "玉米"}

SRC_BY_DOMAIN = {
    "nync.ln.gov.cn": "SRC-LNNYNC",
    "slt.ln.gov.cn": "SRC-LNSLT",
    "yjgl.ln.gov.cn": "SRC-LNYJGL",
    "fgw.ln.gov.cn": "SRC-LNFGW",
    "swt.ln.gov.cn": "SRC-LNSWT",
    "lcj.ln.gov.cn": "SRC-LNLCJ",
    "ln.cma.gov.cn": "SRC-LNCMA",
    "www.ln.gov.cn": "SRC-LNGOV",
    "www.tieling.gov.cn": "SRC-TIELING-GOV",
    "www.chaoyang.gov.cn": "SRC-CY-GOV",
    "nyncj.chaoyang.gov.cn": "SRC-CY-NYNCJ",
    "www.dandong.gov.cn": "SRC-DANDONG-GOV",
    "nyncj.jz.gov.cn": "SRC-JZ-NYNCJ",
    "yjj.jz.gov.cn": "SRC-JZ-YJJ",
    "sswj.jz.gov.cn": "SRC-JZ-SSWJ",
    "www.jz.gov.cn": "SRC-JZ-GOV",
    "www.dl.gov.cn": "SRC-DALIAN-GOV",
    "lnjp.gov.cn": "SRC-JP-GOV",
    "www.lnjp.gov.cn": "SRC-JP-GOV",
    "www.bp.gov.cn": "SRC-BP-GOV",
}


def source_id(url: str) -> str:
    dom = (url or "").split("/")[2] if "//" in (url or "") else ""
    return SRC_BY_DOMAIN.get(dom, f"SRC-{dom}" if dom else "")


def read_csv(path: Path) -> list[dict]:
    if not path.exists():
        return []
    with path.open(encoding="utf-8-sig", newline="") as fh:
        return list(csv.DictReader(fh))


def write_csv(path: Path, fields: list[str], rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=fields)
        w.writeheader()
        for r in rows:
            w.writerow({k: r.get(k, "") for k in fields})


def copy_raw(raw_file: str, topic: str, base: Path) -> str:
    src = PROJ / raw_file
    if not raw_file or not src.exists():
        return ""
    dst = base.parents[4] / "data/raw" / "web_captures" / base.parent.name / topic / src.name
    dst.parent.mkdir(parents=True, exist_ok=True)
    if not dst.exists():
        shutil.copy2(src, dst)
    return str(dst.relative_to(base))


def phen_to_schema(r: dict) -> dict:
    crop = (r.get("crop") or "").strip()
    date = (r.get("date") or "").strip()
    return {
        "city": r.get("city", ""),
        "county": r.get("county", ""),
        "crop_raw": crop,
        "crop_standard": CROP_ALIAS.get(crop, crop),
        "year": r.get("year", ""),
        "stage": r.get("stage", ""),
        "start_date": date,
        "end_date": date,
        "date_precision": "day" if len(date) == 10 else "unknown",
        "source_id": source_id(r.get("source_url", "")),
        "source_url": r.get("source_url", ""),
        "source_text": (r.get("note") or r.get("title") or "")[:500],
        "quality_grade": r.get("quality_grade", ""),
        "derived_from_text": r.get("stage_detail", ""),
    }


def main() -> None:
    phen = read_csv(PROJ / "city_data/reference/staging" / "phenology_events.csv")
    dis = read_csv(PROJ / "city_data/reference/marts" / "fact_disaster_event_observed.csv")
    pol = read_csv(PROJ / "city_data/reference/marts" / "fact_policy_event.csv")
    dis_fields = list(dis[0].keys()) if dis else []
    pol_fields = list(pol[0].keys()) if pol else []

    dis_city = [r for r in dis if (r.get("spatial_level") or "") in ("city", "county")]
    dis_prov = [r for r in dis if (r.get("spatial_level") or "") == "province"]
    pol_city = [r for r in pol if (r.get("level") or "") == "city"]
    pol_prov = [r for r in pol if (r.get("level") or "") == "province"]

    print(f"主表：phenology={len(phen)} disaster={len(dis)}(城{len(dis_city)}/省{len(dis_prov)}) "
          f"policy={len(pol)}(城{len(pol_city)}/省{len(pol_prov)})\n")
    summary = {}
    for cn, en in CN2EN.items():
        base = CITY_DATA / en / "data"
        p_rows = [phen_to_schema(r) for r in phen if (r.get("city") or "") == cn]
        d_rows = [r for r in dis_city if (r.get("city") or "") == cn]
        o_rows = [r for r in pol_city if (r.get("city") or "") == cn]

        write_csv(base / "interim" / "phenology_events.csv", PHEN_FIELDS, p_rows)
        write_csv(base / "interim" / "disaster_events_observed.csv", dis_fields, d_rows)
        write_csv(base / "interim" / "policy_events.csv", pol_fields, o_rows)

        n_raw = 0
        for r in phen:
            if (r.get("city") or "") == cn and copy_raw(r.get("raw_file", ""), "phenology", base):
                n_raw += 1
        for r in d_rows:
            if copy_raw(r.get("raw_file", ""), "disaster", base):
                n_raw += 1
        for r in o_rows:
            if copy_raw(r.get("raw_file", ""), "policy", base):
                n_raw += 1
        summary[cn] = (len(p_rows), len(d_rows), len(o_rows))
        print(f"{cn:<3} 物候={len(p_rows):<3} 灾害={len(d_rows):<3} 政策={len(o_rows):<3} raw={n_raw}")

    ref = CITY_DATA / "reference"
    write_csv(ref / "disaster_events_observed_province.csv", dis_fields, dis_prov)
    write_csv(ref / "policy_events_province.csv", pol_fields, pol_prov)
    n_ref = 0
    for r in dis_prov:
        if copy_raw(r.get("raw_file", ""), "disaster", ref):
            n_ref += 1
    for r in pol_prov:
        if copy_raw(r.get("raw_file", ""), "policy", ref):
            n_ref += 1
    print(f"\nreference/: 省级灾害={len(dis_prov)} 省级政策={len(pol_prov)} raw={n_ref}")
    print("城市合计：物候=%d 灾害=%d 政策=%d" % (
        sum(v[0] for v in summary.values()),
        sum(v[1] for v in summary.values()),
        sum(v[2] for v in summary.values())))


if __name__ == "__main__":
    main()
