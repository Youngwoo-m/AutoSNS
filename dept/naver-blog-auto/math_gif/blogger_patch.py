"""이미 올린 블로거 글에 수식 이미지·Manim GIF 조각을 끼워 넣는다(--go 없으면 위치만 보여 준다).
    ./.venv/bin/python math_gif/blogger_patch.py [--go]
같은 글에 두 번 넣지 않는다(본문에 math/ 경로가 있으면 건너뜀). 원본 본문은 backup/ 에 저장한다.
"""
import argparse, json, os, sys, time
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
import geoai_blogger  # noqa: E402
from common import load_config, log  # noqa: E402
from post_draft import figure, upload_raw  # noqa: E402

S = os.path.join(HERE, "samples")
# (글 id, 끼울 위치 앞의 마커, 파일 접두, GIF 파일, 수식 PNG, GIF alt·캡션, 수식 alt·캡션)
JOBS = [
    ("6440350485774183902", "<h3>Ⅳ. 현장 품질관리", "compaction", "GCompaction.gif", "blogger_compaction_formula.png",
     ("건조밀도 식과 다짐도 계산을 한 줄씩 전개하는 도식", "도식: 건조밀도에서 다짐도 94.7%까지의 계산 순서"),
     ("ρd = ρ/(1+w), Rc(%) = ρd/ρd,max × 100", "다짐도 산정 공식")),
    ("3407895417652989301", "<h3>4. 계산 예", "spt", "GSPT.gif", "blogger_spt_formula.png",
     ("측정 N 18이 에너지 보정 24.0, 상재압 보정 29.6으로 이어지는 도식", "도식: 측정 N에서 (N1)60 까지의 보정 순서"),
     ("N60 = (ER/60%)·N, (N1)60 = CN·N60, CN = 0.77·log10(20/σ′v), N′ = 15 + ½(N−15)", "SPT N값 보정식")),
    ("7029565164290135606", "<h3>5. 제어방법", "thermal", "GThermal.gif", "blogger_thermal_formula.png",
     ("온도균열지수 정의식과 간이식으로 ΔT 12℃일 때 1.25, 목표 1.5의 ΔT 10℃를 구하는 도식", "도식: 온도균열지수 정의·간이식과 계산 예"),
     ("Icr = fsp(t)/σt(t), Icr = 15/ΔT, ΔTi ≤ 15/1.5 = 10℃", "온도균열지수 공식")),
    ("1244330485690819869", '<h3 data-ke-size="size23">Ⅴ. 시험·해석 시 유의사항', "pile", "GPile.gif", "blogger_pile_formula.png",
     ("Davisson 한계 침하량 식에 단면적과 하중 2,500·3,000 kN을 넣어 계산하는 도식", "도식: Davisson 한계선 침하량 계산 순서"),
     ("slim = QL/AE + (4 + D/120) [mm], A = π/4(D² − d²)", "Davisson 한계 침하량 공식")),
]

ap = argparse.ArgumentParser(); ap.add_argument("--go", action="store_true"); a = ap.parse_args()
cfg = load_config(); svc = geoai_blogger.service(); bid = geoai_blogger.blog_id(cfg)
os.makedirs(os.path.join(HERE, "backup"), exist_ok=True)
for pid, marker, name, gif, png, (ga, gc), (pa, pc) in JOBS:
    p = svc.posts().get(blogId=bid, postId=pid).execute()
    c = p["content"]
    if "geoai-assets" in c and f"math/20261023_{name}" in c:
        print(pid, "이미 넣음 — 건너뜀"); continue
    if c.count(marker) != 1:
        print(pid, "마커 위치 불확실:", marker, c.count(marker)); continue
    print(pid, p["title"][:30], "→", marker, "앞에 삽입", "(실행)" if a.go else "(미리보기)")
    if not a.go:
        continue
    with open(os.path.join(HERE, "backup", f"{pid}_{int(time.time())}.html"), "w") as f:
        f.write(c)
    gu = upload_raw(os.path.join(S, gif), f"math/20261023_{name}.gif", cfg)
    pu = upload_raw(os.path.join(S, png), f"math/20261023_{name}_formula.png", cfg)
    frag = figure(pu, pa, pc) + figure(gu, ga, gc)
    svc.posts().patch(blogId=bid, postId=pid, body={"content": c.replace(marker, frag + marker)}).execute()
    log(f"블로거 수식 삽입: {pid} {gu}")
    print("  완료", p["url"])
