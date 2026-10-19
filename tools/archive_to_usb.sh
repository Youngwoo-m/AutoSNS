#!/bin/bash
# 산출물(posts/)을 USB 로 옮긴다 — 내장 디스크가 자꾸 가득 차서 만든 보관 스크립트.
#
# 오늘 만든 파일은 두고, 하루 이상 지난 것만 옮긴다(발행 직후 파일을 건드리지 않기 위함).
# 복사한 뒤 크기를 대조하고, 일치할 때만 원본을 지운다. USB 가 없으면 아무것도 안 한다.
#
#   미리 보기 : ./tools/archive_to_usb.sh
#   실제 이동 : ./tools/archive_to_usb.sh --go
set -u
USB="${USB_DIR:-/Volumes/USB256}"
DEST="$USB/AutoSNS_archive"
GO=0; [ "${1:-}" = "--go" ] && GO=1
cd "$(dirname "$0")/.." || exit 1

if [ ! -d "$USB" ]; then
  echo "USB 가 연결돼 있지 않습니다: $USB" >&2
  exit 1
fi

total=0; moved=0
for proj in naver-blog-auto insta-cardnews youtube-shorts-auto; do
  src="$proj/posts"
  [ -d "$src" ] || continue
  while IFS= read -r f; do
    total=$((total+1))
    rel="${f#$src/}"
    ym=$(date -r "$f" +%Y-%m)
    out="$DEST/$proj/$ym/$rel"
    if [ "$GO" -eq 0 ]; then
      [ "$total" -le 5 ] && echo "[미리보기] $f → $out"
      continue
    fi
    mkdir -p "$(dirname "$out")"
    if cp -p "$f" "$out" 2>/dev/null && [ "$(stat -f%z "$f")" = "$(stat -f%z "$out")" ]; then
      rm -f "$f"; moved=$((moved+1))
    else
      echo "실패(원본 유지): $f" >&2
    fi
  done < <(find "$src" -type f -mtime +0 2>/dev/null)
done

# 빈 폴더 정리
[ "$GO" -eq 1 ] && find naver-blog-auto/posts insta-cardnews/posts youtube-shorts-auto/posts \
  -type d -empty -delete 2>/dev/null

if [ "$GO" -eq 0 ]; then
  echo "대상 $total 개(오늘 파일 제외). 실제로 옮기려면 --go 를 붙이세요."
else
  echo "옮김: $moved/$total 개 → $DEST"
  df -h / | tail -1
fi
