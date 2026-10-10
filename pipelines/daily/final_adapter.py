# -*- coding: utf-8 -*-
"""Final Model Adapter：Daily 只准备"今天发生了什么"，风险/决策由 Final Model 生产入口计算。

严格约束：
  - **不复制** Final Model 算法到 data/daily/；
  - 只通过 `decision_engine.final.inference.FinalDecisionEngine.evaluate()` 调用；
  - 不修改 models/ 任何文件；
  - Final 不可用时**不静默 fallback**：标 MODEL_UNAVAILABLE / PARTIAL；
    仅当显式 `--adapter legacy` 时才使用旧信号，并标 LEGACY_FALLBACK。

实时化方式（不重训、不动模型）：
  默认 Final 引擎读取冻结快照 `models/data/snapshots/final_v1/`。
  Adapter 在 Daily 自有目录 `data/processed/daily/final_input/extended_snapshot/`
  中生成"冻结内容 + 当日真实价格"的**输入快照**，再把 Final 各模块的 SNAPSHOT_DIR
  指向该目录 → 模型（models/models/final/*.pkl）不变，输入为最新。
  数据集由 Final 自己的 builder（`final.build.build_dataset_for`）重建。

model_status 取值：
  FINAL             Final 正常
  PARTIAL           Final 可用但有部分作物/指标缺失（capability 原样表达）
  MODEL_UNAVAILABLE Final 不可用（不做旧模型静默替换）
  LEGACY_FALLBACK   显式启用的旧信号（不得当作 Final 结果）
"""
from __future__ import annotations

import shutil
import sys
from dataclasses import dataclass, asdict, field
from pathlib import Path

import numpy as np
import pandas as pd

from . import config as C
from . import io_utils as IO

# ---------------------------------------------------------------- 状态
MS_FINAL = "FINAL"
MS_PARTIAL = "PARTIAL"
MS_UNAVAILABLE = "MODEL_UNAVAILABLE"
MS_LEGACY = "LEGACY_FALLBACK"

# 统一四级（与 Final HRI_level 语义对应）
LEVELS = ["NORMAL", "WATCH", "HIGH", "VERY_HIGH"]
_ORDER = {lv: i for i, lv in enumerate(LEVELS)}
_FINAL_LEVEL_MAP = {"low": "NORMAL", "medium": "WATCH", "high": "HIGH", "very_high": "VERY_HIGH"}
_MR_LEVEL_RULE = "daily_past_only_percentile(P50/P75/P90)，切点与 Final HRI_level 一致"

DAILY_HORIZON = 30        # Daily 市场脉搏使用 30d（Final 中为 model horizon，非 scenario_only）

# Final 输出中表示"该作物不可评估"的状态
_UNAVAILABLE_STATUS = {"INSUFFICIENT_MARKET_DATA", "MODEL_ERROR", "NO_FEASIBLE_PLAN"}


def worse(a: str, b: str) -> str:
    c = [x for x in (a, b) if x in LEVELS]
    return max(c, key=lambda x: _ORDER[x]) if c else "UNKNOWN"


def _pct_level(pct: float | None) -> str:
    if pct is None or (isinstance(pct, float) and np.isnan(pct)):
        return "UNKNOWN"
    if pct >= 90:
        return "VERY_HIGH"
    if pct >= 75:
        return "HIGH"
    if pct >= 50:
        return "WATCH"
    return "NORMAL"


def _overall_status(n_ok: int, n_total: int, artifacts_ready: bool) -> str:
    """聚合 model_status（§10/§11）：部分可用绝不报 FINAL。"""
    if n_ok == 0 or n_ok < n_total:
        return MS_PARTIAL
    if not artifacts_ready:
        return MS_PARTIAL      # ML 点预测缺失 → 不假装完全可用
    return MS_FINAL


@dataclass
class CropAssessment:
    crop: str
    model_status: str = MS_UNAVAILABLE
    final_status: str | None = None
    hri: dict | None = None
    market_risk: dict | None = None
    price: dict | None = None
    confidence: dict | None = None
    climate_exposure: dict | None = None
    capability: dict | None = None
    final_warnings: list = field(default_factory=list)
    daily_signal: str = "UNKNOWN"
    signal_basis: dict | None = None
    notes: list = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self)


# ---------------------------------------------------------------- decision_engine 装载
def _ensure_decision_engine():
    """把 models/src 加入 sys.path，并把 decision_engine.common 的 ROOT 校正到项目根。

    这样服务器上（不同目录）也能运行，且**不修改 models/ 任何文件**。
    """
    if str(C.MODEL_SRC) not in sys.path:
        sys.path.insert(0, str(C.MODEL_SRC))
    import decision_engine.common as cm  # noqa: PLC0415
    if str(cm.ROOT) != str(C.ROOT):
        cm.ROOT = C.ROOT
        cm.DE = C.MODELS_DIR
    return cm


def _live_wholesale_rows() -> pd.DataFrame:
    """Daily 表的 wholesale 可入模行（QC_OK）。"""
    df = pd.read_parquet(C.PROCESSED_DAILY_DIR / "daily_market_price.parquet")
    df = df[(df["price_level"] == C.MODEL_PRICE_LEVEL) &
            (df["quality_status"] == C.QC_OK)].copy()
    df["date"] = pd.to_datetime(df["date"])
    df["price_per_kg"] = pd.to_numeric(df["price_per_kg"], errors="coerce")
    df = df.dropna(subset=["price_per_kg"])
    g = (df.groupby(["date", "crop_standard"])
         .agg(price_per_kg=("price_per_kg", "median"), source_name=("source_name", "first"))
         .reset_index())
    return g.sort_values(["crop_standard", "date"])


def final_readiness() -> dict:
    """Final Model 生产前置检查（§6/§10/§11）。

    建模 Agent 可能正在重新冻结（reports/final/tables、models/final/*.pkl 会被清空重建）。
    分两级判定，避免"部分可用"被当成完全可用：
      - ready          ：HRI / Market Risk / 价格情景 可计算（选型表 + 快照 + 数据集齐备）
      - artifacts_ready：ML 点预测产物（.pkl）就绪
    缺失时**不静默换旧模型**，只降级并明确标注。
    """
    required = {
        "run_meta": C.FINAL_RUN_META,
        "output_schema": C.FINAL_OUTPUT_SCHEMA,
        "price_model_selection": C.FINAL_REPORTS_DIR / "tables" / "price_model_selection.csv",
        "shenyang_dataset": C.FINAL_SNAPSHOT_DIR / "datasets" / "decision_dataset_沈阳.parquet",
        "shenyang_market_daily": C.FINAL_SNAPSHOT_DIR / "model_ready/shenyang_core/market_daily.parquet",
    }
    missing = [k for k, p in required.items() if not Path(p).exists()]
    has_artifacts = C.FINAL_MODELS_DIR.exists() and any(C.FINAL_MODELS_DIR.glob("沈阳_*.pkl"))
    ready = not missing
    note = ""
    if missing:
        note = ("Final 产物不完整（可能正在重新冻结）→ MODEL_UNAVAILABLE，不静默替换旧模型")
    elif not has_artifacts:
        note = ("Final ML 点预测产物（models/final/*.pkl）尚未就绪 → 价格情景回退为历史分位，"
                "model_status 降级为 PARTIAL（HRI/Market Risk 仍可用）")
    return {"ready": ready, "missing": missing,
            "has_model_artifacts": bool(has_artifacts),
            "artifacts_ready": bool(has_artifacts), "note": note}


class FinalModelAdapter:
    """通过 Final Model 生产入口计算风险与决策（实时输入）。"""

    name = "final"

    def __init__(self, city: str = C.PRIMARY_CITY):
        self.city = city
        _ensure_decision_engine()
        from decision_engine.final import fcommon, build, risk, inference, artifacts  # noqa: PLC0415
        from decision_engine.final import capabilities as CAP  # noqa: PLC0415
        self._fcommon, self._build, self._risk = fcommon, build, risk
        self._inference, self._artifacts, self._cap = inference, artifacts, CAP
        self.ext_root = C.FINAL_INPUT_DIR / "extended_snapshot"
        self._prepared = False

    # ------------------------------------------------ 输入快照
    def _patch_snapshot_dir(self) -> None:
        for mod in (self._fcommon, self._build, self._risk, self._inference,
                    self._artifacts, self._cap):
            if hasattr(mod, "SNAPSHOT_DIR"):
                mod.SNAPSHOT_DIR = self.ext_root

    def _reset_caches(self) -> None:
        d = self._inference._Data
        d._ds, d._hri, d._mr = {}, {}, {}
        d._clim = d._ct = d._sel = d._rng = None

    def _ensure_ext_skeleton(self) -> None:
        """复制 Final 冻结快照中被推理读取的**静态**文件（缺失才复制，保持冻结）。

        复制整个 `model_ready/` 树（体积小，约 3.6MB）以避免遗漏
        （market_daily / climate / profit / cost_reference / phenology 等都会被读到），
        另加朝阳数据集；沈阳数据集由 Daily 用 Final 自己的 builder 重建。
        动态文件（沈阳 market_daily、沈阳 dataset）在 prepare_inputs 中覆盖写入。
        """
        src = C.FINAL_SNAPSHOT_DIR
        static_rels = []
        mr = src / "model_ready"
        if mr.exists():
            static_rels += [f"model_ready/{p.relative_to(mr).as_posix()}"
                            for p in mr.rglob("*") if p.is_file()]
        for rel in ["datasets/decision_dataset_朝阳.parquet",
                    "datasets/decision_dataset_沈阳.parquet"]:
            if (src / rel).exists():
                static_rels.append(rel)
        for rel in static_rels:
            dst = self.ext_root / rel
            if dst.exists():
                continue
            s = src / rel
            if s.exists():
                dst.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(s, dst)

    def _build_extended_market_daily(self) -> pd.DataFrame:
        """冻结 market_daily + 当日真实价格 → 扩展价格序列（模型口径 wholesale）。"""
        frozen_p = C.FINAL_SNAPSHOT_DIR / "model_ready/shenyang_core/market_daily.parquet"
        frozen = pd.read_parquet(frozen_p)
        frozen["_dt"] = pd.to_datetime(frozen["observation_date"])
        fmax = frozen["_dt"].max()

        live = _live_wholesale_rows()
        new = live[live["date"] > fmax]
        cols = list(frozen.columns)
        add = pd.DataFrame(index=range(len(new)), columns=cols)
        for c in cols:
            add[c] = pd.Series([None] * len(new), dtype="object")
        if len(new):
            add["city"] = self.city
            add["observation_date"] = new["date"].values
            add["crop_standard"] = new["crop_standard"].values
            add["price_per_kg"] = new["price_per_kg"].astype(str).values
            add["price_level_canonical"] = C.MODEL_PRICE_LEVEL
            add["price_level"] = C.MODEL_PRICE_LEVEL
            add["market_name"] = "沈阳菜篮子信息发布平台（批发口径）"
            add["source_name"] = new["source_name"].values
            add["unit_original"] = "元/斤"
            add["frequency"] = "daily"
        ext = pd.concat([frozen.drop(columns=["_dt"]), add], ignore_index=True)
        ext["observation_date"] = pd.to_datetime(ext["observation_date"])
        ext = ext.sort_values(["crop_standard", "observation_date"]).reset_index(drop=True)
        return ext

    def prepare_inputs(self) -> dict:
        """生成 Daily 自有的 Final 输入快照（幂等、原子写）。"""
        self.ext_root.mkdir(parents=True, exist_ok=True)
        self._sync_source_fingerprint()
        self._ensure_ext_skeleton()
        self._patch_snapshot_dir()

        ext = self._build_extended_market_daily()
        md_path = self.ext_root / "model_ready/shenyang_core/market_daily.parquet"
        IO.atomic_write_parquet(ext, md_path)

        # 用 Final 自己的 builder 重建沈阳决策数据集（含 point-in-time 特征与目标）
        ds = self._build.build_dataset_for(self.city)
        IO.atomic_write_parquet(ds, self.ext_root / "datasets" / f"decision_dataset_{self.city}.parquet")

        self._reset_caches()
        self._prepared = True
        # 全部静态副本就绪后才落指纹，避免半成品被当成有效输入
        IO.atomic_write_json(self.ext_root / ".source_fingerprint.json", self._fingerprint())
        return {
            "extended_snapshot": str(self.ext_root.relative_to(C.ROOT)),
            "market_daily_rows": int(len(ext)),
            "market_daily_max_date": str(pd.to_datetime(ext["observation_date"]).max().date()),
            "dataset_rows": int(len(ds)),
            "source_final": self._fingerprint(),
        }

    @staticmethod
    def _fingerprint() -> dict:
        cur = C.final_versions()
        return {"final_generated_at": cur.get("final_generated_at"),
                "code_fingerprint": cur.get("code_fingerprint"),
                "model_version": cur.get("model_version")}

    def _sync_source_fingerprint(self) -> None:
        """Final 重新冻结时，Daily 的输入快照必须重建（否则会用到过期副本）。"""
        marker = self.ext_root / ".source_fingerprint.json"
        have = IO.read_json_safe(marker, None)
        if have is not None and have == self._fingerprint():
            return
        if self.ext_root.exists():
            shutil.rmtree(self.ext_root)
        self.ext_root.mkdir(parents=True, exist_ok=True)

    # ------------------------------------------------ 推理
    def compute(self, as_of: str | None = None) -> tuple[dict[str, CropAssessment], dict]:
        ready = final_readiness()
        if not ready["ready"]:
            crops = C.supported_crops(self.city)
            ver = C.final_versions()
            return {}, {
                "adapter": self.name, "model_status": MS_UNAVAILABLE,
                "model_version": ver["model_version"], "data_version": ver["data_version"],
                "entry": "decision_engine.final.inference.FinalDecisionEngine.evaluate",
                "crops": crops, "n_crops_evaluated": 0, "n_crops_total": len(crops),
                "readiness": ready, "fallback_used": False,
                "error": f"Final 产物缺失: {ready['missing']}",
                "note": "Final 不可用 → 不静默替换旧模型；仍输出真实价格/变化/freshness。",
            }
        prep = self.prepare_inputs()
        crops = C.supported_crops(self.city)
        eng = self._inference.FinalDecisionEngine()
        ver = C.final_versions()

        # market risk 历史序列（用于 past-only 分位分级，值本身来自 Final）
        mr_hist = self._inference._Data.mr(self.city)

        out: dict[str, CropAssessment] = {}
        n_ok = 0
        for crop in crops:
            req = {"city": self.city, "crop": crop, "horizon_days": DAILY_HORIZON}
            if as_of:
                req["as_of"] = as_of
            try:
                r = eng.evaluate(req)
            except Exception as exc:  # noqa: BLE001
                out[crop] = CropAssessment(
                    crop=crop, model_status=MS_PARTIAL, final_status="MODEL_ERROR",
                    notes=[f"final_eval_error:{type(exc).__name__}: {exc}"])
                continue

            st = r.get("status")
            hri = r.get("hri") or {}
            mr = r.get("market_risk") or {}
            price = r.get("price")
            ca = CropAssessment(
                crop=crop,
                model_status=MS_FINAL,
                final_status=st,
                hri=hri or None,
                market_risk=mr or None,
                price=price,
                confidence=r.get("confidence"),
                climate_exposure=r.get("climate_exposure"),
                capability=r.get("capability"),
                final_warnings=list(r.get("warnings") or []),
            )

            if st in _UNAVAILABLE_STATUS or price is None:
                ca.model_status = MS_PARTIAL
                ca.daily_signal = "UNKNOWN"
                ca.notes.append(f"Final capability 原样表达：status={st}")
                out[crop] = ca
                continue

            # HRI 等级：直接取 Final 输出
            hri_level = _FINAL_LEVEL_MAP.get(str(hri.get("level")), "UNKNOWN")
            # Market Risk 等级：值来自 Final，等级由 Daily 用 past-only 分位分级（已标注规则）
            mr_level = "UNKNOWN"
            mr_pct = None
            if not mr_hist.empty:
                s = mr_hist[(mr_hist["crop"] == crop)]
                if len(s):
                    series = s.sort_values("date")["market_risk"]
                    mr_pct = float(series.expanding(min_periods=60).rank(pct=True).iloc[-1] * 100) \
                        if len(series) >= 60 else None
                    mr_level = _pct_level(mr_pct)
            if ca.market_risk is not None:
                ca.market_risk = {**ca.market_risk, "level": mr_level,
                                  "level_pct": mr_pct, "level_rule": _MR_LEVEL_RULE}
            ca.daily_signal = worse(hri_level, mr_level)
            ca.signal_basis = {"hri_level": hri_level, "market_risk_level": mr_level,
                               "rule": "取两者更高；HRI 等级来自 Final，"
                                       "Market Risk 等级为 Daily past-only 分位映射"}
            n_ok += 1
            out[crop] = ca

        overall = _overall_status(n_ok, len(crops), ready.get("artifacts_ready", True))

        meta = {
            "adapter": self.name,
            "model_status": overall,
            "model_version": ver["model_version"],
            "data_version": ver["data_version"],
            "final_code_fingerprint": ver["code_fingerprint"],
            "final_generated_at": ver["final_generated_at"],
            "entry": "decision_engine.final.inference.FinalDecisionEngine.evaluate",
            "horizon_days": DAILY_HORIZON,
            "as_of": as_of,
            "n_crops_evaluated": n_ok,
            "n_crops_total": len(crops),
            "crops": crops,
            "input_snapshot": prep,
            "market_risk_level_rule": _MR_LEVEL_RULE,
            "readiness": ready,
            "degradation": None if ready.get("artifacts_ready", True)
            else "ML 点预测产物缺失：价格情景为历史分位（scenario_quantile），非模型预测",
            "fallback_used": False,
        }
        return out, meta


# ---------------------------------------------------------------- Legacy（仅显式启用）
class LegacyAdapter:
    """旧每日信号（hri_v1 / market_risk_v1）。仅在显式 --adapter legacy 时使用。"""

    name = "legacy"

    def __init__(self, city: str = C.PRIMARY_CITY):
        self.city = city

    def compute(self, as_of: str | None = None) -> tuple[dict[str, CropAssessment], dict]:
        _ensure_decision_engine()
        from decision_engine.monitoring.daily_signal import daily_signal  # noqa: PLC0415
        crops = C.supported_crops(self.city)
        out: dict[str, CropAssessment] = {}
        for crop in crops:
            try:
                r = daily_signal(self.city, crop, as_of_date=as_of)
            except Exception as exc:  # noqa: BLE001
                out[crop] = CropAssessment(crop=crop, model_status=MS_LEGACY,
                                           notes=[f"legacy_error:{type(exc).__name__}"])
                continue
            if r.get("status") != "ok":
                out[crop] = CropAssessment(crop=crop, model_status=MS_LEGACY,
                                           notes=[f"legacy_status:{r.get('status')}"])
                continue
            out[crop] = CropAssessment(
                crop=crop, model_status=MS_LEGACY, final_status="LEGACY",
                hri={"value": r.get("HRI"), "level": r.get("HRI_level"), "available": True},
                market_risk={"value": r.get("market_risk"),
                             "level": r.get("market_risk_level"), "available": True},
                price=None,
                daily_signal=r.get("warning_level", "UNKNOWN"),
                notes=["LEGACY_FALLBACK：旧信号库，非 Final 结果，不得当作 Final。"],
            )
        meta = {"adapter": self.name, "model_status": MS_LEGACY,
                "model_version": "legacy", "data_version": "legacy",
                "entry": "decision_engine.monitoring.daily_signal.daily_signal",
                "crops": crops, "fallback_used": True,
                "warning": "LEGACY_FALLBACK 结果不得作为 Final 对外呈现"}
        return out, meta


# ---------------------------------------------------------------- 入口
def compute_assessments(city: str = C.PRIMARY_CITY, as_of: str | None = None,
                        adapter: str = "final") -> tuple[dict[str, CropAssessment], dict]:
    """返回 (crop -> CropAssessment, meta)。

    adapter='final'（默认）：Final 生产入口；失败 → MODEL_UNAVAILABLE，**不静默换旧模型**。
    adapter='legacy'        ：显式旧信号，标 LEGACY_FALLBACK。
    """
    if adapter == "legacy":
        return LegacyAdapter(city).compute(as_of=as_of)
    try:
        return FinalModelAdapter(city).compute(as_of=as_of)
    except Exception as exc:  # noqa: BLE001
        return {}, {
            "adapter": "final",
            "model_status": MS_UNAVAILABLE,
            "model_version": C.final_versions()["model_version"],
            "data_version": C.final_versions()["data_version"],
            "entry": "decision_engine.final.inference.FinalDecisionEngine.evaluate",
            "crops": C.supported_crops(city),
            "error": f"{type(exc).__name__}: {exc}",
            "fallback_used": False,
            "note": "Final 不可用 → 不静默替换旧模型；快照标 PARTIAL/MODEL_UNAVAILABLE，"
                    "仍输出真实价格/变化/freshness。",
        }