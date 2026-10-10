"""沈阳农业气象风险研究 — 共享基础模块。

职责：
  1. 集中解析 config/paths.yaml，禁止业务代码出现绝对路径字面量；
  2. 统一日志、随机种子、目录创建；
  3. 统一输入表读取（带缓存与类型约定）；
  4. 统一图/表输出（图必须自带可独立阅读的标题、单位、来源层级）；
  5. 统一结果登记（results_registry.csv）与异常记录（BLOCKERS.md）。

本模块不包含任何研究逻辑。
"""
from __future__ import annotations

import hashlib
import json
import logging
import os
import platform
import sys
import time
import traceback
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

import numpy as np
import pandas as pd
import yaml

# -----------------------------------------------------------------------------
# 路径解析
# -----------------------------------------------------------------------------
PROJECT_ROOT = Path(__file__).resolve().parents[1]
CONFIG_DIR = PROJECT_ROOT / "config"


def _read_yaml(path: Path) -> Dict[str, Any]:
    with path.open("r", encoding="utf-8") as f:
        return yaml.safe_load(f)


class Paths:
    """路径注册表：把 paths.yaml 中的相对路径解析为绝对路径。"""

    def __init__(self) -> None:
        self.cfg = _read_yaml(CONFIG_DIR / "paths.yaml")
        wh = self.cfg["warehouse"]
        self.warehouse_root = Path(wh["root"])
        self.w_root = self.warehouse_root
        for k in ("metadata", "raw", "staging", "curated", "marts", "reports"):
            setattr(self, f"w_{k}", self.warehouse_root / wh[k])
        self.inputs: Dict[str, Path] = {
            k: self.warehouse_root / v for k, v in self.cfg["inputs"].items()
        }
        self.project: Dict[str, Path] = {
            k: PROJECT_ROOT / v for k, v in self.cfg["project"].items()
        }
        self.artifacts: Dict[str, Path] = {
            k: PROJECT_ROOT / v for k, v in self.cfg["artifacts"].items()
        }

    # -- 便捷访问 -------------------------------------------------------------
    def inp(self, name: str) -> Path:
        if name not in self.inputs:
            raise KeyError(f"未在 config/paths.yaml inputs 中登记输入表: {name}")
        p = self.inputs[name]
        if not p.exists():
            raise FileNotFoundError(f"输入表不存在: {p}")
        return p

    def out(self, key: str) -> Path:
        """项目内输出路径（自动建父目录）。"""
        if key in self.artifacts:
            p = self.artifacts[key]
        elif key in self.project:
            p = self.project[key]
        else:
            p = PROJECT_ROOT / key
        p.parent.mkdir(parents=True, exist_ok=True)
        return p

    def dir(self, key: str) -> Path:
        p = self.project[key]
        p.mkdir(parents=True, exist_ok=True)
        return p

    def figure(self, name: str) -> Path:
        p = self.dir("figures") / name
        p.parent.mkdir(parents=True, exist_ok=True)
        return p

    def table(self, name: str) -> Path:
        p = self.dir("tables") / name
        p.parent.mkdir(parents=True, exist_ok=True)
        return p

    def metric(self, name: str) -> Path:
        p = self.dir("metrics") / name
        p.parent.mkdir(parents=True, exist_ok=True)
        return p

    def report(self, name: str) -> Path:
        p = self.dir("reports") / name
        p.parent.mkdir(parents=True, exist_ok=True)
        return p


PATHS = Paths()
ANALYSIS: Dict[str, Any] = _read_yaml(CONFIG_DIR / "analysis.yaml")
CROPS_CFG: Dict[str, Any] = _read_yaml(CONFIG_DIR / "crops.yaml")
EVENTS_CFG: Dict[str, Any] = _read_yaml(CONFIG_DIR / "events.yaml")


def set_seed() -> int:
    seed = int(ANALYSIS["project"]["random_seed"])
    np.random.seed(seed)
    os.environ["PYTHONHASHSEED"] = str(seed)
    return seed


# -----------------------------------------------------------------------------
# 日志
# -----------------------------------------------------------------------------
_LOG_INITIALIZED = False


def get_logger(module: str) -> logging.Logger:
    global _LOG_INITIALIZED
    if not _LOG_INITIALIZED:
        log_dir = PATHS.dir("logs")
        fmt = logging.Formatter(
            "%(asctime)s | %(levelname)-7s | %(name)-22s | %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )
        sh = logging.StreamHandler(sys.stdout)
        sh.setFormatter(fmt)
        root = logging.getLogger()
        root.setLevel(logging.INFO)
        root.addHandler(sh)
        fh = logging.FileHandler(log_dir / f"run_{datetime.now():%Y%m%d}.log", encoding="utf-8")
        fh.setFormatter(fmt)
        root.addHandler(fh)
        _LOG_INITIALIZED = True
    return logging.getLogger(module)


class StepTimer:
    """模块级耗时记录（写入 outputs/metrics/step_times.csv）。"""

    def __init__(self, step: str, logger: logging.Logger) -> None:
        self.step = step
        self.log = logger

    def __enter__(self) -> "StepTimer":
        self.t0 = time.time()
        self.log.info(">>> START %s", self.step)
        return self

    def __exit__(self, exc_type, exc, tb) -> bool:
        dt = time.time() - self.t0
        status = "OK" if exc_type is None else f"ERROR({exc_type.__name__})"
        self.log.info("<<< END   %s | %.2fs | %s", self.step, dt, status)
        path = PATHS.metric("step_times.csv")
        row = pd.DataFrame(
            [{"step": self.step, "seconds": round(dt, 3), "status": status,
              "timestamp": datetime.now().isoformat(timespec="seconds")}]
        )
        if path.exists():
            row = pd.concat([pd.read_csv(path), row], ignore_index=True)
        row.to_csv(path, index=False, encoding="utf-8-sig")
        return False  # 不吞异常


# -----------------------------------------------------------------------------
# 阻断记录（BLOCKERS.md）
# -----------------------------------------------------------------------------
def log_blocker(module: str, reason: str, detail: str = "") -> None:
    """数据列缺失 / 版本冲突 / 日期范围异常 → 记录阻断，但不让其他模块停摆。"""
    p = PATHS.report("BLOCKERS.md")
    if not p.exists():
        p.write_text(
            "# BLOCKERS — 数据阻断与降级记录\n\n"
            "> 规则：数据不支持时宁可记录 BLOCKED，也不补造、不静默失败。\n"
            "> 单个模块阻断不影响其他模块继续执行。\n\n",
            encoding="utf-8",
        )
    with p.open("a", encoding="utf-8") as f:
        f.write(
            f"## {module}\n\n"
            f"- 记录时间：{datetime.now():%Y-%m-%d %H:%M:%S}\n"
            f"- 原因：{reason}\n"
            f"- 详情：{detail or '—'}\n"
            f"- 处理：该模块对应分析标记为 `NOT SUPPORTED BY CURRENT DATA`\n\n"
        )
    get_logger(module).warning("BLOCKER 已记录: %s | %s", reason, detail)


# -----------------------------------------------------------------------------
# 输入读取
# -----------------------------------------------------------------------------
def read_input(name: str, parse_dates: Optional[Iterable[str]] = None, **kw) -> pd.DataFrame:
    p = PATHS.inp(name)
    if p.suffix == ".parquet":
        df = pd.read_parquet(p)
    else:
        df = pd.read_csv(p, low_memory=False, **kw)
    for c in list(parse_dates or []):
        if c in df.columns:
            df[c] = pd.to_datetime(df[c], errors="coerce")
    return df


def sha256_of(path: Path, chunk: int = 1 << 20) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for blk in iter(lambda: f.read(chunk), b""):
            h.update(blk)
    return h.hexdigest()


def file_signature(path: Path, compute_hash: bool = True) -> Dict[str, Any]:
    st = path.stat()
    try:
        rel = str(path.relative_to(PATHS.warehouse_root))
    except ValueError:
        rel = str(path)
    sig: Dict[str, Any] = {
        "path": str(path),
        "relative_path": rel,
        "size_bytes": st.st_size,
        "mtime": datetime.fromtimestamp(st.st_mtime).isoformat(timespec="seconds"),
    }
    if compute_hash:
        sig["sha256"] = sha256_of(path)
    if path.suffix == ".csv":
        try:
            df = pd.read_csv(path, nrows=200000, low_memory=False)
            sig["rows_sampled"] = int(len(df))
            sig["columns"] = int(df.shape[1])
        except Exception:
            pass
    return sig


# -----------------------------------------------------------------------------
# 输出
# -----------------------------------------------------------------------------
def save_table(df: pd.DataFrame, name: str, index: bool = False, both: bool = False) -> Path:
    p = PATHS.table(name)
    df.to_csv(p, index=index, encoding="utf-8-sig")
    if both and p.suffix == ".csv":
        try:
            df.to_parquet(p.with_suffix(".parquet"), index=index)
        except Exception:
            pass
    return p


def save_parquet(df: pd.DataFrame, key_or_name: str) -> Path:
    if key_or_name in PATHS.artifacts:
        p = PATHS.out(key_or_name)
    elif "/" in key_or_name:
        p = PATHS.out(key_or_name)
    else:
        p = PATHS.out(f"data/processed/{key_or_name}")
    df.to_parquet(p, index=False)
    return p


def load_parquet(key_or_name: str) -> pd.DataFrame:
    if key_or_name in PATHS.artifacts:
        p = PATHS.artifacts[key_or_name]
    elif "/" in key_or_name:
        p = PROJECT_ROOT / key_or_name
    else:
        p = PATHS.out(f"data/processed/{key_or_name}")
    if not p.exists():
        raise FileNotFoundError(
            f"缺少中间产物 {p}；请先运行上游模块（见 reports/DECISION_LOG.md 的执行顺序）"
        )
    return pd.read_parquet(p)


# -----------------------------------------------------------------------------
# 绘图（统一风格；每张图必须能独立说明内容）
# -----------------------------------------------------------------------------
_FONT_READY = False
_CJK_FONTS = ["Hiragino Sans GB", "Heiti TC", "Songti SC", "STHeiti", "Arial Unicode MS"]


def setup_matplotlib():
    global _FONT_READY
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib import font_manager as fm

    if not _FONT_READY:
        avail = {f.name for f in fm.fontManager.ttflist}
        chosen = [f for f in _CJK_FONTS if f in avail]
        plt.rcParams["font.sans-serif"] = chosen + ["DejaVu Sans"]
        plt.rcParams["axes.unicode_minus"] = False
        plt.rcParams.update({
            "figure.dpi": 130,
            "savefig.dpi": 150,
            "savefig.bbox": "tight",
            "axes.grid": True,
            "grid.alpha": 0.25,
            "grid.linestyle": "--",
            "axes.spines.top": False,
            "axes.spines.right": False,
            "font.size": 10.5,
            "axes.titlesize": 12,
            "axes.titleweight": "bold",
            "figure.facecolor": "white",
        })
        _FONT_READY = True
    return plt


FIGURE_SOURCE_LINE = (
    "数据来源：沈阳市场=沈阳市发改委菜篮子信息发布平台（批发口径）；"
    "气象/土壤=Open-Meteo ERA5 / ERA5-Land 再分析（非气象站实测）"
)


def render_figure(fig, name: str, source_note: str = FIGURE_SOURCE_LINE) -> Path:
    """统一落图：底部固定标注数据来源层级与再分析属性。"""
    p = PATHS.figure(name)
    fig.text(0.005, -0.012, source_note, fontsize=7.2, color="#555555", va="top")
    fig.savefig(p)
    import matplotlib.pyplot as plt
    plt.close(fig)
    return p


# -----------------------------------------------------------------------------
# 结果登记（results_registry.csv）
# -----------------------------------------------------------------------------
REGISTRY_COLUMNS = [
    "result_id", "research_question", "crop", "period", "method", "metric",
    "estimate", "ci_low", "ci_high", "p_value", "robustness", "figure", "table",
    "evidence_level", "notes",
]


def register_results(rows: List[Dict[str, Any]]) -> Path:
    """追加写入 results_registry.csv（按 result_id 覆盖同 id 的旧记录）。"""
    p = PATHS.artifacts["results_registry"]
    p.parent.mkdir(parents=True, exist_ok=True)
    new = pd.DataFrame(rows)
    for c in REGISTRY_COLUMNS:
        if c not in new.columns:
            new[c] = None
    new = new[REGISTRY_COLUMNS]
    if p.exists():
        old = pd.read_csv(p)
        if "result_id" in old.columns:
            old = old[~old["result_id"].isin(new["result_id"])]
        new = pd.concat([old, new], ignore_index=True)
    new.to_csv(p, index=False, encoding="utf-8-sig")
    return p


# -----------------------------------------------------------------------------
# 环境记录
# -----------------------------------------------------------------------------
def env_info() -> Dict[str, Any]:
    import importlib
    pkgs = {}
    for m in ["pandas", "numpy", "scipy", "sklearn", "statsmodels", "matplotlib",
              "pyarrow", "lightgbm", "shap", "pygam"]:
        try:
            pkgs[m] = getattr(importlib.import_module(m), "__version__", "?")
        except Exception:
            pkgs[m] = "MISSING"
    return {
        "python": sys.version.split()[0],
        "platform": platform.platform(),
        "packages": pkgs,
        "run_at": datetime.now().isoformat(timespec="seconds"),
    }


# -----------------------------------------------------------------------------
# 统计工具
# -----------------------------------------------------------------------------
def hac_ols(y: np.ndarray, X: np.ndarray, maxlags: int = 14):
    """Newey-West / HAC 稳健标准误 OLS。返回 dict(coef, se, t, p, r2, n)。"""
    import statsmodels.api as sm

    y = np.asarray(y, dtype=float)
    X = np.asarray(X, dtype=float)
    Xc = sm.add_constant(X, has_constant="add")
    model = sm.OLS(y, Xc, missing="drop").fit(
        cov_type="HAC", cov_kwds={"maxlags": maxlags}
    )
    return {
        "coef": model.params,
        "se": model.bse,
        "t": model.tvalues,
        "p": model.pvalues,
        "r2": model.rsquared,
        "adj_r2": model.rsquared_adj,
        "n": int(model.nobs),
        "model": model,
    }


def bh_fdr(pvals: np.ndarray) -> np.ndarray:
    """Benjamini-Hochberg FDR 校正。NaN 原样返回。"""
    p = np.asarray(pvals, dtype=float)
    out = np.full_like(p, np.nan)
    mask = ~np.isnan(p)
    pv = p[mask]
    n = pv.size
    if n == 0:
        return out
    order = np.argsort(pv)
    ranked = pv[order]
    q = ranked * n / (np.arange(1, n + 1))
    q = np.minimum.accumulate(q[::-1])[::-1]
    q = np.clip(q, 0, 1)
    res = np.empty(n)
    res[order] = q
    out[mask] = res
    return out


def bootstrap_ci(
    values: np.ndarray, n_boot: int = 1000, alpha: float = 0.05, seed: Optional[int] = None
):
    rng = np.random.default_rng(seed if seed is not None else ANALYSIS["project"]["random_seed"])
    v = np.asarray(values, dtype=float)
    v = v[~np.isnan(v)]
    if v.size < 3:
        return (np.nan, np.nan)
    idx = rng.integers(0, v.size, size=(n_boot, v.size))
    boots = v[idx].mean(axis=1)
    return (float(np.quantile(boots, alpha / 2)), float(np.quantile(boots, 1 - alpha / 2)))


def safe_div(a, b, fill=np.nan):
    with np.errstate(divide="ignore", invalid="ignore"):
        r = np.where((b == 0) | pd.isna(b), fill, a / b)
    return r


def require_columns(df: pd.DataFrame, cols: Iterable[str], module: str) -> bool:
    missing = [c for c in cols if c not in df.columns]
    if missing:
        log_blocker(module, "缺少必需数据列", f"missing={missing}; available={list(df.columns)}")
        return False
    return True
