"""건축·안전 개인 Blogger: 기존 일일 상한·예약 중복을 잠금 안에서 확인한다."""
import argparse
from copy import deepcopy
import datetime
import hashlib
import json
import os
from pathlib import Path
import re
import sys
import time

ROOT = Path(__file__).resolve().parents[2]
LEAF = ROOT / "dept/naver-blog-auto"
EXAMS = {"building-daily": "건축시공기술사", "safety-daily": "건설안전기술사"}
RECOVERY_DATE = "2026-10-31"
RECOVERY_ID = "2026-10-31-building-safety-day1-day2"
RECOVERY_REPLY = "이번 4편만 상한 예외로 발행"
RECOVERY_SLOTS = {(job, day) for job in EXAMS for day in (1, 2)}
RECOVERY_LEDGER = ROOT / "GeoAI_NA/claude-jobs/recovery/2026-10-31/blogger-four-post-exception-ledger.json"


def recovery_authorization(approval_path, job, title, body, today, entries, ledger):
    """사용자가 승인한 그날의 네 원고만 허용한다. 미확정 슬롯은 사용할 수 없다."""
    if not approval_path:
        return None
    approval = json.loads(Path(approval_path).read_text(encoding="utf-8"))
    if (today != RECOVERY_DATE or approval.get("date") != RECOVERY_DATE
            or approval.get("approval_id") != RECOVERY_ID
            or approval.get("user_reply") != RECOVERY_REPLY
            or approval.get("blog_id") != "7628821136256904634"):
        raise ValueError("이번 네 편의 날짜·사용자 승인·개인 블로그가 일치하지 않습니다")
    targets = approval.get("targets", [])
    if (len(targets) != 4
            or {(t.get("job"), t.get("day")) for t in targets} != RECOVERY_SLOTS):
        raise ValueError("예외 대상은 건축·안전 각각 1·2일차 네 편뿐입니다")
    match = re.search(r"\| 하루 한 문제 ([12])일차$", title)
    if not match or not title.startswith("[" + EXAMS[job] + "]"):
        raise ValueError("승인된 종목·일차 제목이 아닙니다")
    day = int(match.group(1))
    target = next(t for t in targets if (t["job"], t["day"]) == (job, day))
    digest = hashlib.sha256(body.encode("utf-8")).hexdigest()
    if target.get("title") != title or target.get("html_sha256") != digest:
        raise ValueError("승인 파일의 정확한 제목·원고 SHA256과 일치하지 않습니다")
    slot = job + ":" + str(day)
    if ledger.get("approval_id") != RECOVERY_ID or not isinstance(ledger.get("attempts"), dict):
        raise ValueError("복구 예외 사용 원장이 올바르지 않습니다")
    if slot in ledger["attempts"]:
        raise ValueError("이미 시도한 예외 대상입니다. 공개·예약 상태를 수동 확인해야 합니다")
    for post in entries:
        if (post.get("title", "").startswith("[" + EXAMS[job] + "]")
                and re.search(r"\| 하루 한 문제 " + str(day) + r"일차$", post.get("title", ""))):
            raise ValueError("같은 종목·일차 글이 이미 공개·예약·초안 목록에 있습니다")
    return {"approval_id": RECOVERY_ID, "slot": slot, "title": title,
            "html_sha256": digest, "date": today,
            "approval_sha256": hashlib.sha256(Path(approval_path).read_bytes()).hexdigest()}


def recovery_ledger():
    if not RECOVERY_LEDGER.exists():
        return {"approval_id": RECOVERY_ID, "attempts": {}}
    return json.loads(RECOVERY_LEDGER.read_text(encoding="utf-8"))


def write_recovery_ledger(ledger):
    """quota 잠금 안에서, 전송에 앞서 예약을 원자 저장한다."""
    RECOVERY_LEDGER.parent.mkdir(parents=True, exist_ok=True)
    temporary = RECOVERY_LEDGER.with_suffix(".tmp")
    with temporary.open("w", encoding="utf-8") as stream:
        json.dump(ledger, stream, ensure_ascii=False, indent=2)
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(temporary, RECOVERY_LEDGER)


def quota_snapshot(entries, cfg, today):
    if any(p.get("status") not in ("LIVE", "DRAFT", "SCHEDULED") for p in entries):
        raise ValueError("글 공개 상태를 확인하지 못했습니다")
    g = cfg.get("geoai") or {}
    extra = g.get("cap_exclude_prefixes") or []
    if not isinstance(extra, list) or any(not isinstance(x, str) or not x for x in extra):
        raise ValueError("상한 제외 설정이 올바르지 않습니다")
    prefixes = tuple(dict.fromkeys(extra + ["NaGeoAI 실제 QGIS 실습", "[토목시공기술사]"]))
    zone = datetime.timezone(datetime.timedelta(hours=9))
    current = []
    for post in entries:
        if post["status"] != "LIVE":
            continue
        date = datetime.datetime.fromisoformat(post["published"].replace("Z", "+00:00"))
        if date.tzinfo is None:
            raise ValueError("글 발행 시각에 시간대가 없습니다")
        if date.astimezone(zone).date().isoformat() == today:
            current.append(post)
    counted = [p for p in current if not p.get("title", "").startswith(prefixes)]
    return {"cap": max(int(g.get("posts_per_day", 1)), 1), "counted": len(counted),
            "counted_titles": [p.get("title") for p in counted], "excluded_prefixes": list(prefixes)}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--job", choices=EXAMS, required=True)
    parser.add_argument("--html", required=True)
    parser.add_argument("--title", required=True)
    parser.add_argument("--labels", default="")
    parser.add_argument("--recovery-approval", help="2026-10-31 승인된 건축·안전 1·2일차 네 편의 제목·원고 해시 파일")
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--dry", action="store_true")
    mode.add_argument("--go", action="store_true")
    args = parser.parse_args()
    if not args.title.startswith("[" + EXAMS[args.job] + "]"):
        parser.error("기술사와 제목이 일치하지 않습니다")
    if os.environ.get("AX_LOCKED") != "1":
        os.execv(sys.executable, [sys.executable, str(ROOT / "shared/axlock.py"), "run", "--job",
                                 "engineer-blogger." + args.job, "--", sys.executable,
                                 str(Path(__file__).resolve()), *sys.argv[1:]])
    sys.path.insert(0, str(ROOT))
    sys.path.insert(0, str(LEAF))
    import geoai_blogger as gb
    from shared.axlock import hold, stopped
    os.environ["TZ"] = "Asia/Seoul"
    time.tzset()
    body = Path(args.html).read_text(encoding="utf-8")
    if re.search(r'(src|href)="(?!https?://)[^"#]', body):
        raise ValueError("Blogger 원고에는 공개 HTTP(S) 주소만 사용해야 합니다")
    cfg = deepcopy(gb.load_config())
    if gb.blog_id(cfg) != "7628821136256904634":
        raise ValueError("개인 Blogger 계정이 일치하지 않습니다")
    forbidden = {"세명대학교", "재난안전학과", "#세명대학교", "#재난안전학과"}
    for section in (cfg, cfg.setdefault("geoai", {})):
        if section.get("local_tags"):
            section["local_tags"] = [x for x in section["local_tags"] if x not in forbidden]
    labels = [EXAMS[args.job]] + [x.strip() for x in args.labels.split(",") if x.strip() and x.strip() not in forbidden]
    with hold(["quota:blogger-personal"], job="engineer-blogger:" + args.job, wait=2400):
        if stopped():
            result = {"status": "blocked", "reason": "emergency_stop"}
        else:
            service = gb.service()
            entries, token = [], None
            while True:
                data = service.posts().list(blogId=gb.blog_id(cfg), view="ADMIN", fetchBodies=False, maxResults=100,
                                            status=["LIVE", "DRAFT", "SCHEDULED"], pageToken=token,
                                            fields="items(id,title,status,url,published),nextPageToken").execute()
                entries.extend(data.get("items", []))
                token = data.get("nextPageToken")
                if not token:
                    break
            duplicate = next((p for p in entries if p.get("title", "").strip() == args.title.strip()), None)
            today = datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=9))).date().isoformat()
            quota = quota_snapshot(entries, cfg, today)
            ledger = recovery_ledger() if args.recovery_approval else None
            recovery = None
            if not duplicate and args.recovery_approval:
                recovery = recovery_authorization(args.recovery_approval, args.job, args.title, body,
                                                  today, entries, ledger)
            if duplicate:
                result = {"status": "duplicate", "url": duplicate.get("url", ""), "existing_status": duplicate["status"]}
            elif quota["counted"] >= quota["cap"] and not recovery:
                result = {"status": "blocked", "reason": "daily_cap", "quota": quota}
            elif stopped():
                result = {"status": "blocked", "reason": "emergency_stop"}
            else:
                dry = args.dry or os.environ.get("AX_DRY") == "1"
                if recovery and not dry:
                    ledger["attempts"][recovery["slot"]] = {
                        **recovery, "status": "reserved_before_publish",
                        "at": datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=9))).isoformat()}
                    write_recovery_ledger(ledger)
                    if stopped():
                        print(json.dumps({"status": "blocked", "reason": "emergency_stop_after_reservation"}, ensure_ascii=False))
                        return 1
                result = gb.publish(args.title, body, labels, cfg=cfg, pinned=[EXAMS[args.job]], dry_run=dry)
                result["quota_before"] = quota
                if recovery:
                    result["recovery_exception"] = recovery
                    if not dry:
                        ledger["attempts"][recovery["slot"]]["result"] = result
                        ledger["attempts"][recovery["slot"]]["status"] = result.get("status", "unknown")
                        write_recovery_ledger(ledger)
    print(json.dumps(result, ensure_ascii=False))
    return 0 if result.get("status") in ("published", "duplicate", "dry_run") else 1


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as exc:
        print(json.dumps({"status": "error", "message": type(exc).__name__ + ": " + str(exc)[:240]}, ensure_ascii=False))
        sys.exit(1)
