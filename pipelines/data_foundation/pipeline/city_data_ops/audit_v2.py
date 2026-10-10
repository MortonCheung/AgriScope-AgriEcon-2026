"""AgriScope city_data 现状审计 V2 + 缺口分析。

输入：city_data/<city>/workspace/data/interim/*.csv
输出（写入 city_data/_gap_analysis_20260922/）：
  CITY_DATA_AUDIT_V2.csv            每城×数据集真实统计
  PRODUCTION_UNIT_QC.csv            生产单位(吨/万吨)与公式一致性 QC
  CORE_CROP_CANDIDATES.csv          跨城核心作物候选
  COMMON_TIME_WINDOW_AUDIT.csv      同作物×同price_level 跨城共同时间窗
  RESEARCH_TREE_DATA_GAPS.csv       研究树缺口表
"""
from __future__ import annotations

from datetime import datetime
from pathlib import Path

import pandas as pd

ROOT = next(p for p in Path(__file__).resolve().parents if (p / "AgriScope").is_dir() and (p / "data").is_dir()) / "data/raw/retained_source/city_data"          # city_data/
OUT = ROOT.parent / "archive" / "audits" / "gap_analysis_20260922"
OUT.mkdir(exist_ok=True)

CITIES = ["shenyang", "tieling", "jinzhou", "dandong", "dalian", "chaoyang"]
CN = {"shenyang": "沈阳", "tieling": "铁岭", "jinzhou": "锦州",
      "dandong": "丹东", "dalian": "大连", "chaoyang": "朝阳"}
FIVE = ["tieling", "jinzhou", "dandong", "dalian", "chaoyang"]

PRICE_LEVELS = ["farm_gate", "wholesale", "market_average", "retail_market", "supermarket"]


def interim(city: str) -> Path:
    return ROOT / city / "data"


def read(city: str, name: str):
    p = interim(city) / name
    if not p.exists():
        return None
    try:
        return pd.read_csv(p, encoding="utf-8-sig", low_memory=False)
    except Exception:
        return None


# ---------------- 1. 审计 ----------------
def audit() -> pd.DataFrame:
    rows = []
    for c in CITIES:
        d = interim(c)
        if not d.exists():
            continue
        for f in sorted(d.glob("*.csv")):
            try:
                df = pd.read_csv(f, encoding="utf-8-sig", low_memory=False)
            except Exception:
                continue
            datecol = next((x for x in ("observation_date", "date", "year", "publish_date",
                                        "policy_date", "start_date") if x in df.columns), None)
            sdt = df[datecol].astype(str) if datecol else pd.Series(dtype=str)
            rows.append({
                "city": CN[c], "dataset": f.stem, "rows": len(df), "columns": df.shape[1],
                "unique_dates": int(sdt.nunique()) if len(sdt) else 0,
                "start_date": sdt.min() if len(sdt) else "",
                "end_date": sdt.max() if len(sdt) else "",
                "crop_count": int(df["crop_standard"].nunique()) if "crop_standard" in df.columns
                              else (int(df["crop"].nunique()) if "crop" in df.columns else 0),
                "source_count": int(df["source_id"].nunique()) if "source_id" in df.columns else 0,
            })
    return pd.DataFrame(rows)


# ---------------- 2. 生产单位 QC ----------------
def production_qc() -> pd.DataFrame:
    out = []
    for c in CITIES:
        df = read(c, "production_yearly.csv")
        if df is None or "production" not in df.columns:
            continue
        for r in df.itertuples(index=False):
            rd = r._asdict()
            area = rd.get("planting_area")
            prod = rd.get("production")
            yld = rd.get("yield_per_area")
            upa = str(rd.get("unit_planting_area") or "")
            upr = str(rd.get("unit_production") or "")
            note = str(rd.get("note") or "")
            flag = []
            # 公式一致性：yield ≈ production/area（注意单位：千公顷 & 万吨 → 公斤/公顷）
            try:
                a, p, y = float(area), float(prod), float(yld)
                if a and p and y:
                    # 千公顷 & 万吨 -> 吨/公顷 = p*10000/(a*1000)=p*10/a；公斤/公顷 = p*10000/a
                    if "千公顷" in upa and "万吨" in upr:
                        calc = p * 10000 / a
                        if abs(calc - y) / max(y, 1e-9) > 0.05:
                            flag.append(f"公式不符(算{calc:.1f} vs 报{y:.1f})")
            except (TypeError, ValueError):
                pass
            if "吨" in upr and "万" not in upr:
                flag.append("产量单位=吨(需核对是否本应万吨)")
            out.append({
                "city": CN[c], "year": rd.get("year"), "crop": rd.get("crop"),
                "planting_area": area, "unit_area": upa,
                "production": prod, "unit_production": upr,
                "yield_per_area": yld, "unit_yield": rd.get("unit_yield"),
                "qc_consistency": rd.get("qc_consistency"),
                "flags": "; ".join(flag), "note": note[:60],
            })
    return pd.DataFrame(out)


# ---------------- 3. 核心作物候选 ----------------
def core_crops(prices: dict) -> pd.DataFrame:
    crops = set()
    for c in FIVE + ["shenyang"]:
        d = prices.get(c)
        if d is not None and "crop_standard" in d.columns:
            crops |= set(d["crop_standard"].dropna().unique())
    prod_crops = {}
    for c in FIVE + ["shenyang"]:
        pd_ = read(c, "production_yearly.csv")
        if pd_ is not None and "crop" in pd_.columns:
            prod_crops[c] = set(pd_["crop"].dropna().astype(str).unique())
    rows = []
    for crop in sorted(crops):
        r = {"crop_standard": crop}
        pcities = 0
        for c in FIVE + ["shenyang"]:
            d = prices.get(c)
            if d is None or "crop_standard" not in d.columns:
                r[f"{c}_rows"] = 0; r[f"{c}_days"] = 0
                continue
            sub = d[d["crop_standard"] == crop]
            r[f"{c}_rows"] = len(sub)
            r[f"{c}_days"] = int(sub["observation_date"].nunique()) if len(sub) else 0
            if len(sub):
                pcities += 1
        ppcities = sum(1 for c in FIVE if crop in prod_crops.get(c, set()))
        r["cities_with_price"] = pcities
        r["cities_with_production"] = ppcities
        allp = pd.concat([prices[c] for c in FIVE + ["shenyang"]
                          if prices.get(c) is not None], ignore_index=True)
        sub = allp[allp["crop_standard"] == crop]
        r["first_date"] = sub["observation_date"].min() if len(sub) else ""
        r["last_date"] = sub["observation_date"].max() if len(sub) else ""
        r["main_price_level"] = sub["price_level"].mode().iloc[0] if len(sub) and sub["price_level"].notna().any() else ""
        r["total_rows"] = len(sub)
        # 研究价值：多城+多日+有生产
        r["research_value"] = round(pcities * 1.0 + min(r["total_rows"], 5000) / 1000
                                    + ppcities * 0.5, 2)
        r["priority"] = "P1" if (pcities >= 4 and r["total_rows"] > 500) else (
            "P2" if pcities >= 2 else "P3")
        rows.append(r)
    df = pd.DataFrame(rows).sort_values(["cities_with_price", "total_rows"], ascending=False)
    return df


# ---------------- 4. 共同时间窗 ----------------
def common_window(prices: dict) -> pd.DataFrame:
    out = []
    for c in FIVE + ["shenyang"]:
        d = prices.get(c)
        if d is None or "crop_standard" not in d.columns:
            continue
        d = d.copy()
        d["observation_date"] = pd.to_datetime(d["observation_date"], errors="coerce")
        d = d.dropna(subset=["observation_date"])
        for (crop, lvl), g in d.groupby(["crop_standard", "price_level"]):
            if pd.isna(lvl):
                continue
            g = g.sort_values("observation_date")
            days = g["observation_date"].dt.date.nunique()
            gaps = g["observation_date"].drop_duplicates().diff().dt.days.dropna()
            span = (g["observation_date"].max() - g["observation_date"].min()).days + 1
            out.append({
                "city": CN[c], "crop_standard": crop, "price_level": lvl,
                "first_date": str(g["observation_date"].min().date()),
                "last_date": str(g["observation_date"].max().date()),
                "unique_days": days,
                "unique_weeks": g["observation_date"].dt.to_period("W").nunique(),
                "unique_months": g["observation_date"].dt.to_period("M").nunique(),
                "coverage_ratio": round(days / span, 4) if span else 0,
                "median_gap_days": float(gaps.median()) if len(gaps) else None,
                "max_gap_days": float(gaps.max()) if len(gaps) else None,
                "source_count": int(g["source_id"].nunique()) if "source_id" in g.columns else 0,
            })
    return pd.DataFrame(out)


def main() -> None:
    prices = {c: read(c, "price_observation.csv") for c in CITIES}
    a = audit(); a.to_csv(OUT / "CITY_DATA_AUDIT_V2.csv", index=False, encoding="utf-8-sig")
    print(f"[OK] CITY_DATA_AUDIT_V2.csv {a.shape}")
    q = production_qc(); q.to_csv(OUT / "PRODUCTION_UNIT_QC.csv", index=False, encoding="utf-8-sig")
    nflag = int((q["flags"].astype(str).str.len() > 0).sum()) if len(q) else 0
    print(f"[OK] PRODUCTION_UNIT_QC.csv {q.shape}，异常 {nflag} 行")
    cc = core_crops(prices); cc.to_csv(OUT / "CORE_CROP_CANDIDATES.csv", index=False, encoding="utf-8-sig")
    print(f"[OK] CORE_CROP_CANDIDATES.csv {cc.shape}")
    cw = common_window(prices); cw.to_csv(OUT / "COMMON_TIME_WINDOW_AUDIT.csv", index=False, encoding="utf-8-sig")
    print(f"[OK] COMMON_TIME_WINDOW_AUDIT.csv {cw.shape}")
    print("\n=== 顶层核心作物候选（按跨城数） ===")
    cols = ["crop_standard", "cities_with_price", "cities_with_production", "total_rows", "priority"]
    print(cc[cols].head(25).to_string(index=False))


if __name__ == "__main__":
    main()
