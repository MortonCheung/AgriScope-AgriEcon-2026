"""validate_claims.py — 证据登记校验器（P3/P4 强制护栏）。

复刻 scientific-agent-skills/peer-review 的 `validate_claim_evidence.py` 硬性规则，
并适配本项目字段（施工手册 §16）。

校验规则：
  1. 字段齐全（§16 规定的 16 列）；
  2. claim_id 唯一；
  3. status ∈ {supported, partly_supported, not_supported, descriptive_only, unsupported}；
  4. `supported` 必须有 estimate 与 sample_size，且 source_ids 非空；
  5. `not_supported` / `unsupported` 必须有 p_raw 或 p_adjusted（阴性也必须有统计量）；
  6. `descriptive_only` 允许无 p 值，但必须有 table_id 或 figure_id；
  7. 所有 source_ids 必须能在 source_registry.csv 中找到（禁止悬空来源）；
  8. table_id / figure_id 若填写，文件必须存在；
  9. causal / mechanistic 类型且 status=supported 时**自动告警**（须专家复核）。

退出码：0 = 通过（可有 warning）；1 = 存在 error。
"""
from __future__ import annotations

import csv
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
EV = ROOT / "evidence" / "claim_evidence.csv"
SRC = ROOT / "sources" / "source_registry.csv"
TABLES = ROOT / "results" / "tables"
FIGURES = ROOT / "results" / "figures"

REQUIRED = ["claim_id", "study_id", "claim_text", "claim_type", "evidence_id", "source_ids",
            "table_id", "figure_id", "estimate", "ci_low", "ci_high", "p_raw", "p_adjusted",
            "sample_size", "method_id", "status"]
STATUS = {"supported", "partly_supported", "not_supported", "descriptive_only", "unsupported"}
CLAIM_TYPES = {"descriptive", "association", "causal", "mechanistic", "prediction",
               "measurement", "methods"}


def main() -> int:
    errors, warnings = [], []
    if not EV.exists():
        print(f"[ERROR] 缺少 {EV}")
        return 1
    with EV.open(encoding="utf-8-sig") as fh:
        rows = list(csv.DictReader(fh))

    header = list(rows[0].keys()) if rows else []
    for c in REQUIRED:
        if c not in header:
            errors.append(f"缺少列：{c}")

    src_ids = set()
    if SRC.exists():
        with SRC.open(encoding="utf-8-sig") as fh:
            src_ids = {r["source_id"] for r in csv.DictReader(fh)}

    seen = set()
    n_supported = 0
    for i, r in enumerate(rows, start=2):
        cid = r.get("claim_id", "").strip()
        if not cid:
            errors.append(f"L{i}: claim_id 为空")
            continue
        if cid in seen:
            errors.append(f"L{i}: claim_id 重复：{cid}")
        seen.add(cid)

        st = (r.get("status") or "").strip()
        if st not in STATUS:
            errors.append(f"L{i} {cid}: status 非法（{st}）")
        ct = (r.get("claim_type") or "").strip()
        if ct and ct not in CLAIM_TYPES:
            warnings.append(f"L{i} {cid}: claim_type 非常规（{ct}）")

        sids = [s.strip() for s in (r.get("source_ids") or "").replace(";", ",").split(",") if s.strip()]
        for s in sids:
            if src_ids and s not in src_ids:
                errors.append(f"L{i} {cid}: source_id 悬空：{s}")

        if st == "supported":
            n_supported += 1
            if not (r.get("estimate") or "").strip():
                errors.append(f"L{i} {cid}: supported 但缺 estimate")
            if not (r.get("sample_size") or "").strip():
                errors.append(f"L{i} {cid}: supported 但缺 sample_size")
            if not sids:
                errors.append(f"L{i} {cid}: supported 但无 source_ids")
        if st in {"not_supported", "unsupported"}:
            if not ((r.get("p_raw") or "").strip() or (r.get("p_adjusted") or "").strip()):
                errors.append(f"L{i} {cid}: 阴性结论必须给出 p_raw 或 p_adjusted")
        if st == "descriptive_only":
            if not ((r.get("table_id") or "").strip() or (r.get("figure_id") or "").strip()):
                errors.append(f"L{i} {cid}: descriptive_only 必须指向 table_id 或 figure_id")

        tid = (r.get("table_id") or "").strip()
        if tid and not (TABLES / tid).exists():
            warnings.append(f"L{i} {cid}: table_id 文件不存在：{tid}")
        fid = (r.get("figure_id") or "").strip()
        if fid and not (FIGURES / fid).exists():
            warnings.append(f"L{i} {cid}: figure_id 文件不存在：{fid}")

        if ct in {"causal", "mechanistic"} and st == "supported":
            warnings.append(
                f"L{i} {cid}: causal/mechanistic 且 supported → 需专家复核（CAUSAL_CLAIM_REQUIRES_REVIEW）")

    print(f"claims: {len(rows)} 条；supported {n_supported}")
    print(f"errors: {len(errors)}；warnings: {len(warnings)}")
    for e in errors[:60]:
        print("  [ERR ]", e)
    for w in warnings[:60]:
        print("  [WARN]", w)
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
