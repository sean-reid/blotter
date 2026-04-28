#!/bin/bash
# Track GPU/CPU/memory usage
GPU_UTIL=$(nvidia-smi --query-gpu=utilization.gpu --format=csv,noheader,nounits 2>/dev/null | head -1 || echo 0)
GPU_MEM=$(nvidia-smi --query-gpu=memory.used --format=csv,noheader,nounits 2>/dev/null | head -1 || echo 0)
MEM_USED_PCT=$(free | awk '/Mem:/{printf("%.0f", $3/$2*100)}')
LOAD_1M=$(awk '{print $1}' /proc/loadavg)

clickhouse-client -q \
  "INSERT INTO blotter.pipeline_metrics (metric, value) VALUES
   ('gpu.utilization_pct', ${GPU_UTIL:-0}),
   ('gpu.memory_used_mb', ${GPU_MEM:-0}),
   ('system.memory_used_pct', ${MEM_USED_PCT:-0}),
   ('system.load_1m', ${LOAD_1M:-0})" 2>/dev/null
