#!/bin/bash
# AX 오케스트레이터: 잠금(같은 크롬 프로필·한도를 쓰는 작업은 차례로)·비상 정지를 거쳐 다시 실행한다 — shared/axlock.py
[ -z "$AX_LOCKED" ] && exec /usr/bin/python3 /Volumes/USB256/devAPP/AutoSNS/shared/axlock.py run --job cacheprune.daily -- "$0" "$@"
# AutoSNS chrome-profile 캐시 정리 — 로그인 세션은 보존, 재생성되는 캐시만 삭제.
# launchd(com.smuds.cacheprune.daily)가 매일 새벽 호출. 수동 실행도 가능.
# 안전장치: 해당 프로필을 점유한 프로세스가 있으면 그 프로필은 건너뛴다(손상 방지).
set -u
# 이 스크립트가 놓인 곳을 기준으로 잡는다. 전에는 "$HOME/devAPP/AutoSNS" 로 박혀
# 있었는데, 2026-09-21 에 같은 이름의 빈 디렉터리가 홈에 생기면서 그쪽을 보게 됐다.
# chrome-profile 이 하나도 없으니 조용히 0건으로 끝났다(9/20 로그 "약 0MB 확보").
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
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

# 지우는 볼륨을 잰다. 전에는 df -k / 로 내장 디스크를 재서, USB 에서 지워 놓고
# "여유 0GB" 를 찍었다.
freed_before=$(df -k "$ROOT" | awk 'NR==2{print $4}')
echo "[$(ts)] prune 시작 — $ROOT" >> "$LOG"

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

freed_after=$(df -k "$ROOT" | awk 'NR==2{print $4}')
diff_mb=$(( (freed_after - freed_before) / 1024 ))
echo "[$(ts)] prune 완료 — 약 ${diff_mb}MB 확보 (여유 $((freed_after/1024/1024))GB)" >> "$LOG"
