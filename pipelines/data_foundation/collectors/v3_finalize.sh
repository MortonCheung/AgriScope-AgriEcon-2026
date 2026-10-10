#!/bin/bash
# Decision Engine V3 收尾编排：等 NDVI → 补空 → 合并派生 → EVI 终pass → QC
cd "$(cd "$(dirname "$0")" && pwd)/../../.." || exit 1
export GDAL_HTTP_TIMEOUT=30 GDAL_HTTP_CONNECTTIMEOUT=10 GDAL_HTTP_MAX_RETRY=3
export GDAL_DISABLE_READDIR_ON_OPEN=EMPTY_DIR
RS=data/raw/decision_engine_supplement_v3/remote_sensing
LOG=$RS/finalize.log
echo "[$(date +%H:%M:%S)] 等待 NDVI 进程结束..." >> $LOG
while [ "$(pgrep -f 'AgriScope/pipelines/data_foundation/collectors/v3_remote_sensing_ndvi.py' | wc -l)" -gt 0 ]; do sleep 60; done
echo "[$(date +%H:%M:%S)] NDVI 进程结束，cache=$(ls $RS/cache/*.json 2>/dev/null|wc -l)" >> $LOG

# 1) 清理 null 缓存并补漏
for f in $RS/cache/*.json; do [ "$(cat "$f")" = "null" ] && rm -f "$f"; done
echo "[$(date +%H:%M:%S)] 清理后 cache=$(ls $RS/cache/*.json 2>/dev/null|wc -l)，补漏重跑..." >> $LOG
python3 -u tools/collectors/v3_remote_sensing_ndvi.py >> $LOG 2>&1
echo "[$(date +%H:%M:%S)] 补漏后 cache=$(ls $RS/cache/*.json 2>/dev/null|wc -l)" >> $LOG

# 2) 合并 + 派生
python3 -u tools/collectors/v3_rs_merge_anomaly.py >> $LOG 2>&1

# 3) EVI 终 pass（先沈阳，再全城）
echo "[$(date +%H:%M:%S)] EVI 终pass: 沈阳" >> $LOG
python3 -u tools/collectors/v3_s2_evi_backfill.py 沈阳 >> $LOG 2>&1
echo "[$(date +%H:%M:%S)] EVI 终pass: 全城" >> $LOG
python3 -u tools/collectors/v3_s2_evi_backfill.py >> $LOG 2>&1

# 4) QC + 价值分类
python3 -u tools/collectors/v3_model_value.py >> $LOG 2>&1
python3 -u tools/collectors/v3_qc.py >> $LOG 2>&1
echo "[$(date +%H:%M:%S)] ALL FINALIZE DONE" >> $LOG
touch /tmp/v3_finalize.done
