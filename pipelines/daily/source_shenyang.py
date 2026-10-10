# -*- coding: utf-8 -*-
"""P0 数据源：沈阳菜篮子信息发布平台（结构化 JSON，日度，公开无鉴权）。

复用 AgriScope/pipelines/data_foundation/collectors/shenyang_price.py 已验证的接口与参数：
    GET {SOURCE_API}?marketType={1|2|3}&dates=YYYY-MM-DD&page=1&limit=100

原始响应原样落盘（原子写、不修改）：
    data/raw/daily/shenyang_clz/<date>/mt<n>.json      原始 JSON
    data/raw/daily/shenyang_clz/<date>/metadata.json   抓取元数据（URL/时间/状态/条数）

网络礼貌：合理 User-Agent、有限重试、超时、请求间隔。
"""
from __future__ import annotations

import json
import ssl
import time
import urllib.parse
import urllib.request
from dataclasses import dataclass, field, asdict
from pathlib import Path

from . import config as C
from . import io_utils as IO

_UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
       "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")

# 抓取状态
ST_OK = "OK"
ST_EMPTY = "EMPTY"
ST_FAIL = "FAIL"
ST_SKIPPED = "SKIPPED"

# 结构漂移标记（fail loud）
SCHEMA_CHANGED = "SOURCE_SCHEMA_CHANGED"


@dataclass
class RawResult:
    date: str
    market_type: str
    url: str
    status: str
    count: int = 0
    records: list = field(default_factory=list)
    raw_path: str | None = None
    error: str | None = None
    crawl_time: str = ""
    http_attempts: int = 0
    schema_ok: bool = True
    schema_note: str | None = None


def _ctx() -> ssl.SSLContext:
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    return ctx


def _build_url(target_date: str, market_type: str) -> str:
    params = {"marketType": market_type, "dates": target_date, "page": 1, "limit": 100}
    return f"{C.SOURCE_API}?{urllib.parse.urlencode(params)}"


def fetch(target_date: str, market_type: str, retries: int | None = None,
          timeout: int | None = None) -> RawResult:
    """抓取单个 (日期, marketType)。带有限重试与超时，失败不抛异常、只记录。"""
    retries = C.HTTP_RETRIES if retries is None else retries
    timeout = C.HTTP_TIMEOUT if timeout is None else timeout
    url = _build_url(target_date, market_type)
    now = IO.now_str()
    last_err = None
    for attempt in range(1, retries + 1):
        try:
            req = urllib.request.Request(url, headers={
                "User-Agent": _UA,
                "X-Requested-With": "XMLHttpRequest",
                "Referer": C.SOURCE_REFERER,
            })
            with urllib.request.urlopen(req, timeout=timeout, context=_ctx()) as resp:
                body = resp.read().decode("utf-8", "replace")
            obj = json.loads(body)
            data = obj.get("data")
            if data is None:
                # 结构变化：期望 data 字段却不存在 → fail loud，不当作"空"
                return RawResult(date=target_date, market_type=market_type, url=url,
                                 status=ST_EMPTY, count=0, records=[],
                                 crawl_time=now, http_attempts=attempt,
                                 schema_ok=False,
                                 schema_note=f"{SCHEMA_CHANGED}: 响应缺少 data 字段（keys={sorted(obj)[:8]}）")
            res = RawResult(date=target_date, market_type=market_type, url=url,
                            status=ST_OK if data else ST_EMPTY, count=len(data),
                            records=data, crawl_time=now, http_attempts=attempt)
            res.schema_note = _schema_check(res)
            res.schema_ok = not (res.schema_note or "").startswith(SCHEMA_CHANGED)
            return res
        except Exception as exc:  # noqa: BLE001
            last_err = repr(exc)[:200]
            if attempt < retries:
                time.sleep(1.5 * attempt)
    return RawResult(date=target_date, market_type=market_type, url=url, status=ST_FAIL,
                     error=last_err, crawl_time=now, http_attempts=retries)


# 必需字段（结构漂移 fail-loud 的依据）
_REQUIRED_FIELDS = ("productName", "price", "unit")


def _schema_check(res: RawResult) -> str | None:
    """字段级结构检查：批发口径作物数异常或必需字段缺失 → SOURCE_SCHEMA_CHANGED。"""
    if res.status != ST_OK or not res.records:
        return None
    missing = [k for k in _REQUIRED_FIELDS if not any(k in r for r in res.records)]
    if missing:
        return f"{SCHEMA_CHANGED}: 记录缺少必需字段 {missing}"
    is_wholesale = C.MARKET_TYPES.get(res.market_type, {}).get("model_comparable")
    if is_wholesale and res.count != C.EXPECTED_WHOLESALE_CROPS:
        return (f"{SCHEMA_CHANGED}: 批发口径作物数 {res.count} ≠ 期望 "
                f"{C.EXPECTED_WHOLESALE_CROPS}")
    return None


def _archive(result: RawResult) -> RawResult:
    """原始响应 + 元数据落盘（原子写；dry-run 不落盘）。

    同一日期重复抓取：旧响应不被删除，移入 attempts/ 保留（可追溯每次 attempt），
    当前 mt<n>.json 为**本次使用**的响应。
    """
    day_dir = C.RAW_DAILY_DIR / "shenyang_clz" / result.date
    day_dir.mkdir(parents=True, exist_ok=True)
    raw_file = day_dir / f"mt{result.market_type}.json"
    if result.status in (ST_OK, ST_EMPTY):
        if raw_file.exists():
            prev = IO.read_json_safe(raw_file, {}) or {}
            if (prev.get("count"), prev.get("data")) != (result.count, result.records):
                attempts = day_dir / "attempts"
                attempts.mkdir(parents=True, exist_ok=True)
                meta_old = IO.read_json_safe(day_dir / "metadata.json", {}) or {}
                ts = str((meta_old.get(f"mt{result.market_type}") or {})
                         .get("crawl_time", "unknown")).replace(":", "").replace(" ", "T")
                IO.atomic_write_text(attempts / f"mt{result.market_type}.{ts}.json",
                                     json.dumps(prev, ensure_ascii=False))
        payload = {"code": 0, "count": result.count, "data": result.records}
        IO.atomic_write_text(raw_file, json.dumps(payload, ensure_ascii=False))
        result.raw_path = str(raw_file.relative_to(C.ROOT))
    meta_file = day_dir / "metadata.json"
    meta = IO.read_json_safe(meta_file, {}) or {}
    mt_meta = asdict(result)
    mt_meta.pop("records", None)
    mt_meta["price_level"] = C.MARKET_TYPES.get(result.market_type, {}).get("price_level")
    mt_meta["market_cn"] = C.MARKET_TYPES.get(result.market_type, {}).get("market_cn")
    mt_meta["source_id"] = C.SOURCE_ID
    mt_meta["source_name"] = C.SOURCE_NAME
    mt_meta["source_url"] = C.SOURCE_URL
    mt_meta["parser_version"] = C.SOURCE_PARSER_VERSION
    mt_meta["timezone"] = C.SOURCE_TIMEZONE
    meta[f"mt{result.market_type}"] = mt_meta
    meta["date"] = result.date
    IO.atomic_write_json(meta_file, meta)
    return result


def _has_data(raw_file: Path) -> bool:
    """已归档的原始文件是否含有效数据（空响应不算，必须重取）。"""
    obj = IO.read_json_safe(raw_file)
    return bool(obj and obj.get("data"))


def collect_day(target_date: str, market_types: list[str] | None = None,
                dry_run: bool = False, skip_existing: bool = False) -> list[RawResult]:
    """采集某一天全部 marketType。

    skip_existing 仅对**已含有效数据**的日期生效；空响应会被重新抓取，
    避免"当日尚未发布"被永久跳过（发布延迟场景）。
    目标日期由调用方保证总是重取。
    """
    market_types = market_types or list(C.MARKET_TYPES.keys())
    out: list[RawResult] = []
    for mt in market_types:
        raw_file = C.RAW_DAILY_DIR / "shenyang_clz" / target_date / f"mt{mt}.json"
        legacy = C.DATA_DIR / "raw" / "prices" / "shenyang_clz" / f"{target_date}_mt{mt}.json"
        if skip_existing and _has_data(raw_file):
            out.append(RawResult(date=target_date, market_type=mt,
                                 url=_build_url(target_date, mt), status=ST_SKIPPED,
                                 raw_path=str(raw_file.relative_to(C.ROOT))))
            continue
        if skip_existing and _has_data(legacy) and not raw_file.exists():
            _copy_legacy(legacy, raw_file)
            n = len(IO.read_json_safe(raw_file, {}).get("data") or [])
            out.append(RawResult(date=target_date, market_type=mt,
                                 url=_build_url(target_date, mt), status=ST_SKIPPED,
                                 count=n, raw_path=str(raw_file.relative_to(C.ROOT))))
            continue
        res = fetch(target_date, mt)
        if not dry_run:
            _archive(res)
        elif res.status in (ST_OK, ST_EMPTY):
            res.raw_path = None
        out.append(res)
        time.sleep(C.HTTP_SLEEP)
    return out


def _copy_legacy(legacy: Path, raw_file: Path) -> None:
    """旧布局已有有效数据 → 搬运行证据（不重复请求），保留来源标注。"""
    raw_file.parent.mkdir(parents=True, exist_ok=True)
    IO.atomic_write_bytes(raw_file, legacy.read_bytes())
    meta_file = raw_file.parent / "metadata.json"
    meta = IO.read_json_safe(meta_file, {}) or {}
    meta["date"] = raw_file.parent.name
    meta.setdefault("migrated_from_legacy", str(legacy.relative_to(C.ROOT)))
    IO.atomic_write_json(meta_file, meta)