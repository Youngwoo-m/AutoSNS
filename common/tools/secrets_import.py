"""NAME=값 파일에 적은 키를 암호화 저장소(secrets.env.enc)로 옮기고 그 파일을 지운다 (2026-11-06).

    python common\\tools\\secrets_import.py E:\\MacMini\\key\\autosns_keys.env

값은 출력하지 않고 키 이름만 보여 준다. 빈 줄·# 주석·값이 빈 키는 건너뛴다.
옮긴 뒤 파일을 덮어써서 지운다(--keep 이면 남겨 둔다).
"""
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.realpath(__file__))))
sys.path.insert(0, ROOT)
from shared import secret_env  # noqa: E402


def main(argv):
    if not argv:
        print(__doc__)
        return 2
    path = argv[0]
    vals, empty = {}, []
    with open(path, encoding="utf-8-sig") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            k, v = k.strip(), v.strip().strip('"').strip("'")
            (vals.__setitem__(k, v) if v else empty.append(k))
    if vals:
        secret_env.update(vals)
    print("저장한 키:", ", ".join(sorted(vals)) or "없음")
    print("비어 있어 건너뛴 키:", ", ".join(empty) or "없음")
    if "--keep" not in argv:
        size = os.path.getsize(path)
        with open(path, "r+b") as f:          # 내용을 덮어쓴 뒤 지운다
            f.write(b"\0" * size)
        os.remove(path)
        print("입력 파일을 지웠습니다:", path)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
