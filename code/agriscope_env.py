# -*- coding: utf-8 -*-
"""统一环境变量加载器（全项目唯一实现，禁止各模块重复解析 .env）。

规则（硬约束）：
  1. **系统环境变量优先**：已存在的 `os.environ` 键绝不被 .env 覆盖（`override=False`）。
  2. `.env` 不存在 → 正常运行，不报错、不中断。
  3. 只读取、绝不打印、记录或回传任何值（只返回「读了多少键 / 跳过了多少键」）。
  4. 路径解析顺序：显式参数 > `AGRISCOPE_ENV_FILE` > `AGRISCOPE_ROOT/backend/.env`
     > 本仓库根 `backend/.env`。
  5. 解析规则保守：`KEY=VALUE`（允许 `export ` 前缀、引号、`#` 整行注释、空行），
     不做变量展开、不执行任何命令，避免任何注入面。

用法：
    from agriscope_env import load_env
    load_env()          # 幂等；重复调用无副作用
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import Dict, Optional

REPO_ROOT = Path(__file__).resolve().parent
_DEFAULT_RELATIVE = Path("backend") / ".env"
_LOADED: Dict[str, object] = {"loaded": False, "file": None, "applied": 0, "kept": 0, "rejected": []}

# 判定一个目录是否为合法 AgriScope 根（存在的哨兵文件）。用于拒绝 .env 中过期的绝对路径，
# 避免把后端 / decision_engine / Long-Horizon 静默指向仓库之外的旧数据副本。
ROOT_SENTINELS = ("backend/app/main.py", "models/src/decision_engine/common.py",
                  "data/daily/run_daily.py")
ROOT_KEYS = ("AGRISCOPE_ROOT", "PROJECT_ROOT")


def is_valid_root(path: Path) -> bool:
    try:
        return all((path / name).is_file() for name in ROOT_SENTINELS)
    except OSError:
        return False


def env_file_path(explicit: Optional[Path | str] = None) -> Path:
    if explicit:
        return Path(explicit).expanduser()
    from_env = os.environ.get("AGRISCOPE_ENV_FILE")
    if from_env:
        return Path(from_env).expanduser()
    root = os.environ.get("AGRISCOPE_ROOT")
    base = Path(root).expanduser() if root else REPO_ROOT
    return base / _DEFAULT_RELATIVE


def _parse(text: str) -> Dict[str, str]:
    out: Dict[str, str] = {}
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[7:].strip()
        if "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        if not key or not key.replace("_", "").isalnum():
            continue
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in ("'", '"'):
            value = value[1:-1]
        out[key] = value
    return out


def load_env(path: Optional[Path | str] = None, *, override: bool = False) -> Dict[str, object]:
    """把 .env 注入 os.environ；已存在的键默认保留（系统环境优先）。返回值不含任何机密。"""
    target = env_file_path(path)
    if not target.is_file():
        _LOADED.update({"loaded": False, "file": str(target), "applied": 0, "kept": 0})
        return dict(_LOADED)
    try:
        pairs = _parse(target.read_text(encoding="utf-8"))
    except Exception as error:  # noqa: BLE001
        _LOADED.update({"loaded": False, "file": str(target), "applied": 0, "kept": 0,
                        "error": type(error).__name__})
        return dict(_LOADED)
    applied = kept = 0
    rejected = []
    for key, value in pairs.items():
        if key in os.environ and not override:
            kept += 1
            continue
        if key in ROOT_KEYS and not is_valid_root(Path(value).expanduser()):
            # 过期/错误的根路径：拒绝注入，避免把模型与数据指向错误的目录树。
            rejected.append(key)
            continue
        os.environ[key] = value
        applied += 1
    _LOADED.update({"loaded": True, "file": str(target), "applied": applied,
                    "kept": kept, "rejected": rejected, "keys": sorted(pairs)})
    return dict(_LOADED)


def status() -> Dict[str, object]:
    """诊断信息：文件路径与键名清单（**不含值**）。"""
    info = dict(_LOADED)
    if info.get("loaded") and "keys" not in info:
        try:
            info["keys"] = sorted(_parse(Path(str(info["file"])).read_text(encoding="utf-8")))
        except Exception:  # noqa: BLE001
            info["keys"] = []
    return info


__all__ = ["load_env", "env_file_path", "status", "is_valid_root", "REPO_ROOT", "ROOT_KEYS"]