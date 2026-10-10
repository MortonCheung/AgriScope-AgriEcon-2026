"""Prospective issuance/outcome boundaries and the frozen numerical Gate."""
from copy import deepcopy

import numpy as np
import pandas as pd
import pytest

from scripts import evaluate_prospective_v2 as p
from long_horizon.v2 import target_spec


ORIGIN=pd.Timestamp('2026-10-08')


def fixture(target='harvest_market_price'):
    definition='harvest_post_14' if target=='harvest_market_price' else 'cycle_market_average'
    spec=target_spec(definition,30)
    entry={'key':f'土豆|30|{target}','crop':'土豆','horizon':30,'target_type':target,
           'target_definition':definition,'baseline_method':'same_season_mean','calibration_effective_n':20}
    bundle={'entries':[entry],'prospective_origin_not_before':'2026-10-08','method_registry_version':'test','config_hash':'test'}
    history=pd.DataFrame({'date':pd.date_range(ORIGIN,periods=80),'crop':'土豆','price_per_kg':10.})
    e={'crop':'土豆','horizon':30,'target_type':target,'anchor_observation_date':str(ORIGIN.date()),'available':True,
       'point_forecast':11.,'range_low':9.,'range_high':13.,'baseline_method':'same_season_mean','baseline_point':14.,
       'target_window':{'definition':definition,'start_offset':spec['start_offset'],'end_offset_exclusive':spec['end_exclusive_offset'],
                        'start_date':str((ORIGIN+pd.Timedelta(spec['start_offset'],'D')).date()),
                        'end_date_exclusive':str((ORIGIN+pd.Timedelta(spec['end_exclusive_offset'],'D')).date())}}
    snap={'method_registry_version':'test','evaluation_config_hash':'test','generated_at':'2026-10-08T20:30:00+08:00',
          'issuance_protocol':{'version':'prospective_issuance_v1','max_origin_age_days':1},'entries':[e]}
    seal(snap)
    return bundle,history,snap


def seal(snap):
    snap['snapshot_hash']=p.digest({k:v for k,v in snap.items() if k not in ('snapshot_hash','generated_at')})


def test_delayed_backfill_cannot_be_a_prospective_30_day_forecast():
    bundle,history,snap=fixture()
    snap['generated_at']='2026-11-06T20:30:00+08:00'
    result=p.evaluate_snapshots(bundle,history,[snap])
    assert result['matured_forecasts']==0
    assert result['skipped']['PUBLICATION_NOT_AT_ORIGIN']==1
    assert not result['production_promotion']


def test_cycle_publication_cannot_be_after_first_outcome_date():
    bundle,history,snap=fixture('cycle_market_average')
    snap['generated_at']='2026-10-09T12:00:00+08:00'
    result=p.evaluate_snapshots(bundle,history,[snap])
    assert result['matured_forecasts']==0
    assert result['skipped']['PUBLICATION_AFTER_TARGET_STARTED']==1


def test_immutable_prediction_hash_is_validated():
    bundle,history,snap=fixture()
    snap['entries'][0]['point_forecast']=12.
    with pytest.raises(ValueError,match='checksum'):
        p.evaluate_snapshots(bundle,history,[snap])


def test_window_dates_are_checked_even_if_core_hash_matches():
    bundle,history,snap=fixture()
    snap['entries'][0]['target_window']['end_date_exclusive']='2026-11-22'
    seal(snap)
    with pytest.raises(ValueError,match='definition/date'):
        p.evaluate_snapshots(bundle,history,[snap])


def test_version_mismatch_does_not_mix_refit_models():
    bundle,history,snap=fixture()
    snap['method_registry_version']='other_model'
    result=p.evaluate_snapshots(bundle,history,[snap])
    assert result['matured_forecasts']==0 and result['skipped']['VERSION_MISMATCH']==1


def test_deduplication_uses_earliest_valid_publication_and_reports_raw_count():
    bundle,history,first=fixture()
    later=deepcopy(first)
    later['generated_at']='2026-10-08T23:30:00+08:00'
    later['entries'][0]['point_forecast']=12.;seal(later)
    result=p.evaluate_snapshots(bundle,history,[later,first])
    assert result['raw_archived_forecasts']==2
    assert result['matured_forecasts']==1 and result['duplicate_archived_forecasts']==1
    assert result['groups'][0]['WAPE']==pytest.approx(10.)
    assert result['groups'][0]['status']=='INSUFFICIENT_PROSPECTIVE_EVIDENCE'
    assert not result['groups'][0]['point_gate_pass']


def test_sales_window_matures_only_after_inclusive_last_day():
    bundle,history,snap=fixture()
    # H=30 post14 uses offsets30..43, exclusive end44.
    incomplete=history[history.date<=ORIGIN+pd.Timedelta(42,'D')]
    complete=history[history.date<=ORIGIN+pd.Timedelta(43,'D')]
    assert p.evaluate_snapshots(bundle,incomplete,[snap])['matured_forecasts']==0
    result=p.evaluate_snapshots(bundle,complete,[snap])
    assert result['matured_forecasts']==1
    assert result['groups'][0]['nonoverlap_exposure_blocks']==1


def gate_group(n=15):
    dates=pd.date_range(ORIGIN,periods=n,freq='43D')
    g=pd.DataFrame({'date':dates,'actual':10.,'prediction':9.5,'baseline':12.,'low':9.,'high':11.,'exposure_spacing_days':43})
    g.loc[g.index[:3],'high']=9.8
    return g,{'baseline_method':'same_season_mean','calibration_effective_n':20}


def test_complete_gate_components_use_frozen_thresholds_and_never_promote():
    group,entry=gate_group()
    result=p.gate_components(group,entry)
    assert result['point_gate_pass'] and result['prediction_interval_gate_pass']
    assert result['all_gate_components_pass']
    assert result['independent_interval_coverage']==pytest.approx(.8)
    assert result['paired_ci_low_pp']>0
    assert result['gate_components']['minimum_absolute_gain']['threshold']==1.
    assert result['gate_components']['minimum_relative_gain']['threshold']==.05
    assert not result['production_promotion']


def test_trivial_gain_and_missing_baseline_do_not_pass():
    group,entry=gate_group()
    group['prediction']=10.8377;group['baseline']=10.838
    result=p.gate_components(group,entry)
    assert result['absolute_gain_pp']==pytest.approx(.003)
    assert result['gate_components']['minimum_absolute_gain']['status']=='FAIL'
    assert not result['point_gate_pass']
    group.loc[0,'baseline']=None
    result=p.gate_components(group,entry)
    assert not result['gate_components']['paired_baseline_availability']['passed']
    assert result['status']=='INSUFFICIENT_PROSPECTIVE_EVIDENCE'


def test_small_calibration_does_not_allow_prediction_interval():
    group,entry=gate_group()
    entry['calibration_effective_n']=2
    result=p.gate_components(group,entry)
    assert result['point_gate_pass']
    assert not result['prediction_interval_gate_pass']
    assert result['gate_components']['calibration_exposure_blocks']['status']=='FAIL'


def test_worst_period_is_reported_and_fails_without_relaxing_threshold():
    group,entry=gate_group()
    group.loc[group.date.dt.year==2026,'prediction']=20.
    result=p.gate_components(group,entry)
    assert result['gate_components']['worst_period']['observed']>2.
    assert result['gate_components']['worst_period']['status']=='FAIL'
    assert not result['point_gate_pass']
