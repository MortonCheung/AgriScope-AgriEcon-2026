"""Daily 后独立长期推理：只加载模型，绝不 fit 或重新选择方法。"""
from __future__ import annotations
import argparse
import contextlib
import fcntl
import hashlib
import json
import os
import sys
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Optional
from zoneinfo import ZoneInfo
import numpy as np
import pandas as pd
from joblib import parallel_backend

_HERE = Path(__file__).resolve()
PROJECT = Path(os.environ.get('PROJECT_ROOT') or _HERE.parents[3]).resolve()   # monorepo 根
AGRISCOPE = _HERE.parents[2]                                                   # AgriScope 仓
for path in (AGRISCOPE, AGRISCOPE / 'pipelines', AGRISCOPE / 'pipelines' / 'modeling',
             AGRISCOPE / 'pipelines' / 'modeling' / 'src'):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))
SNAPSHOT_DIR = PROJECT / 'data/processed/long_horizon/snapshots'
LOCK_PATH = PROJECT / 'data/processed/long_horizon/.run.lock'
FROZEN_DATA = PROJECT / 'data/model_ready/snapshots/final_v1/datasets/decision_dataset_沈阳.parquet'
DAILY_DATA = PROJECT / 'data/processed/daily/daily_market_price.parquet'
DAILY_LATEST = PROJECT / 'data/processed/daily/snapshots/latest.json'
TARGETS = ('cycle_market_average', 'harvest_market_price')
HORIZONS = (30, 60, 90, 120, 150, 180)
SCHEMA = 'lh_forecast_v2'


def digest(obj):
    raw = json.dumps(obj, ensure_ascii=False, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()
    return hashlib.sha256(raw).hexdigest()


def load_runtime_history(as_of=None):
    """保留冻结历史，只追加 QC OK、沈阳、wholesale、同口径的更新观测。"""
    frozen = pd.read_parquet(FROZEN_DATA)[['date', 'crop', 'price_per_kg']].copy()
    frozen['date'] = pd.to_datetime(frozen['date'])
    daily_meta = json.loads(DAILY_LATEST.read_text()) if DAILY_LATEST.exists() else {}
    appended = pd.DataFrame(columns=frozen.columns)
    committed = (daily_meta.get('status') in ('complete', 'partial') and
                 daily_meta.get('contract_valid') is True and daily_meta.get('crawl_status') != 'FAILED' and
                 daily_meta.get('latest_data_date'))
    committed_cutoff = min(pd.Timestamp(daily_meta['latest_data_date']),
                           pd.Timestamp(datetime.now(ZoneInfo('Asia/Shanghai')).date())) if committed else None
    if as_of and committed_cutoff is not None:
        committed_cutoff = min(committed_cutoff, pd.Timestamp(as_of))
    if DAILY_DATA.exists() and committed_cutoff is not None:
        d = pd.read_parquet(DAILY_DATA)
        required = {'date', 'city', 'crop_standard', 'price_per_kg', 'price_level', 'model_comparable', 'quality_status'}
        if not required <= set(d.columns):
            raise ValueError('Daily normalized schema mismatch')
        d['date'] = pd.to_datetime(d['date'])
        d = d[d.date <= committed_cutoff]
        d['price_per_kg'] = pd.to_numeric(d['price_per_kg'], errors='coerce')
        d = d[(d.city == '沈阳') & (d.price_level == 'wholesale') & (d.model_comparable == True) &
              (d.quality_status == 'OK') & np.isfinite(d.price_per_kg) & (d.price_per_kg > 0)]
        d = d.rename(columns={'crop_standard': 'crop'})
        ends = frozen.groupby('crop').date.max()
        d = d[d.crop.isin(ends.index)]
        d = d[d.date > d.crop.map(ends)]
        appended = d.groupby(['crop', 'date'], as_index=False).price_per_kg.median()
    history = frozen.copy() if appended.empty else pd.concat([frozen, appended], ignore_index=True)
    if as_of:
        history = history[history.date <= pd.Timestamp(as_of)]
    history = history.sort_values(['crop', 'date']).reset_index(drop=True)
    if history.empty:
        raise ValueError('No market history at cutoff')
    serial = [{'crop': r.crop, 'date': str(r.date.date()), 'price': float(r.price_per_kg)} for r in history.itertuples()]
    return history, {'runtime_data_version': digest(serial), 'latest_data_date': str(history.date.max().date()),
                     'daily_latest_data_date': daily_meta.get('latest_data_date'),
                     'daily_status': daily_meta.get('status', 'unavailable'),
                     'daily_freshness': daily_meta.get('data_freshness', 'UNKNOWN'),
                     'appended_rows': len(history) - len(frozen[frozen.date <= history.date.max()]),
                     'source': 'frozen_final_history+daily_QC_OK_wholesale_append'}


def number(v):
    if v is None or isinstance(v, bool):
        return None
    v = float(v)
    return v if np.isfinite(v) else None


def build(as_of: Optional[str] = None):
    from long_horizon.v2 import load_bundle, predict_at
    history, runtime = load_runtime_history(as_of)
    bundle = load_bundle()
    latest = runtime['latest_data_date']
    if as_of and str(pd.Timestamp(as_of).date()) > latest:
        raise ValueError('as_of cannot advance beyond observed market history')
    entries = []
    for crop in sorted(history.crop.unique()):
        anchor = history.loc[history.crop == crop, 'date'].max()
        for h in HORIZONS:
            for target in TARGETS:
                # Forest 的并行累加顺序会产生 1e-15 级浮点差，影响快照哈希。
                # 推理串行调度；不改已训练权重/参数、统计方法或评估配置。
                with parallel_backend('sequential'):
                    r = predict_at(bundle, history, crop, h, target)
                registered = next(e for e in bundle['entries'] if e['key'] == f'{crop}|{h}|{target}')
                pt, lo, hi = [number(r.get(k, r.get(alt))) for k, alt in
                              [('point', 'point_forecast'), ('low', 'range_low'), ('high', 'range_high')]]
                if pt is not None and (pt <= 0 or lo is None or hi is None or not 0 < lo <= pt <= hi):
                    raise ValueError(f'Invalid forecast range: {crop}/{h}/{target}')
                start = int(r.get('window_start_offset', r.get('start_offset', 1)))
                end = int(r.get('window_end_offset', r.get('end_offset_exclusive', h + 1)))
                entries.append({'crop': crop, 'horizon': h, 'target_type': target,
                    'method': r.get('method'), 'actual_method': r.get('actual_method', r.get('method')),
                    'production_status': r.get('production_status', r.get('status', 'SCENARIO_ONLY')),
                    'confidence': r.get('confidence', 'low'), 'range_type': r.get('range_type', 'scenario_range'),
                    'unit': 'CNY/kg', 'point_forecast': pt, 'range_low': lo, 'range_high': hi,
                    'available': pt is not None, 'reason': r.get('reason'),
                    'fallback_used': bool(r.get('fallback_used', False)), 'forecast_source': 'scenario_only',
                    'current_price': float(history[history.crop == crop].iloc[-1].price_per_kg),
                    'anchor_observation_date': str(anchor.date()),
                    'target_window': {'definition': r.get('window_definition', r.get('window', target)),
                        'start_offset': start, 'end_offset_exclusive': end,
                        'start_date': str((anchor + pd.Timedelta(days=start)).date()),
                        'end_date_exclusive': str((anchor + pd.Timedelta(days=end)).date())},
                    'model_disagreement': r.get('model_disagreement', {}),
                    'baseline_method': registered.get('baseline_method', registered.get('fallback')),
                    'baseline_point': r.get('model_disagreement', {}).get(registered.get('baseline_method', registered.get('fallback'))),
                    'last_value_point': r.get('model_disagreement', {}).get('last_value'),
                    'model_disagreement_pct': number(r.get('model_disagreement_pct')),
                    'sample_n': r.get('sample_n', 0), 'effective_n': r.get('effective_n', 0),
                    'retrospective_effective_n': r.get('retrospective_effective_n', r.get('effective_n', 0)),
                    'final_effective_n': r.get('final_effective_n', 0),
                    'evidence_status': r.get('evidence_status', 'RETROSPECTIVE_ONLY_NO_UNTOUCHED'),
                    'llm_used': False, 'llm_status': 'LLM_UNAVAILABLE',
                    'range_band_source': 'separate_2025_calibration_residuals_scenario_only'})
    snap = {'schema_version': SCHEMA, 'model_version': bundle.get('model_version', 'long_horizon_v2'),
        'training_data_version': bundle.get('training_data_version', bundle.get('data_version', 'final_v1')),
        'runtime_data_version': runtime['runtime_data_version'], 'data_version': runtime['runtime_data_version'],
        'as_of': latest, 'market_as_of': latest, 'latest_data_date': latest,
        'method_registry_version': bundle.get('method_registry_version', bundle.get('config_hash')),
        'evaluation_config_hash': bundle.get('config_hash'),
        'issuance_protocol': {'version': 'prospective_issuance_v1', 'max_origin_age_days': 1,
                              'duplicate_rule': 'earliest_valid_publication', 'origin_not_before': '2026-10-08'},
        'llm_model': None, 'prompt_version': None, 'city': '沈阳', 'unit': 'CNY/kg',
        'horizons': list(HORIZONS), 'target_types': list(TARGETS), 'n_entries': len(entries),
        'entries': entries, 'runtime': runtime, 'status': 'SCENARIO_ONLY_PENDING_PROSPECTIVE_VALIDATION',
        'notes': ['上市窗口价格与周期市场均价回答两个不同问题；收益情景采用上市窗口价格。',
                  '2026历史核验已被RC1查看，不能称untouched；未来独立样本尚不足，不作强推荐。',
                  '区间是情景范围，不是经过独立验证的概率预测区间。',
                  'Daily后仅推理，不重训、不重新选型；LLM未通过真实评估，不参与数值。',
                  '用户选择预计上市日期/跨度；未根据作物名猜测生育期。']}
    snap['snapshot_hash'] = digest(snap)
    return snap


@contextlib.contextmanager
def job_lock():
    LOCK_PATH.parent.mkdir(parents=True, exist_ok=True)
    with LOCK_PATH.open('a+') as handle:
        try:
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            raise RuntimeError('Long-Horizon job already running') from exc
        try:
            yield
        finally:
            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


def atomic_json(path, obj):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix='.publish-', suffix='.tmp', dir=path.parent)
    try:
        with os.fdopen(fd, 'w', encoding='utf-8') as f:
            json.dump(obj, f, ensure_ascii=False, indent=2, allow_nan=False)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, path)
        dir_fd = os.open(path.parent, os.O_RDONLY)
        try:
            os.fsync(dir_fd)
        finally:
            os.close(dir_fd)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)


def write_snapshot(snap, *, locked=False):
    if not locked:
        with job_lock():
            return write_snapshot(snap, locked=True)
    SNAPSHOT_DIR.mkdir(parents=True, exist_ok=True)
    latest = SNAPSHOT_DIR / 'latest.json'
    old = json.loads(latest.read_text()) if latest.exists() else {}
    if old.get('snapshot_hash') == snap['snapshot_hash']:
        return {'path': str(latest), 'latest_written': False, 'idempotent': True,
                'snapshot_hash': snap['snapshot_hash'], 'n_entries': snap['n_entries']}
    payload = dict(snap, generated_at=datetime.now(ZoneInfo('Asia/Shanghai')).isoformat(timespec='seconds'))
    archive = SNAPSHOT_DIR / 'history' / snap['as_of'] / (snap['snapshot_hash'] + '.json')
    if not archive.exists():
        atomic_json(archive, payload)
    target = SNAPSHOT_DIR / f"{snap['as_of']}.json"
    atomic_json(target, payload)
    advanced = str(snap['as_of']) >= str(old.get('as_of', ''))
    if advanced:
        atomic_json(latest, payload)
    return {'path': str(target), 'latest_written': advanced, 'idempotent': False,
            'snapshot_hash': snap['snapshot_hash'], 'n_entries': snap['n_entries']}


def run(as_of=None):
    with job_lock():
        return write_snapshot(build(as_of), locked=True)


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--as-of', default=None)
    args = ap.parse_args()
    try:
        print(json.dumps(run(args.as_of), ensure_ascii=False))
        return 0
    except Exception as exc:
        print(json.dumps({'status': 'LONG_HORIZON_JOB_FAILED', 'error_type': type(exc).__name__, 'message': str(exc)}, ensure_ascii=False))
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
