"""월간 실적을 '온라인 홍보활동 보고서' 양식에 채워 넣는다. .venv 로 실행할 것.

양식(/Volumes/USB256/온라인 홍보활동 보고서.xlsx)은 구분·분류별로 몇 줄씩만 비워 둔
서식이다. 한 달 실적은 그보다 훨씬 많으므로, 각 구간을 필요한 만큼 늘려 쓰고
머리글·서명란·테두리·인쇄설정은 양식 그대로 둔다.

양식의 분류 ← 우리 수집 데이터
  홈페이지 공지사항      ← 학과공지 + 채용정보 및 자료
  홈페이지 학과소식      ← 포토갤러리
  유튜브 영상(long-form) ← 60초 초과
  유튜브 Shorts          ← 60초 이하
  인스타 게시물          ← 이미지·카드뉴스
  인스타 릴스            ← 숏츠·영상
  블로그                 ← 네이버 블로그
  기타                   ← 블로거(blogspot)
  페이스북               ← 운영하지 않아 비워 둔다

사용: python build_promo_report.py [YYYY-MM] [출력경로]
"""
import os
import shutil
import sys
from calendar import monthrange
from copy import copy
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from analytics.common import OUT_DIR, load_part, log  # noqa: E402
from analytics.build_report import merge  # noqa: E402
from analytics.build_monthly import prev_month  # noqa: E402

from openpyxl import load_workbook  # noqa: E402
from openpyxl.styles import Alignment, Font  # noqa: E402

TEMPLATE = "/Volumes/USB256/온라인 홍보활동 보고서.xlsx"
DEPT = "재난안전학과"
HEAD_ROW = 6            # 구분/분류/내용/업로드일자/비고
FIRST_ROW = 7           # 데이터 시작
LAST_ROW = 29           # 양식의 마지막 데이터 행(기타)


def sections(rows, ym):
    """양식 순서대로 (구분, 분류, 항목들). 항목은 (내용, 업로드일자, 링크)."""
    cur = [r for r in rows if r["date"][:7] == ym]

    # 블로거(blogspot)는 주간·월간 리포트의 4개 매체에 들어 있지 않아 따로 읽는다.
    blogger = [x for x in (load_part("blogger") or {}).get("items", [])
               if x["date"][:7] == ym]
    blogger = [(x["title"] or "(제목 없음)", x["date"], x.get("url", ""))
               for x in sorted(blogger, key=lambda a: a["date"])]

    def pick(media, types=None, sources=None):
        out = []
        for r in sorted(cur, key=lambda x: x["date"]):
            if r["media"] != media:
                continue
            if types and r["type"] not in types:
                continue
            if sources and r.get("source") not in sources:
                continue
            out.append((r["title"] or "(제목 없음)", r["date"], r.get("url", "")))
        return out

    return [
        ("홈페이지", "공지사항", pick("학과 홈페이지", sources=("학과공지", "채용정보 및 자료"))),
        ("홈페이지", "학과소식\n(갤러리 등)", pick("학과 홈페이지", sources=("포토갤러리",))),
        ("유튜브", "영상\n(long-form)", pick("유튜브", types=("영상",))),
        ("유튜브", "Shorts", pick("유튜브", types=("숏츠",))),
        ("인스타", "게시물", pick("인스타그램", types=("이미지", "카드뉴스"))),
        ("인스타", "릴스", pick("인스타그램", types=("숏츠", "영상"))),
        ("페이스북", None, []),
        ("블로그", None, pick("네이버 블로그")),
        ("기타", None, blogger),
    ]


def build(rows, ym, out_path):
    shutil.copy(TEMPLATE, out_path)
    wb = load_workbook(out_path)
    ws = wb.active

    # 서식 견본을 먼저 떠 둔다(행을 지우기 전에).
    sample = {c: copy(ws[f"{c}{FIRST_ROW}"]._style) for c in "ABCDE"}
    last_style = {c: copy(ws[f"{c}{LAST_ROW}"]._style) for c in "ABCDE"}
    row_h = ws.row_dimensions[FIRST_ROW].height

    secs = sections(rows, ym)
    for rng in list(ws.merged_cells.ranges):
        if rng.min_row >= FIRST_ROW:
            ws.unmerge_cells(str(rng))
    for r in range(FIRST_ROW, LAST_ROW + 1):
        for c in "ABCDE":
            ws[f"{c}{r}"].value = None

    need = sum(max(len(items), 1) for _, _, items in secs)
    have = LAST_ROW - FIRST_ROW + 1
    if need > have:
        ws.insert_rows(LAST_ROW, need - have)

    row = FIRST_ROW
    counts = {}
    for gubun, bunryu, items in secs:
        n = max(len(items), 1)
        counts[gubun] = counts.get(gubun, 0) + len(items)
        for i in range(n):
            for c in "ABCDE":
                ws[f"{c}{row + i}"]._style = copy(sample[c])
            ws.row_dimensions[row + i].height = row_h
            if i < len(items):
                content, date, url = items[i]
                ws[f"C{row + i}"] = content
                ws[f"D{row + i}"] = date.replace("-", ".") + "."
                if url:
                    cell = ws[f"E{row + i}"]
                    cell.value = url
                    cell.hyperlink = url
                    cell.font = copy(cell.font)
                    cell.font = Font(name=cell.font.name, size=9, color="FF0563C1", underline="single")
                    cell.alignment = Alignment(horizontal="left", vertical="center")
        ws[f"A{row}"] = gubun          # 건수는 아래에서 총계를 알고 난 뒤 채운다
        if bunryu:
            ws[f"B{row}"] = bunryu
        else:
            ws.merge_cells(start_row=row, start_column=1, end_row=row + n - 1, end_column=2)
        row += n
    end_row = row - 1

    # 구분 묶음(홈페이지 8행 등)을 다시 병합하고 '(총 n건)' 을 채운다.
    row = FIRST_ROW
    i = 0
    while i < len(secs):
        gubun = secs[i][0]
        block = [s for s in secs if s[0] == gubun]
        span = sum(max(len(s[2]), 1) for s in block)
        if secs[i][1]:                                  # 분류가 있는 구분: A 만 병합
            ws.merge_cells(start_row=row, start_column=1, end_row=row + span - 1, end_column=1)
            sub = row
            for _, bunryu, items in block:
                h = max(len(items), 1)
                if h > 1:
                    ws.merge_cells(start_row=sub, start_column=2, end_row=sub + h - 1, end_column=2)
                sub += h
        ws[f"A{row}"] = f"{gubun}\n(총 {counts.get(gubun, 0)}건)"
        row += span
        i += len(block)

    y, m = int(ym[:4]), int(ym[5:])
    last_day = monthrange(y, m)[1]
    ws["A1"] = f"[{DEPT}] 온라인 홍보활동 보고서 ({y}.{m:02d}.01. - {m:02d}.{last_day:02d}.)"
    ws.column_dimensions["E"].width = 46   # 링크가 잘리지 않게
    ws.print_area = f"A1:E{end_row}"
    wb.save(out_path)
    total = sum(counts.values())
    return {"path": out_path, "total": total, "counts": counts, "rows": end_row}


if __name__ == "__main__":
    ym = sys.argv[1] if len(sys.argv) > 1 and "-" in sys.argv[1] else prev_month(
        datetime.now().strftime("%Y-%m-%d"))
    out = sys.argv[2] if len(sys.argv) > 2 else os.path.join(
        OUT_DIR, f"[{DEPT}] 온라인 홍보활동 보고서 {ym}.xlsx")
    rows, channel, profile, warn = merge()
    info = build(rows, ym, out)
    log(f"홍보활동 보고서: {ym} 총 {info['total']}건 → {os.path.basename(out)} "
        f"({', '.join(f'{k} {v}' for k, v in info['counts'].items() if v)})")
    print(out)
