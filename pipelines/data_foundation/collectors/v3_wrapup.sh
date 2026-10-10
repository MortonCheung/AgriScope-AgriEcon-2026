#!/bin/bash
cd "$(cd "$(dirname "$0")" && pwd)/../../.." || exit 1
RS=data/raw/decision_engine_supplement_v3/remote_sensing
REF=city_data/reference/decision_engine_supplement_v3
LOG=$RS/wrapup.log
echo "[$(date +%H:%M:%S)] wrapup start" > $LOG

# 等 NDVI 补跑结束（最多 ~20 分钟）
for i in $(seq 1 40); do
  [ "$(pgrep -f 'AgriScope/pipelines/data_foundation/collectors/v3_remote_sensing_ndvi.py' | wc -l)" -eq 0 ] && break
  sleep 30
done
echo "[$(date +%H:%M:%S)] NDVI procs=$(pgrep -f 'AgriScope/pipelines/data_foundation/collectors/v3_remote_sensing_ndvi.py'|wc -l) cache=$(ls $RS/cache/*.json 2>/dev/null|wc -l)" >> $LOG

# 等 EVI 结束（最多再 ~25 分钟）
for i in $(seq 1 50); do
  [ "$(pgrep -f v3_s2_evi_backfill | wc -l)" -eq 0 ] && break
  sleep 30
done
echo "[$(date +%H:%M:%S)] EVI procs=$(pgrep -f v3_s2_evi_backfill|wc -l) evi_cache=$(ls $RS/evi_cache/*.json 2>/dev/null|wc -l)" >> $LOG

# 清理分片中间文件
rm -f $REF/remote_sensing_ndvi_city_monthly_*of2.csv
# 合并 + 派生 + QC
python3 -u tools/collectors/v3_rs_merge_anomaly.py >> $LOG 2>&1
python3 -u tools/collectors/v3_model_value.py >> $LOG 2>&1
python3 -u tools/collectors/v3_qc.py >> $LOG 2>&1
echo "[$(date +%H:%M:%S)] WRAPUP DONE" >> $LOG
touch /tmp/v3_done2.marker
