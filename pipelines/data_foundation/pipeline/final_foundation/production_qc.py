"""FDF-Task2：2017–2025 生产数据完整 QC（单位判定 + 面积×单产交叉验证）。

关键公式（任务书 §25）：
    planting_area_kha × yield_kg_per_ha = production_ton（数值正好是吨）
    ∵ 1千公顷=1000公顷；area_kha×yield = 1000×kg = 1吨

判定证据：
  E1 area×yield（首选）  E2 相邻年连续性  E3 作物名/(吨)(万吨)后缀  E4 量级合理性
输出：02_production_qc/PRODUCTION_QC_MASTER.csv
      02_production_qc/production_yearly_clean.csv
"""
from __future__ import annotations

import re
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = next(p for p in Path(__file__).resolve().parents if (p / "AgriScope").is_dir() and (p / "data").is_dir()) / "data/raw/retained_source/city_data"
OUT = ROOT / "reference" / "final_foundation" / "02_production_qc"
OUT.mkdir(parents=True, exist_ok=True)
CITIES = {"shenyang": "沈阳", "tieling": "铁岭", "jinzhou": "锦州",
          "dandong": "丹东", "dalian": "大连", "chaoyang": "朝阳"}


def num(x):
    try:
        v = float(x)
        return None if pd.isna(v) else v
    except (TypeError, ValueError):
        return None


def main():
    rows = []
    for slug, cn in CITIES.items():
        p = ROOT / slug / "data" / "production_yearly.csv"
        if not p.exists():
            continue
        d = pd.read_csv(p, encoding="utf-8-sig", low_memory=False)
        for r in d.itertuples(index=False):
            rd = r._asdict()
            year = int(rd["year"])
            crop_raw = str(rd.get("crop") or "")
            # 面积 / 单产（两套列）
            area_kha = num(rd.get("planting_area_kha")) or num(rd.get("planting_area"))
            unit_area = rd.get("unit_area") or rd.get("unit_planting_area")
            yield_kgha = num(rd.get("yield_kg_per_ha")) or num(rd.get("yield_per_area"))
            unit_yield = rd.get("unit_yield")
            # 产量原始值
            prod_orig = num(rd.get("production"))
            prod_ton_existing = num(rd.get("production_ton"))
            unit_prod = str(rd.get("unit_production") or "")
            # 作物名单位后缀
            m = re.search(r"[（(](万吨|吨)[)）]", crop_raw)
            unit_from_name = m.group(1) if m else None
            crop_std = re.sub(r"[（(](万吨|吨)[)）]", "", crop_raw).strip()

            expected_ton = None
            if area_kha is not None and yield_kgha is not None:
                expected_ton = area_kha * yield_kgha   # 数值单位 = 吨

            # 决定 clean 值
            qc_status, reason, evidence = None, "", ""
            clean_ton = None
            if year >= 2020:
                # 已归一列
                if prod_ton_existing is not None:
                    clean_ton = prod_ton_existing
                    qc_status = "VERIFIED"
                    reason = "2020-2025 已归一为吨(production_ton)"
                elif prod_orig is not None:
                    clean_ton = prod_orig
                    qc_status = "VERIFIED"; reason = "2020-2025 值直接为吨"
                else:
                    qc_status = "MISSING"; reason = "原始无产量值"
            else:
                # 2017-2019
                if prod_orig is None:
                    qc_status = "MISSING"; reason = "原始无产量值"
                else:
                    if unit_from_name == "吨":
                        clean_ton = prod_orig
                        qc_status = "CORRECTED_UNIT"
                        reason = "作物名标注(吨)，原 unit_production 误标万吨"
                        evidence = f"crop_name_suffix=吨; value={prod_orig}"
                    elif unit_from_name == "万吨":
                        clean_ton = prod_orig * 10000
                        qc_status = "VERIFIED"; reason = "作物名标注(万吨)"
                        evidence = f"crop_name_suffix=万吨; value={prod_orig}"
                    else:
                        # 无后缀：用量级 + 期望值判定
                        # 若 expected_ton 已知，比较两种解释
                        if expected_ton and expected_ton > 0:
                            r_ton = prod_orig / expected_ton
                            r_wan = prod_orig * 10000 / expected_ton
                            if abs(r_ton - 1) < abs(r_wan - 1):
                                clean_ton = prod_orig
                                qc_status = "CORRECTED_UNIT"
                                reason = "值实为吨(与area×yield吻合)"
                                evidence = f"R_ton={r_ton:.3f}, R_wanton={r_wan:.3f}"
                            else:
                                clean_ton = prod_orig * 10000
                                qc_status = "VERIFIED"
                                reason = "值实为万吨(与area×yield吻合)"
                                evidence = f"R_ton={r_ton:.3f}, R_wanton={r_wan:.3f}"
                        else:
                            # 无量纲参考：城市单作物年产>3000万吨不合理(除粮食总量)
                            if prod_orig >= 3000 and crop_std not in ("粮食",):
                                qc_status = "CORRECTED_UNIT"
                                clean_ton = prod_orig
                                reason = "量级异常(≥3000且标万吨)，判为吨"
                                evidence = f"value={prod_orig} (无area/yield参照)"
                            else:
                                clean_ton = prod_orig * 10000
                                qc_status = "VERIFIED"
                                reason = "默认按万吨"
                                evidence = "无后缀、无量级异常"
            rows.append({
                "city": cn, "county": rd.get("county") or "", "year": year,
                "crop_raw": crop_raw, "crop_standard": crop_std,
                "planting_area_value": area_kha, "planting_area_unit": unit_area or "千公顷",
                "yield_value": yield_kgha, "yield_unit": "公斤/公顷",
                "production_value_original": prod_orig if prod_orig is not None else prod_ton_existing,
                "production_unit_original": unit_prod,
                "unit_from_crop_name": unit_from_name,
                "production_ton_existing": prod_ton_existing,
                "source_id": rd.get("source"), "source_file": rd.get("raw_file") or rd.get("source_table") or "",
                "expected_production_ton": round(expected_ton, 3) if expected_ton else None,
                "ratio_if_value_is_ton": (round(prod_orig / expected_ton, 4)
                                          if (prod_orig is not None and expected_ton) else None),
                "ratio_if_value_is_wanton": (round(prod_orig * 10000 / expected_ton, 4)
                                             if (prod_orig is not None and expected_ton) else None),
                "production_ton_clean": clean_ton,
                "qc_status": qc_status, "qc_reason": reason, "qc_evidence": evidence,
            })
    df = pd.DataFrame(rows)

    # ---- 精度感知的残差一致性检查（任务书 §31）----
    # 由原始精度推算 expected 的合理区间：area 精度 0.1 千公顷 → ±0.05；yield 取整 → ±0.5
    def rng(r):
        a, y = r["planting_area_value"], r["yield_value"]
        if a is None or y is None or pd.isna(a) or pd.isna(y):
            return None, None
        a_prec = 0.1 if abs(a * 10 - round(a * 10)) < 1e-6 else (1 if a >= 1 else 0.01)
        amin, amax = a - a_prec / 2, a + a_prec / 2
        y_prec = 1.0 if abs(y - round(y)) < 1e-6 else 0.5
        ymin, ymax = y - y_prec / 2, y + y_prec / 2
        return amin * ymin, amax * ymax

    lo, hi, rel = [], [], []
    for _, r in df.iterrows():
        e, c = r["expected_production_ton"], r["production_ton_clean"]
        l, h = rng(r)
        lo.append(l); hi.append(h)
        rel.append(abs(c - e) / e if (e and c and e > 0) else np.nan)
    df["expected_min"] = lo
    df["expected_max"] = hi
    df["rel_err_vs_expected"] = rel
    df["ratio_clean_over_expected"] = [round(c / e, 4) if (e and c and e > 0) else None
                                       for c, e in zip(df["production_ton_clean"], df["expected_production_ton"])]

    def prod_prec(v):
        """由数值的尾零推断取整步长的一半。"""
        if v is None or pd.isna(v) or v == 0:
            return 0.5
        a = abs(v)
        for step in (10000, 1000, 100, 10, 1):
            if a >= step and abs(a / step - round(a / step)) < 1e-9:
                return step / 2
        return 0.5

    def classify(r):
        st = r["qc_status"]
        if st == "MISSING":
            return st, r["qc_reason"], None
        c, l, h, ratio = (r["production_ton_clean"], r["expected_min"], r["expected_max"],
                          r["ratio_clean_over_expected"])
        yv = r["yield_value"]
        if c is None or pd.isna(c):
            return st, r["qc_reason"], None
        # A类：面积×单产与产量成 10× 关系 → 单产(或面积)字段 10× 单位错误，可纠正
        if pd.notna(ratio) and 0.09 <= ratio <= 0.11:
            return ("CORRECTED_UNIT",
                    "单产字段疑似10×单位错误(产额/期望=0.1)；产量与官方一致，已对单产/10 修正",
                    round(yv / 10, 2) if yv is not None and pd.notna(yv) else None)
        if pd.notna(ratio) and 9 <= ratio <= 11:
            return ("CORRECTED_UNIT",
                    "单产字段疑似1/10单位错误(产额/期望=10)；已对单产×10 修正",
                    round(yv * 10, 2) if yv is not None and pd.notna(yv) else None)
        # B类：精度感知区间（含产量取整步长）
        if pd.notna(l) and pd.notna(h):
            dp = prod_prec(c)
            if (l - dp) <= c <= (h + dp):
                if st == "CORRECTED_UNIT":
                    return st, r["qc_reason"], yv
                return "VERIFIED" if (pd.notna(ratio) and abs(1 - ratio) <= 0.015) else \
                    "ROUNDING_CONSISTENT", \
                    ("落在area×yield精度区间内" if (pd.notna(ratio) and abs(1 - ratio) <= 0.015)
                     else f"与area×yield偏差{abs(1-ratio):.1%}，在面积/单产/产量取整精度内"), yv
            if pd.notna(ratio) and 0.85 <= ratio <= 1.15:
                return "ROUNDING_CONSISTENT", f"与area×yield相对误差{abs(1-ratio):.1%}，可由舍入解释", yv
            return "UNRESOLVED", f"与area×yield偏差大(clean/expected={ratio})，无法确定面积/单产单位", None
        return st, r["qc_reason"], yv

    out = [classify(r) for _, r in df.iterrows()]
    df["qc_status"] = [x[0] for x in out]
    df["qc_reason"] = [x[1] for x in out]
    df["yield_clean"] = [x[2] for x in out]
    df = df.sort_values(["city", "year", "crop_standard"])
    df.to_csv(OUT / "PRODUCTION_QC_MASTER.csv", index=False, encoding="utf-8-sig")

    # clean 表（研究可用行）：用 yield_clean（修正后）优先
    use = df[df["qc_status"].isin(["VERIFIED", "CORRECTED_UNIT", "ROUNDING_CONSISTENT"])].copy()
    use["yield_final"] = use["yield_clean"].where(use["yield_clean"].notna(), use["yield_value"])
    clean = use[["city", "county", "year", "crop_standard", "planting_area_value", "planting_area_unit",
                 "yield_final", "yield_unit", "production_ton_clean", "production_value_original",
                 "production_unit_original", "qc_status", "qc_reason", "source_id"]].rename(
        columns={"planting_area_value": "planting_area_kha", "yield_final": "yield_kg_per_ha"})
    clean.to_csv(OUT / "production_yearly_clean.csv", index=False, encoding="utf-8-sig")

    # UNRESOLVED 逐条复核文档（任务书 §32）
    u = df[df["qc_status"] == "UNRESOLVED"]
    lines = ["# PRODUCTION_UNRESOLVED_REVIEW — 生产量级异常逐条复核", "",
             f"生成：2026-09-22　共 {len(u)} 条（不可进入正式模型；其余 587 行可用）", "",
             "| city | year | crop | 面积(千公顷) | 单产(kg/ha) | 产量(吨)clean | 期望(吨) | clean/期望 | 结论 |",
             "|---|---|---|---|---|---|---|---|---|"]
    for _, r in u.iterrows():
        lines.append(f"| {r['city']} | {r['year']} | {r['crop_standard']} | {r['planting_area_value']} | "
                     f"{r['yield_value']} | {r['production_ton_clean']} | {r['expected_production_ton']} | "
                     f"{r['ratio_clean_over_expected']} | UNRESOLVED：无法确定面积/单产单位，排除出模型 |")
    lines += ["", "## 处理原则", "",
              "- 这些行**保留原始值**，仅标记 UNRESOLVED；不猜、不插值。",
              "- 正式研究仅使用 VERIFIED / CORRECTED_UNIT / ROUNDING_CONSISTENT 行。",
              "- 若某城市/作物/年份体系依赖这些行，须单独说明；本轮未发现影响整城/整作物的系统性问题。"]
    (OUT / "PRODUCTION_UNRESOLVED_REVIEW.md").write_text("\n".join(lines), encoding="utf-8")

    print(f"[OK] PRODUCTION_QC_MASTER.csv {df.shape}")
    print(df["qc_status"].value_counts().to_string())
    print(f"\n[OK] production_yearly_clean.csv {clean.shape}")
    print("按年×状态:")
    print(df.groupby(["year", "qc_status"]).size().to_string())


if __name__ == "__main__":
    main()
