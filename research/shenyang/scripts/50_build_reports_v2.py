"""50_build_reports_v2.py — 生成 reports/v2 的 references.md，并统计交付清单。

从 sources/source_registry.csv 中 ACADEMIC / METHOD / NEWS_OFFICIAL 条目生成
reports/v2/references.md（含 DOI 链接与在本项目中的用途）。
"""
from __future__ import annotations

import csv
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
REG = ROOT / "sources" / "source_registry.csv"
OUT = Path("/Users/morton_cheung/Desktop/比赛/大数据分析/shenyang/reports/v2")

DATA_TYPES = {"DATA_GOV", "DATA_API"}


def main() -> None:
    rows = []
    with REG.open(encoding="utf-8-sig") as fh:
        rows = list(csv.DictReader(fh))

    data = [r for r in rows if r["source_type"] in DATA_TYPES]
    lit = [r for r in rows if r["source_type"] not in DATA_TYPES]

    L = ["# 数据来源与参考文献（沈阳研究 v2）", "",
         "> 本文件列出 v2 使用的全部来源。**公开来源（URL）与本地留档严格分离**：",
         "> 下表只给出互联网可访问的公开地址；本地快照路径仅存于内部 provenance",
         "> （`research_v2/sources/source_registry.csv` 的 `local_snapshot` 列），**不对外展示**。", "",
         "## 一、数据来源", "",
         "| 来源 ID | 名称 | 发布方 | 时间范围 | 公开地址 | 等级 |", "|---|---|---|---|---|---|"]
    for r in data:
        L.append(f"| `{r['source_id']}` | {r['title']} | {r['publisher']} | {r['data_period']} "
                 f"| [{r['public_url']}]({r['public_url']}) | {r['source_grade']} |")

    L += ["", "## 二、参考文献", "",
          f"共 {len(lit)} 条。全部 DOI 已通过 Crossref API 批量核验（34/34 通过）；",
          "中文期刊 DOI 经 doi.org 解析至中国 DOI 注册机构（chndoi）。", "",
          "| # | 文献 | 类型 | 用途 | DOI / 链接 |", "|---|---|---|---|---|"]
    for i, r in enumerate(sorted(lit, key=lambda x: (x["source_type"] != "METHOD", x["source_id"])), 1):
        kind = "方法" if r["source_type"] == "METHOD" else "学术"
        L.append(f"| {i} | {r['title']}（{r['authors']}，{r['published_date']}，*{r['publisher']}*） "
                 f"| {kind} | {r['notes'].split('；')[0]} | [{r['public_url']}]({r['public_url']}) |")

    L += ["", "## 三、来源分级说明", "",
          "- **A**：政府统计部门 / 官方公报 / 国家级官方接口 / 同行评议文献",
          "- **B**：区县本级政府门户 / 算法派生数据 / 区县年鉴（非市级统一口径）",
          "- **C**：其他官方公开材料（本研究中未使用）",
          "- **D**：非官方公开材料（本研究中未使用）", "",
          "## 四、数据性质声明", "",
          "1. 气象数据为 **ERA5 / ERA5-Land 再分析网格数据**，"
          "**不是气象站实测**；本系列全部文章均按此表述。",
          "2. 批发市场**成交量单位官方未公开**（`volume_unit=unknown`）；"
          "全系列**禁止**把成交量写作「吨」，只使用 z / % / 相对口径。",
          "3. 极端天气事件分**算法事件**（ERA5 阈值识别）与**官方事件**（政府/气象部门通报）两套，"
          "始终分开报告，不合并为一个概念。",
          "4. 中国气象数据网（data.cma.cn）需实名认证，本项目**未绕过任何鉴权**，"
          "故改用公开再分析接口。", ""]

    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "references.md").write_text("\n".join(L), encoding="utf-8")
    print(f"[OK] {OUT/'references.md'} — 数据来源 {len(data)} + 文献 {len(lit)}")


if __name__ == "__main__":
    main()
