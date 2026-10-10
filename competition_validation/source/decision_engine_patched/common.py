# -*- coding: utf-8 -*-
"""AgriScope Decision Engine — 通用工具（配置加载 / 路径 / IO）"""
from __future__ import annotations
import hashlib
import json
import os
from pathlib import Path
from typing import Any, Dict

import yaml

# 项目根：优先 PROJECT_ROOT/AGRISCOPE_ROOT 环境变量，否则由本文件位置推导
# （PORTABILITY_PATCH：仅路径解析方式改变；算法/权重/数据/模型产物均未改动）
ROOT = Path(
    os.environ.get("PROJECT_ROOT")
    or os.environ.get("AGRISCOPE_ROOT")
    or Path(__file__).resolve().parents[3]
).resolve()
DE = ROOT / "models"


def load_yaml(name: str) -> Dict[str, Any]:
    with open(DE / "config" / name, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def paths() -> Dict[str, Any]:
    return load_yaml("paths.yaml")


def model_config() -> Dict[str, Any]:
    return load_yaml("model_config.yaml")


def feature_config() -> Dict[str, Any]:
    return load_yaml("feature_config.yaml")


def proj(*parts: str) -> Path:
    return ROOT.joinpath(*parts)


def de_path(*parts: str) -> Path:
    return DE.joinpath(*parts)


def sha256_file(path: Path, chunk: int = 1 << 20) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while True:
            b = f.read(chunk)
            if not b:
                break
            h.update(b)
    return h.hexdigest()


def ensure_dir(p: Path) -> Path:
    p.mkdir(parents=True, exist_ok=True)
    return p


def write_json(obj: Any, path: Path) -> None:
    ensure_dir(path.parent)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=2, default=str)


def read_json(path: Path) -> Any:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)