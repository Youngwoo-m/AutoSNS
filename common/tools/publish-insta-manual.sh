#!/bin/bash
# insta-manual 폴더만 떼어내 공개 GitHub 저장소로 올린다.
#
# 작업은 계속 AutoSNS/channels/insta-manual 에서 하고, 공개할 때만 이걸 돌린다.
# subtree split 이 그 폴더의 커밋만 뽑아 별도 이력을 만들어 준다.
#
#   사용법:  ./tools/publish-insta-manual.sh
#   최초 1회는 gh auth login 과 저장소 생성이 먼저 필요하다(README 참고).
set -euo pipefail
cd -P "$(dirname "$0")/../.."

REPO="${INSTA_MANUAL_REPO:-}"
if [ -z "$REPO" ]; then
  REPO=$(git config --get remote.insta-manual.url || true)
fi
if [ -z "$REPO" ]; then
  echo "공개 저장소 주소를 모릅니다. 아래 중 하나로 알려주세요:"
  echo "  git remote add insta-manual https://github.com/<계정>/<저장소>.git"
  echo "  INSTA_MANUAL_REPO=https://github.com/<계정>/<저장소>.git $0"
  exit 1
fi

# 커밋 안 된 변경이 있으면 먼저 알려준다(그건 올라가지 않는다)
if ! git diff --quiet -- channels/insta-manual || ! git diff --cached --quiet -- channels/insta-manual; then
  echo "⚠️  insta-manual 에 커밋되지 않은 변경이 있습니다. 먼저 커밋하세요."
  git status --short channels/insta-manual
  exit 1
fi

echo "insta-manual 이력 분리 중..."
git branch -D insta-manual-public 2>/dev/null || true
git subtree split --prefix=channels/insta-manual -b insta-manual-public >/dev/null

echo "올라갈 파일:"
git ls-tree -r --name-only insta-manual-public | sed 's/^/  /'

echo "푸시: $REPO (main)"
git push "$REPO" insta-manual-public:main
echo "완료."
