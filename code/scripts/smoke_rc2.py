#!/usr/bin/env python3
"""对真实 HTTP API 做只读推理 smoke，不训练、不修改快照。"""
import argparse
import json
import urllib.request


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--base-url', default='http://127.0.0.1:8787')
    base = ap.parse_args().base_url.rstrip('/')
    def call(path, body=None):
        req = urllib.request.Request(base + path, data=None if body is None else json.dumps(body).encode(),
                                     headers={'Content-Type': 'application/json'})
        with urllib.request.urlopen(req, timeout=90) as response:
            assert response.status == 200
            return json.load(response)
    call('/health/ready')
    daily = call('/api/daily/latest?city=shenyang')
    cap = call('/api/forecast/capabilities?city=shenyang')
    assert cap['supported']
    for h in [30, 60, 90, 120, 150, 180]:
        f = call('/api/forecast/long-horizon', {'city_id': 'shenyang', 'crop': '土豆', 'horizon_days': h})
        assert set(f['targets']) == {'cycle_market_average', 'harvest_market_price'}
        assert f['targets']['harvest_market_price']['target_type'] == 'harvest_market_price'
    payload = {'contract_version': '2', 'user_context': {'city_id': 'shenyang', 'area_mu': 10,
        'budget_cny': 100000, 'risk_preference': 'balanced', 'crop_preferences': ['土豆', '西红柿'],
        'actual_inputs': {}, 'market_context': {'expected_harvest_horizon_days': 120}},
        'input_source': {'kind': 'structured'}}
    d = call('/api/decision/long-horizon', payload)
    assert d['basis'] == 'harvest_market_price'
    assert d['request'] == payload
    print(json.dumps({'status': 'HTTP_SMOKE_PASS', 'horizons': 6, 'daily_latest': daily['latest_data_date'],
                      'long_horizon_as_of': cap['as_of'], 'long_decision': d.get('status')}, ensure_ascii=False))


if __name__ == '__main__':
    main()
