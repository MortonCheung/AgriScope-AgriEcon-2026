"""plotting.py — 中文字体与科研绘图工具（对齐沈阳 v2 风格）。"""
from __future__ import annotations

from pathlib import Path

FIGSIZE = (7.6, 4.6)
C_MAIN, C_ALT, C_NEG, C_POS = "#2f6f9f", "#c0622b", "#7a5aa8", "#3f8f5f"
C_GREY = "#8a8a8a"


def setup_plt():
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    for f in ["Hiragino Sans GB", "PingFang SC", "Heiti SC", "STHeiti", "Arial Unicode MS", "SimHei"]:
        try:
            matplotlib.font_manager.findfont(f, fallback_to_default=False)
            plt.rcParams["font.family"] = f
            break
        except Exception:  # noqa: BLE001
            continue
    plt.rcParams["axes.unicode_minus"] = False
    plt.rcParams["figure.dpi"] = 130
    return plt


def save_fig(fig, path: Path) -> Path:
    import matplotlib.pyplot as plt
    fig.tight_layout()
    fig.savefig(path, bbox_inches="tight")
    plt.close(fig)
    return path