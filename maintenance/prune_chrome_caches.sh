#!/bin/bash
# AutoSNS chrome-profile 캐시 정리 — 로그인 세션은 보존, 재생성되는 캐시만 삭제.
# launchd(com.smuds.cacheprune.daily)가 매일 새벽 호출. 수동 실행도 가능.
# 안전장치: 해당 프로필을 점유한 프로세스가 있으면 그 프로필은 건너뛴다(손상 방지).
set -u
ROOT="$HOME/devAPP/AutoSNS"
LOG_DIR="$ROOT/maintenance/logs"; mkdir -p "$LOG_DIR"
LOG="$LOG_DIR/prune.log"
ts() { date '+%Y-%m-%d %H:%M:%S'; }

# 삭제 대상 폴더명(캐시성, 재생성됨). 로그인/세션(Cookies, Login Data, Local Storage,
# Preferences, Sessions, Network)은 목록에 없어 보존된다.
PRUNE_NAMES=(
  "Cache" "Code Cache" "GPUCache" "DawnCache" "DawnWebGPUCache" "DawnGraphiteCache"
  "GraphiteDawnCache" "ShaderCache" "component_crx_cache" "optimization_guide_model_store"
  "WasmTtsEngine" "OptimizationHints" "optimization_guide_prediction_model_downloads"
)

freed_before=$(df -k / | awk 'NR==2{print $4}')
echo "[$(ts)] prune 시작" >> "$LOG"

# 각 chrome-profile* 디렉터리 순회
find "$ROOT" -maxdepth 2 -type d -name "chrome-profile*" 2>/dev/null | while IFS= read -r prof; do
  # 프로필 점유 확인: 이 경로를 연 프로세스가 있으면 스킵
  if pgrep -f -- "$prof" >/dev/null 2>&1; then
    echo "[$(ts)] SKIP(사용중): $prof" >> "$LOG"; continue
  fi
  for name in "${PRUNE_NAMES[@]}"; do
    find "$prof" -type d -name "$name" -prune 2>/dev/null | while IFS= read -r d; do
      sz=$(du -sk "$d" 2>/dev/null | awk '{print $1}')
      rm -rf "$d" 2>/dev/null && echo "[$(ts)] del ${sz}KB: ${d#$ROOT/}" >> "$LOG"
    done
  done
done

freed_after=$(df -k / | awk 'NR==2{print $4}')
diff_mb=$(( (freed_after - freed_before) / 1024 ))
echo "[$(ts)] prune 완료 — 약 ${diff_mb}MB 확보 (여유 $((freed_after/1024/1024))GB)" >> "$LOG"
