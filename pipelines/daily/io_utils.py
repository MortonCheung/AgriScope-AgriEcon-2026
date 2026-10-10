# -*- coding: utf-8 -*-
"""Daily 工程基础设施：原子写入 / 进程锁 / 统一时区 / 时间戳。

服务器长期运行要求：
  - 任何关键写入（parquet / json）不得中途崩溃留下半个文件；
  - 定时任务与人工 backfill 不得并发写坏数据；
  - 业务日期、crawl_time、published_at 必须显式使用 Asia/Shanghai，
    不依赖服务器系统时区。
"""
from __future__ import annotations

import errno
import json
import os
import time
from datetime import date, datetime
from pathlib import Path
from typing import Any

try:  # Python 3.9+
    from zoneinfo import ZoneInfo
    TZ = ZoneInfo("Asia/Shanghai")
except Exception:  # 极端环境缺失 tzdata 时退化，但显式固定 +8，不用系统时区
    from datetime import timedelta, timezone as _tz
    TZ = _tz(timedelta(hours=8), name="Asia/Shanghai")

TZ_NAME = "Asia/Shanghai"


# ---------------------------------------------------------------- 时间
def now_tz() -> datetime:
    """当前北京时间（带 tzinfo）。"""
    return datetime.now(TZ)


def now_str() -> str:
    return now_tz().strftime("%Y-%m-%d %H:%M:%S")


def today_str() -> str:
    """业务日期：按北京时间，而非服务器本地日期。"""
    return now_tz().date().isoformat()


def parse_date(s: str) -> date:
    return datetime.strptime(s, "%Y-%m-%d").date()


def add_days(s: str, n: int) -> str:
    from datetime import timedelta
    return (parse_date(s) + timedelta(days=n)).isoformat()


def epoch_ms_to_tz_str(epoch_ms: Any) -> str | None:
    """来源 epoch 毫秒 → 北京时间字符串（来源时间戳为 UTC+8 零点）。"""
    try:
        import pandas as pd
        ts = pd.Timestamp(int(epoch_ms), unit="ms", tz="UTC").tz_convert(TZ_NAME)
        return ts.strftime("%Y-%m-%d %H:%M:%S")
    except Exception:  # noqa: BLE001
        return None


# ---------------------------------------------------------------- 原子写入
def atomic_write_bytes(path: Path, data: bytes) -> None:
    """临时文件 → fsync → 原子 rename，避免半个文件。"""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f".{path.name}.tmp.{os.getpid()}")
    with open(tmp, "wb") as f:
        f.write(data)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, path)


def atomic_write_text(path: Path, text: str, encoding: str = "utf-8") -> None:
    atomic_write_bytes(path, text.encode(encoding))


def atomic_write_json(path: Path, obj: Any) -> None:
    atomic_write_text(path, json.dumps(obj, ensure_ascii=False, indent=2, default=str))


def atomic_write_parquet(df, path: Path) -> None:
    """先写临时 parquet，再原子替换。"""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f".{path.name}.tmp.{os.getpid()}.parquet")
    df.to_parquet(tmp, index=False)
    os.replace(tmp, path)


def atomic_write_csv(df, path: Path, encoding: str = "utf-8-sig") -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f".{path.name}.tmp.{os.getpid()}.csv")
    df.to_csv(tmp, index=False, encoding=encoding)
    os.replace(tmp, path)


def read_json_safe(path: Path, default: Any = None) -> Any:
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        return default


# ---------------------------------------------------------------- 进程锁
class ProcessLock:
    """基于 O_CREAT|O_EXCL 的互斥锁，带过期自愈。

    两个 cron 任务或人工 backfill 同时触发时，后到者立即失败退出，
    绝不并发写 parquet/json。
    """

    def __init__(self, path: Path, stale_after: float = 6 * 3600.0):
        self.path = Path(path)
        self.stale_after = stale_after
        self.acquired = False

    def __enter__(self) -> "ProcessLock":
        self.path.parent.mkdir(parents=True, exist_ok=True)
        deadline = time.time() + self.stale_after
        while True:
            try:
                fd = os.open(self.path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
                os.write(fd, json.dumps({"pid": os.getpid(), "at": now_str()}).encode())
                os.close(fd)
                self.acquired = True
                return self
            except OSError as exc:
                if exc.errno != errno.EEXIST:
                    raise
                # 陈旧锁（进程崩溃遗留）→ 按 mtime 清理
                try:
                    age = time.time() - self.path.stat().st_mtime
                except OSError:
                    continue
                if age > self.stale_after or time.time() > deadline:
                    try:
                        os.unlink(self.path)
                    except OSError:
                        pass
                    continue
                raise RuntimeError(
                    f"另一个 Daily 任务正在运行（锁 {self.path}，age={age:.0f}s）。"
                    "请等待其完成或确认无进程后删除该锁文件。")

    def __exit__(self, *exc) -> None:
        if self.acquired:
            try:
                os.unlink(self.path)
            except OSError:
                pass
            self.acquired = False