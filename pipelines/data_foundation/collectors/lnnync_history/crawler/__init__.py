"""辽宁省农业农村厅农产品价格数据采集器。

模块划分：
    client     HTTP 客户端（限速 / 退避重试）
    listing    分类列表分页遍历 → article_index.csv
    article    文章正文下载与原始 HTML 备份
    parser     正文结构化解析 → Long Format 记录
    normalize  产品名 / 行政区划 / 单位标准化
    validators 数据质量校验
"""
from __future__ import annotations

import logging
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
LOG_DIR = PROJECT_ROOT / "logs"
LOG_DIR.mkdir(parents=True, exist_ok=True)

_CONFIGURED = False


def setup_logging(level: int = logging.INFO) -> None:
    global _CONFIGURED
    if _CONFIGURED:
        return
    fmt = logging.Formatter(
        fmt="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    root = logging.getLogger()
    root.setLevel(level)

    console = logging.StreamHandler(sys.stdout)
    console.setFormatter(fmt)
    console.setLevel(level)
    root.addHandler(console)

    file_handler = logging.FileHandler(LOG_DIR / "crawler.log", encoding="utf-8")
    file_handler.setFormatter(fmt)
    file_handler.setLevel(logging.DEBUG)
    root.addHandler(file_handler)

    _CONFIGURED = True


def get_logger(name: str) -> logging.Logger:
    setup_logging()
    return logging.getLogger(name)
