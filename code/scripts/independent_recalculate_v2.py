#!/usr/bin/env python3
"""不调用模型研究metrics函数，独立复算全部分组误差与样本/标签清洗证据。"""
import json
from pathlib import Path
import numpy as np
import pandas as pd
ROOT=Path(__file__).resolve().parents[1]


def main():
    p=pd.read_parquet(ROOT/'pipelines/long_horizon/artifacts/v2/predictions.parquet')
    m=pd.read_csv(ROOT.parent/'data/research/long_horizon/LONG_HORIZON_V2_METRICS.csv')
    protocol=json.loads((ROOT/'pipelines/long_horizon/evaluation_protocol_v2.json').read_text())
    phases={q['name']:q for q in protocol['config']['phases']}
    cols=['crop','horizon','target_type','method','phase']
    recalculated=[]
    for key,g in p.groupby(cols):
        a=g.actual.to_numpy(float);f=g.prediction.to_numpy(float);c=g.anchor_price.to_numpy(float)
        ok=np.isfinite(a)&np.isfinite(f);a,f,c=a[ok],f[ok],c[ok]
        recalculated.append(dict(zip(cols,key),n=len(a),WAPE=100*np.sum(abs(f-a))/np.sum(abs(a)),
            MAE=float(np.mean(abs(f-a))),sMAPE=100*float(np.mean(2*abs(f-a)/(abs(f)+abs(a)))),
            bias=float(np.mean(f-a)),direction_accuracy=float(np.mean(np.sign(f-c)==np.sign(a-c)))))
    r=pd.DataFrame(recalculated)
    joined=m.merge(r,on=cols,suffixes=('_reported','_recomputed'),validate='one_to_one')
    diffs={k:float(np.max(np.abs(joined[k+'_reported']-joined[k+'_recomputed']))) for k in
           ['n','WAPE','MAE','sMAPE','bias','direction_accuracy']}
    assert len(joined)==len(m)==len(r)
    assert all(v < 1e-8 for v in diffs.values()),diffs
    for phase,g in p.groupby('phase'):
        conf=phases[phase]
        assert (pd.to_datetime(g.label_end)<=pd.Timestamp(conf['end'])).all()
        assert (pd.to_datetime(g.date)>=pd.Timestamp(conf['start'])).all()
    for row in m.itertuples():
        assert pd.Timestamp(row.max_training_label_end)<=pd.Timestamp(phases[row.phase]['train_end'])
    out={'status':'INDEPENDENT_RECALCULATION_PASS','prediction_rows':len(p),'metric_groups':len(m),
         'max_absolute_discrepancy':diffs,'label_maturity_and_phase_end_checks':'PASS',
         'untouched_claim':'NONE; historical periods previously viewed'}
    out_path = ROOT / 'runtime' / 'RC2_INDEPENDENT_RECALCULATION.json'
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(out,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps(out,ensure_ascii=False))


if __name__=='__main__':
    main()
