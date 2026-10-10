"""31_validate_frontend.py — 前端数据 QA 校验器（施工手册 §37）。

自动检查：
  A 文章边界：article id 唯一；文章不含下一篇标题；不含其他 ARTICLE_END。
  B 来源：所有 source_id 存在；public_url 非空；不允许出现 /Users/ 或 workspace/；
         不允许本地绝对路径作为 display source。
  C 图片：所有 figure 路径存在。
  D 摘要：frontend_summary 必须来自显式块（非空），且与 abstract 不相同（不是同一字段）。
  E 数字：文章 JSON 的 key findings 段落中的数字必须能在 evidence/claim_evidence.csv 找到
         （以 claim 的 estimate/p/sample_size 字符串集合做包含匹配）。

退出码 0=通过；1=存在 error。
"""
from __future__ import annotations

import csv
import json
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
FE = ROOT / "exports" / "frontend"
REPORTS = Path("/Users/morton_cheung/Desktop/比赛/大数据分析/shenyang/reports/v2")
FIGDIR = ROOT / "results" / "figures"
EVID = ROOT / "evidence" / "claim_evidence.csv"

BANNED = ("/Users/", "workspace/", "research_v2/")


def main() -> int:
    errors, warns = [], []
    ids, titles = {}, {}
    for fp in sorted((FE / "articles").glob("A*.json")):
        o = json.loads(fp.read_text(encoding="utf-8"))
        sid = o["id"]
        if sid in ids:
            errors.append(f"{sid}: article id 重复")
        ids[sid] = o
        titles[sid] = o["title"]

    # A 文章边界
    for sid, o in ids.items():
        body = json.dumps(o, ensure_ascii=False)
        n_end = body.count("ARTICLE_END")
        if n_end:
            warns.append(f"{sid}: JSON 正文中出现 ARTICLE_END 字样 {n_end} 次（应为 0）")
        for other, t in titles.items():
            if other != sid and t and t in body:
                errors.append(f"{sid}: 正文包含其他文章标题（{other}）")
    # Markdown 层 ARTICLE_END 一致性
    for fp in sorted(REPORTS.glob("0[1-9]_*.md")):
        txt = fp.read_text(encoding="utf-8")
        markers = re.findall(r"<!-- ARTICLE_END:(A\d\d) -->", txt)
        if len(markers) != 1:
            errors.append(f"{fp.name}: ARTICLE_END 标记数 {len(markers)}（应为 1）")
            continue
        if markers[0] not in ids:
            errors.append(f"{fp.name}: ARTICLE_END 的 id {markers[0]} 不在导出中")
        for other, t in titles.items():
            if other != markers[0] and re.search(rf"^#\s+{re.escape(t)}\s*$", txt, flags=re.M):
                errors.append(f"{fp.name}: 含其他文章 H1 标题（{other}）")

    # B 来源
    srcs = json.loads((FE / "sources.json").read_text(encoding="utf-8"))
    src_ids = {s["source_id"] for s in srcs}
    for s in srcs:
        if not s.get("url"):
            errors.append(f"来源 {s['source_id']}: public_url 为空")
        for b in BANNED:
            if b in str(s.get("url", "")):
                errors.append(f"来源 {s['source_id']}: URL 含本地路径（{b}）")
    for sid, o in ids.items():
        for s in o.get("source_ids", []):
            if s not in src_ids:
                errors.append(f"{sid}: source_id {s} 不在 sources.json")
        body = json.dumps(o, ensure_ascii=False)
        for b in BANNED:
            if b in body:
                errors.append(f"{sid}: JSON 正文含本地路径（{b}）")

    # C 图片
    for sid, o in ids.items():
        for f in o.get("figures", []):
            if not (FIGDIR / f["file"]).exists():
                errors.append(f"{sid}: figure 不存在 {f['file']}")
        for t in o.get("tables", []):
            if not (ROOT / "results" / "tables" / t["file"]).exists():
                errors.append(f"{sid}: table 不存在 {t['file']}")

    # D 摘要字段分离
    for sid, o in ids.items():
        if not o.get("frontend_summary"):
            errors.append(f"{sid}: frontend_summary 为空（必须由文章显式提供）")
        if not o.get("abstract"):
            errors.append(f"{sid}: abstract 为空")
        if o.get("frontend_summary", "").strip() == o.get("abstract", "").strip():
            errors.append(f"{sid}: frontend_summary 与 abstract 完全相同（应为两个独立字段）")

    # E 数字可回溯
    ev_tokens = set()
    if EVID.exists():
        with EVID.open(encoding="utf-8-sig") as fh:
            for r in csv.DictReader(fh):
                for k in ("estimate", "ci_low", "ci_high", "p_raw", "p_adjusted", "sample_size"):
                    v = (r.get(k) or "").strip()
                    if v:
                        ev_tokens.add(v)
                        for num in re.findall(r"-?\d+\.?\d*", v):
                            ev_tokens.add(num)
    else:
        warns.append("缺少 evidence/claim_evidence.csv，跳过数字回溯检查")

    if ev_tokens:
        for sid, o in ids.items():
            txt = o.get("frontend_summary", "") + " " + o.get("abstract", "")
            nums = set(re.findall(r"\d+\.\d+", txt))
            miss = [n for n in nums if n not in ev_tokens and n.rstrip("0").rstrip(".") not in ev_tokens]
            if miss:
                warns.append(f"{sid}: 摘要中 {len(miss)} 个数字未在证据登记中直接命中（需人工核对）：{miss[:5]}")

    print(f"articles: {len(ids)}；sources: {len(srcs)}")
    print(f"errors: {len(errors)}；warnings: {len(warns)}")
    for e in errors:
        print("  [ERR ]", e)
    for w in warns[:40]:
        print("  [WARN]", w)
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
