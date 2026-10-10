# -*- coding: utf-8 -*-
"""农业农村部「重点农产品市场信息平台」批发市场当日价格采集器
站点: https://ncpscxx.moa.gov.cn
接口: POST /product/homeWholesalePrice/selectWholesalePriceChart?varietyCode=&marketNames=&provinceNames=
鉴权: 无登录要求；响应体为 AES-256-CBC 加密（密钥硬编码于前端 app.js），此处按前端同构解密。
注意: 该接口只返回**当日**跨市场快照（x=市场名, y=价格 元/公斤），无历史查询参数；
      历史序列需自行每日留档累积，不能回填 2021-2026。
"""
import json, base64, subprocess, time, sys, os
from urllib.parse import quote
from Crypto.Cipher import AES
KEY = b"7s9K$pG2xQ8zR5mB7vA3sD9fH2jW40cV"
BASE = 'https://ncpscxx.moa.gov.cn'
UA = 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 Chrome/131.0.0.0 Safari/537.36'

def _curl(url, method='POST'):
    args=['curl','-s','--max-time','40','-X',method,url,
          '-H','Content-Type: application/json',
          '-H','Origin: '+BASE, '-H','Referer: '+BASE+'/','-H','User-Agent: '+UA]
    for _ in range(3):
        out=subprocess.run(args,capture_output=True,env={'PATH':'/usr/bin:/bin'}).stdout.decode('utf-8','ignore').strip()
        try: return json.loads(out)
        except Exception: time.sleep(2)
    return {}

def decrypt(e):
    iv=e[:16].encode('utf-8'); ct=base64.b64decode(e[16:])
    pt=AES.new(KEY,AES.MODE_CBC,iv).decrypt(ct)
    return pt[:-pt[-1]].decode('utf-8')

def select_tree():
    return _curl(BASE+'/product/homeWholesaleProduct/selectTree').get('data') or []

def province_markets():
    d=_curl(BASE+'/product/homeWholesalePrice/proAndMarket').get('data') or []
    for p in d:
        if p['province'].startswith('辽宁'): return p['children']
    return []

def wholesale_price(variety_code, province='辽宁省', markets=''):
    url=(BASE+'/product/homeWholesalePrice/selectWholesalePriceChart'
         f'?varietyCode={quote(str(variety_code))}&marketNames={quote(str(markets))}'
         f'&provinceNames={quote(str(province))}')
    r=_curl(url)
    if isinstance(r.get('data'),str):
        try: return json.loads(decrypt(r['data']))
        except Exception: return None
    return None

def flatten(tree):
    out=[]
    def walk(n):
        for c in n:
            if c.get('children'): walk(c['children'])
            elif c.get('id'): out.append((c['label'], c['id']))
    walk(tree); return out

if __name__=='__main__':
    os.makedirs('data/raw/market_price_moa',exist_ok=True)
    mk=province_markets()
    print('辽宁省批发市场:', len(mk)-1)
    json.dump(mk, open('data/raw/market_price_moa/liaoning_markets.json','w'), ensure_ascii=False, indent=1)
    tree=select_tree(); leaves=flatten(tree)
    print('品种叶子数:', len(leaves))
    json.dump(leaves, open('data/raw/market_price_moa/variety_tree_leaves.json','w'), ensure_ascii=False, indent=1)
    KEYV=['玉米','粳米(普通)','大豆','大白菜','土豆','黄瓜','西红柿','茄子','芹菜','苹果','葡萄','梨',
          '花生仁','油菜籽','油菜','菠菜','韭菜','胡萝卜','白萝卜','甘蓝','菜花','葱','生姜','大蒜',
          '猪肉(白条猪)','鸡蛋','鲤鱼','草鱼','面粉']
    want={}
    for lbl,cid in leaves:
        if lbl in KEYV and lbl not in want: want[lbl]=cid
    recs=[]
    for lbl,cid in want.items():
        j=wholesale_price(cid)
        if not j: print('  --',lbl,cid,'无数据'); time.sleep(1); continue
        dt=j.get('date'); xs=j.get('x') or []; ys=j.get('y') or []
        for m,v in zip(xs,ys):
            recs.append(dict(date=dt, variety=lbl, variety_code=cid, market=m, price=v, unit='元/公斤'))
        print(f'  OK {lbl:12s} {dt} 市场数={len(xs)}')
        time.sleep(1.2)
    if recs:
        import pandas as pd
        df=pd.DataFrame(recs)
        df['province']='辽宁省'; df['source']='农业农村部重点农产品市场信息平台 ncpscxx.moa.gov.cn'
        df['source_url']=BASE+'/product/homeWholesalePrice/selectWholesalePriceChart'
        df['data_layer']='official_market_spot_price'
        df.to_csv('data/raw/market_price_moa/moa_liaoning_market_spot.csv',index=False,encoding='utf-8-sig')
        print('\n落盘 data/raw/market_price_moa/moa_liaoning_market_spot.csv :',len(df),'行')
        print(df.groupby('variety').size().to_string())
