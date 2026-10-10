# -*- coding: utf-8 -*-
"""把根 data/、models/ 的正式资产发布到 AgriScope/runtime/。

设计原则（见项目架构规范「标准数据流」）：
  研发态：根 data/ + models/ 是唯一完整仓库；
  发布态：由本脚本挑选「产品运行真正需要的最小集合」写入 AgriScope/runtime/，
          使 AgriScope 可脱离外层开发仓独立运行。
本脚本只复制、不删除源；幂等，可反复执行。
包含：runtime/models（模型+推理库+配置+快照）、runtime/data（Daily/长期/治理元数据）。
研究资产**不再由本脚本整包复制**：runtime/research 的「产品件」由
`publish_research.py` 从根 data/research 按选择发布（product/ + research_catalog.json），
本脚本只在 manifest 中如实登记该发布项，不落地研究原始副本。

用法：
    python3 AgriScope/pipelines/publishing/publish_runtime.py
    # 研究产品件请先（或随后）运行 publish_research.py；二者互不覆盖。
"""
from __future__ import annotations

import json
import os
import shutil
from datetime import datetime, timezone
from pathlib import Path


def project_root() -> Path:
    """向上查找同时含 AgriScope/、data/、models/ 的 monorepo 根。"""
    env = os.environ.get("PROJECT_ROOT")
    if env:
        return Path(env).resolve()
    for p in Path(__file__).resolve().parents:
        if (p / "AgriScope").is_dir() and (p / "data").is_dir() and (p / "models").is_dir():
            return p
    raise RuntimeError("无法定位 monorepo 根目录")


ROOT = project_root()
AGRISCOPE = ROOT / "AgriScope"
RUNTIME = AGRISCOPE / "runtime"
PIPELINES = AGRISCOPE / "pipelines"

# (源, 目标, 说明) —— 源不存在则跳过并记录
MANIFEST_ITEMS = [
    (PIPELINES / "modeling" / "src",              RUNTIME / "models" / "src",                 "decision_engine 推理库源码"),
    (PIPELINES / "modeling" / "config",           RUNTIME / "models" / "config",              "模型配置 yaml"),
    (ROOT / "models" / "short_term" / "final",    RUNTIME / "models" / "models" / "final",    "短期冻结模型 pkl"),
    (ROOT / "data" / "model_ready" / "snapshots" / "final_v1",
                                                  RUNTIME / "models" / "data" / "snapshots" / "final_v1", "冻结算法的输入快照"),
    # 模型层（pipelines/modeling）训练/评估与测试所需的开发期输入快照
    (ROOT / "data" / "model_ready" / "snapshots" / "v1",
                                                  RUNTIME / "models" / "data" / "snapshots" / "v1", "开发期城市数据快照 v1"),
    (ROOT / "data" / "model_ready" / "snapshots" / "v2",
                                                  RUNTIME / "models" / "data" / "snapshots" / "v2", "开发期城市数据快照 v2"),
    (ROOT / "data" / "processed" / "decision_dataset",
                                                  RUNTIME / "models" / "data" / "processed", "决策数据集（模型层输入）"),
    (ROOT / "data" / "model_ready" / "features",
                                                  RUNTIME / "models" / "data" / "features",  "模型特征（模型层输入）"),
    (ROOT / "data" / "metadata" / "model_manifests" / "final",
                                                  RUNTIME / "models" / "data" / "manifests" / "final", "模型输入清单"),
    (ROOT / "models" / "reports" / "final",       RUNTIME / "models" / "reports" / "final",   "冻结模型身份报告"),
    (ROOT / "models" / "registry",                RUNTIME / "models" / "models" / "registry",  "模型注册表（decision_engine 契约路径 DE/models/registry）"),
    (ROOT / "data" / "model_ready",               RUNTIME / "data" / "model_ready",           "model_ready 运行时子集"),
    (ROOT / "data" / "metadata",                  RUNTIME / "data" / "metadata",              "治理元数据（含 governance）"),
    (ROOT / "data" / "processed" / "daily",       RUNTIME / "data" / "processed" / "daily",   "Daily 冻结产物"),
    (ROOT / "data" / "processed" / "long_horizon",
                                                  RUNTIME / "data" / "processed" / "long_horizon", "长期预测只读快照"),
    (ROOT / "models" / "registry" / "LONG_HORIZON_V2_REGISTRY.csv",
                                                  RUNTIME / "LONG_HORIZON_V2_REGISTRY.csv",   "长期模型注册表"),
    # LLM 回溯评估证据：`/api/research/llm-evaluation` 只读这三份文件。
    # 它们原本只落在仓内 `llm/artifacts/v2`（gitignored），脱离外层目录后端点会 503，
    # 因此必须作为正式发布资产进入 runtime（§5.1/§6.4）。只发布 API 真正读取的三份，不搬缓存与逐调用记录。
    (AGRISCOPE / "llm" / "artifacts" / "v2" / "real_evaluation_status.json",
                                                  RUNTIME / "llm" / "artifacts" / "v2" / "real_evaluation_status.json",
                                                  "LLM 回溯评估状态（机器可读）"),
    (AGRISCOPE / "llm" / "artifacts" / "v2" / "outcome_labels.json",
                                                  RUNTIME / "llm" / "artifacts" / "v2" / "outcome_labels.json",
                                                  "LLM / Hybrid 结论标签"),
    (AGRISCOPE / "llm" / "artifacts" / "v2" / "fair_comparison.csv",
                                                  RUNTIME / "llm" / "artifacts" / "v2" / "fair_comparison.csv",
                                                  "公平对比表（逐组 WAPE 与增益）"),
]

# 研究资产：由 publish_research.py 从 data/research 按选择发布，本脚本不做整包复制。
RESEARCH_SOURCE = ROOT / "data" / "research"          # 研究完整源（只读）
RESEARCH_DEST = RUNTIME / "research"                  # 只放产品件：product/ + research_catalog.json
RESEARCH_PRODUCT = RESEARCH_DEST / "product"
RESEARCH_CATALOG = RESEARCH_DEST / "research_catalog.json"

# 运行时空目录（fcommon.ensure_final_dirs 要求存在）
EMPTY_DIRS = [RUNTIME / "models" / "evaluation" / "final"]


def copy_item(src: Path, dst: Path) -> str:
    if not src.exists():
        return "SKIP(missing-src)"
    if dst.exists():
        if dst.is_dir():
            shutil.rmtree(dst)
        else:
            dst.unlink()
    dst.parent.mkdir(parents=True, exist_ok=True)
    if src.is_dir():
        shutil.copytree(src, dst)
    else:
        shutil.copy2(src, dst)
    return "OK"


def main() -> int:
    records = []
    print(f"[publish] ROOT    = {ROOT}")
    print(f"[publish] RUNTIME = {RUNTIME}")
    for src, dst, desc in MANIFEST_ITEMS:
        status = copy_item(src, dst)
        records.append({
            "source": str(src.relative_to(ROOT)) if src.exists() else str(src),
            "destination": str(dst.relative_to(AGRISCOPE)),
            "description": desc,
            "status": status,
        })
        print(f"  [{status}] {dst.relative_to(AGRISCOPE)}  <-  {src.relative_to(ROOT) if src.exists() else src}")

    for d in EMPTY_DIRS:
        d.mkdir(parents=True, exist_ok=True)

    # 研究发布项：如实登记（来源=data/research；目标=runtime 内「产品件」子集），
    # 由 publish_research.py 落地，本脚本不复制；不得记录任何已不存在的路径。
    research_ready = RESEARCH_PRODUCT.is_dir() and RESEARCH_CATALOG.is_file()
    research_record = {
        "source": str(RESEARCH_SOURCE.relative_to(ROOT)),
        "destination": str(RESEARCH_DEST.relative_to(AGRISCOPE)),
        "description": ("六城与跨城市研究产品载荷（product/ + research_catalog.json，"
                        "由 publish_research.py 从 data/research 按选择发布）"),
        "asset_type": "research_product",
        "status": "PUBLISHED(research-product)" if research_ready else "SKIP(missing-research-product)",
    }
    records.append(research_record)
    print(f"  [{research_record['status']}] {research_record['destination']}  <-  "
          f"{research_record['source']}  (publish_research.py)")

    manifest = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "publisher": "AgriScope/pipelines/publishing/publish_runtime.py",
        "note": "运行资产快照；由 publishing 从根 data/models 生成，产品只读 runtime/。",
        "assets": records,
    }
    (RUNTIME / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(f"[publish] manifest written: {len(records)} assets")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
