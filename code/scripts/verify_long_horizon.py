#!/usr/bin/env python3
"""V2 独立验收：报告/Registry/双目标/未见证据/freshness/模型包，不训练。"""
import json
import math
from pathlib import Path
import pandas as pd
ROOT = Path(__file__).resolve().parents[1]
PROJECT = ROOT.parent                      # monorepo 根（data/ 与 models/ 所在）
RUNTIME = ROOT / 'runtime'                 # 产品运行时资产
# 交付报告分散在：AgriScope 根（LLM 报告）、runtime、根 data/research/long_horizon、archive
SEARCH_DIRS = [ROOT, RUNTIME,
               PROJECT / 'data' / 'research' / 'long_horizon',
               PROJECT / 'archive' / 'agent_reports',
               PROJECT / 'archive' / 'audits']
DELIVERABLES = ['LONG_HORIZON_V2_TARGET_REPORT.md','LONG_HORIZON_V2_EVALUATION_REPORT.md',
 'LONG_HORIZON_V2_METRICS.csv','LONG_HORIZON_V2_REGISTRY.csv','HARVEST_WINDOW_REPORT.md',
 'LONG_HORIZON_SAMPLE_ACCOUNTING.csv','SAMPLE_ACCOUNTING_REPORT.md','PRODUCTION_GATE_REPORT.md',
 'LLM_REAL_EVALUATION_REPORT.md','LLM_ABLATION_V2_REPORT.md','HYBRID_V2_REPORT.md',
 'DECISION_LONG_HORIZON_BACKTEST.md']


def _find(name):
    for d in SEARCH_DIRS:
        p = d / name
        if p.is_file():
            return p
    return None


def main():
    problems = []
    for name in DELIVERABLES:
        if _find(name) is None: problems.append('Missing report: '+name)
    if problems:
        print('\n'.join(problems));return 1
    registry = pd.read_csv(RUNTIME/'LONG_HORIZON_V2_REGISTRY.csv')
    snap = json.loads((RUNTIME/'data/processed/long_horizon/snapshots/latest.json').read_text())
    index = json.loads((PROJECT/'models/long_horizon/index.json').read_text())
    entries = snap.get('entries', [])
    keys = lambda rows: {(r['crop'],int(r['horizon']),r['target_type']) for r in rows}
    if len(registry)!=120 or len(entries)!=120 or keys(registry.to_dict('records'))!=keys(entries):
        problems.append('Registry/snapshot must have paired 10x6x2 distinct entries')
    if len(keys(entries)) != len(entries): problems.append('Duplicate entries')
    for k in ['schema_version','model_version','training_data_version','runtime_data_version','as_of',
              'latest_data_date','generated_at','method_registry_version','llm_model','prompt_version']:
        if k not in snap: problems.append('Missing snapshot version: '+k)
    if snap.get('schema_version')!='lh_forecast_v2': problems.append('Unsupported snapshot schema')
    if snap.get('method_registry_version')!=index.get('method_registry_version'):
        problems.append('Registry version mismatch')
    for e in entries:
        if e.get('available'):
            vals=[e.get('range_low'),e.get('point_forecast'),e.get('range_high')]
            if any(v is None or not math.isfinite(v) for v in vals) or not 0 < vals[0]<=vals[1]<=vals[2]:
                problems.append('Invalid numeric interval')
        if e.get('unit')!='CNY/kg': problems.append('Unit mismatch')
        if not e.get('actual_method') or not isinstance(e.get('fallback_used'),bool):
            problems.append('Missing actual method/fallback semantics')
        if not e.get('target_window',{}).get('definition'): problems.append('Missing target definition')
        if index.get('evaluation_status')=='RETROSPECTIVE_ONLY_NO_UNTOUCHED':
            if e.get('production_status') in ['PRODUCTION_POINT','PRODUCTION_SCENARIO']:
                problems.append('Historical reused evidence cannot upgrade production')
            if e.get('range_type')!='scenario_range' or e.get('confidence')!='low':
                problems.append('Insufficient final evidence must remain low confidence scenario')
        if e.get('llm_used'): problems.append('Unevaluated LLM enters numeric output')
    if registry.untouched_metric.notna().any() or (registry.final_effective_n!=0).any():
        problems.append('Reused historical evaluation incorrectly reported as untouched')
    accounting=pd.read_csv(_find('LONG_HORIZON_SAMPLE_ACCOUNTING.csv'))
    if not {'calendar_candidates','observed_candidates','nonoverlap_samples','effective_test_samples','fold'} <= set(accounting):
        problems.append('Incomplete sample accounting')
    daily=json.loads((RUNTIME/'data/processed/daily/snapshots/latest.json').read_text())
    if snap['latest_data_date'] < daily['latest_data_date']: problems.append('Long-Horizon has not caught up to Daily')
    print(json.dumps({'status':'LONG_HORIZON_V2_ENGINEERING_ACCEPTANCE_PASS' if not problems else 'FAIL',
                      'registry_rows':len(registry),'snapshot_entries':len(entries),'as_of':snap['as_of'],
                      'untouched_n':0,'scientific_status':index['evaluation_status'],'problems':problems},ensure_ascii=False))
    return 1 if problems else 0


if __name__=='__main__':
    raise SystemExit(main())
