"""네트워크 없이 승인 범위·중복·상한·전송 예약을 검증한다."""
import contextlib
from copy import deepcopy
import datetime
import hashlib
import importlib.util
import io
import json
import os
from pathlib import Path
import sys
import tempfile
import types

ROOT = Path(__file__).resolve().parents[4]
spec = importlib.util.spec_from_file_location("engineer_blogger", ROOT / "personal/claude-jobs/publish_engineer_blogger.py")
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
class FixedDatetime(datetime.datetime):
    @classmethod
    def now(cls, tz=None):
        return cls(2026, 10, 31, 16, 0, tzinfo=datetime.timezone(datetime.timedelta(hours=9))).astimezone(tz)
module.datetime = types.SimpleNamespace(datetime=FixedDatetime, timezone=datetime.timezone, timedelta=datetime.timedelta)
approval = json.loads((Path(__file__).parent / "blogger-four-post-exception-approval.json").read_text())
target = approval["targets"][0]
body = (ROOT / "GeoAI_NA/building-engineer-writing/01일차_한중콘크리트타설전점검/Blogger게시본문.html").read_text()
passed = []

with tempfile.TemporaryDirectory() as directory:
    directory = Path(directory)
    source = directory / "approval.json"
    source.write_text(json.dumps(approval))
    fresh = {"approval_id": module.RECOVERY_ID, "attempts": {}}
    def check(name, data=approval, title=target["title"], text=body, day="2026-10-31", entries=(), ledger=fresh, allowed=False):
        source.write_text(json.dumps(data))
        try:
            result = module.recovery_authorization(str(source), "building-daily", title, text, day, entries, ledger)
        except ValueError:
            assert not allowed, name
        else:
            assert allowed and result["slot"] == "building-daily:1", name
        passed.append(name)
    check("승인된 정확한 1일차 허용", allowed=True)
    check("다른 날짜 거절", day="2026-11-01")
    wrong = deepcopy(approval); wrong["blog_id"] = "학과"
    check("다른 블로그 거절", data=wrong)
    wrong = deepcopy(approval); wrong["user_reply"] = ""
    check("승인 누락 거절", data=wrong)
    wrong = deepcopy(approval); wrong["targets"].append(deepcopy(target))
    check("다섯번째 슬롯 거절", data=wrong)
    check("원고 변조 거절", text=body + "change")
    check("제목 변조 거절", title=target["title"].replace("한중콘크리트", "다른주제"))
    check("3일차 거절", title=target["title"].replace("1일차", "3일차"))
    check("미확정 2일차 거절", title=target["title"].replace("1일차", "2일차"))
    for status in ("LIVE", "DRAFT", "SCHEDULED"):
        check(status + " 같은 일차 중복 거절", entries=[{"title": "[건축시공기술사] 다른 제목 | 하루 한 문제 1일차", "status": status}])
    used = deepcopy(fresh); used["attempts"]["building-daily:1"] = {"status": "reserved_before_publish"}
    check("응답 불명 예약 재시도 거절", ledger=used)
    for job, day in module.RECOVERY_SLOTS:
        complete = deepcopy(approval)
        selected = next(t for t in complete["targets"] if (t["job"], t["day"]) == (job, day))
        selected["title"] = "[" + module.EXAMS[job] + "] 검토된 핵심 문제 | 하루 한 문제 " + str(day) + "일차"
        selected["html_sha256"] = hashlib.sha256(body.encode()).hexdigest()
        source.write_text(json.dumps(complete))
        authorized = module.recovery_authorization(str(source), job, selected["title"], body, "2026-10-31", [], fresh)
        assert authorized["slot"] == job + ":" + str(day)
    passed.append("네 승인 슬롯 모두 정확제목·해시 확정 뒤 허용")

    # 전체 main 경로를 fake API·잠금으로 실행한다. 실제 계정/네트워크 호출 없음.
    cfg = {"geoai": {"posts_per_day": 2, "enabled": True}}
    entries = [{"title": "일반글" + str(i), "status": "LIVE", "published": "2026-10-31T01:00:00+09:00"} for i in range(3)]
    calls = []
    class Request:
        def execute(self):
            return {"items": deepcopy(entries)}
    class Posts:
        def list(self, **kwargs):
            assert kwargs["view"] == "ADMIN" and set(kwargs["status"]) == {"LIVE", "DRAFT", "SCHEDULED"}
            return Request()
    class Service:
        def posts(self):
            return Posts()
    def publish(title, text, labels, **kwargs):
        if not kwargs["dry_run"]:
            stored = json.loads(module.RECOVERY_LEDGER.read_text())
            assert stored["attempts"]["building-daily:1"]["status"] == "reserved_before_publish"
        calls.append(kwargs)
        return {"status": "dry_run" if kwargs["dry_run"] else "published", "url": "https://example.test/post"}
    sys.modules["geoai_blogger"] = types.SimpleNamespace(load_config=lambda: cfg, blog_id=lambda _: "7628821136256904634", service=Service, publish=publish)
    @contextlib.contextmanager
    def hold(resources, **kwargs):
        assert resources == ["quota:blogger-personal"]
        yield
    stopped = [False]
    sys.modules["shared.axlock"] = types.SimpleNamespace(hold=hold, stopped=lambda: stopped[0])
    module.RECOVERY_LEDGER = directory / "ledger.json"
    os.environ["AX_LOCKED"] = "1"
    os.environ.pop("AX_DRY", None)
    manuscript = directory / "post.html"; manuscript.write_text(body)
    def run(extra):
        source.write_text(json.dumps(approval))
        sys.argv = ["publish_engineer_blogger.py", "--job", "building-daily", "--html", str(manuscript), "--title", target["title"], *extra]
        stream = io.StringIO()
        with contextlib.redirect_stdout(stream):
            code = module.main()
        return code, json.loads(stream.getvalue())
    code, result = run(["--go"])
    assert code == 1 and result["reason"] == "daily_cap" and not calls
    passed.append("일반 모드는 기존 상한 유지")
    code, result = run(["--dry", "--recovery-approval", str(source)])
    assert code == 0 and result["status"] == "dry_run" and not module.RECOVERY_LEDGER.exists()
    passed.append("dry는 예외 원장 미소비")
    stopped[0] = True
    code, result = run(["--go", "--recovery-approval", str(source)])
    assert code == 1 and result["reason"] == "emergency_stop" and len(calls) == 1
    passed.append("STOP이면 전송 없음")
    stopped[0] = False
    code, result = run(["--go", "--recovery-approval", str(source)])
    assert code == 0 and result["status"] == "published" and len(calls) == 2
    assert cfg == {"geoai": {"posts_per_day": 2, "enabled": True}}
    passed.append("예외는 전송 직전 예약·기존 설정 불변")
    try:
        run(["--go", "--recovery-approval", str(source)])
    except ValueError:
        assert len(calls) == 2
    else:
        raise AssertionError("재시도 차단 실패")
    passed.append("전송 후 반복 예외 차단")

print(json.dumps({"passed": len(passed), "checks": passed, "network_calls": 0}, ensure_ascii=False, indent=2))
