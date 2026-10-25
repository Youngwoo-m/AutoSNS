#!/bin/bash
# render.sh 장면.py 장면이름 [fps=10] [폭=600] [색수=32]  → samples/장면이름.gif (2MB 이하 점검)
# 필요: 전역 manim(uv tool install manim), TeX(BasicTeX + standalone·preview 등), dvisvgm, ffmpeg
set -e
export PATH="$HOME/.local/bin:/Library/TeX/texbin:/usr/local/bin:$PATH"
cd "$(dirname "$0")"
OUT=samples; mkdir -p $OUT _media
manim -qm -o "$2" --media_dir _media "$1" "$2"
V=$(find _media -name "$2.mp4" | head -1)
ffmpeg -v error -y -i "$V" -vf "fps=${3:-10},scale=${4:-600}:-1:flags=lanczos,split[a][b];[a]palettegen=max_colors=${5:-32}[p];[b][p]paletteuse=dither=none:diff_mode=rectangle" "$OUT/$2.gif"
SIZE=$(stat -f%z "$OUT/$2.gif"); echo "$OUT/$2.gif ${SIZE} bytes"
[ "$SIZE" -gt 2000000 ] && echo "⚠️ 2MB 초과 — fps·폭·색수를 줄이세요" || true
