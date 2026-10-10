import sys, json, collections
from pathlib import Path
_ROOT = next(p for p in Path(__file__).resolve().parents if (p / "AgriScope").is_dir() and (p / "data").is_dir())
sys.path.insert(0, str(_ROOT))
from crawler.parser import parse_article

recs = [json.loads(l) for l in open(str(_ROOT / "data/raw/policy/lnnync_history/articles.jsonl"), encoding='utf-8')]
print('样本数:', len(recs))
print('分类:', collections.Counter(r['category_key'] for r in recs))

for key in ['grain_oil', 'vegetable', 'fruit', 'agri_input']:
    sub = [r for r in recs if r['category_key'] == key]
    if not sub:
        print(f'--- {key}: 无样本'); continue
    r = sorted(sub, key=lambda x: x['publication_date'])[-1]
    a = parse_article(r)
    print('=' * 100)
    print(f'### {key} | {a.publication_date} | {a.title}')
    print(f'    状态={a.parse_status} period={a.period_start}~{a.period_end} year={a.year} week={a.week} 记录={len(a.records)}')
    for x in a.records[:16]:
        print(f'    {x.product:7s} var={str(x.product_variant):6s} {x.record_type:13s} {str(x.price):8s} {str(x.original_unit):8s} '
              f'raw={x.location_raw:14s} lvl={x.geo_level:8s} city={str(x.city):5s} county={str(x.county):9s} mom={x.mom_change_pct} yoy={x.yoy_change_pct}')
