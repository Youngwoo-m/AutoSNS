"""자동 작업이 띄우는 하위 프로그램이 CMD 창을 열지 않게 한다(Windows).

예약 작업은 창 없는 pythonw.exe 로 시작한다. 그런데 창 없는 프로세스가 python.exe·tesseract·ffmpeg 같은
콘솔 프로그램을 띄우면 Windows 가 그때마다 새 콘솔 창을 연다(2026-11-19 사용자 지적: CMD 창이 계속 뜸).
apply() 를 부르면 이 프로세스에서 시작하는 하위 프로세스에 CREATE_NO_WINDOW 를 기본으로 붙인다.
손자 프로세스는 그 숨은 콘솔을 물려받으므로 창이 뜨지 않는다. 크롬 같은 GUI 창에는 영향이 없다.
터미널에서 직접 실행했을 때(콘솔 창이 있을 때)는 아무것도 바꾸지 않아 출력이 그대로 보인다.
"""
import os
import subprocess


def apply():
    if os.name != "nt" or getattr(subprocess.Popen, "_ax_nowindow", False):
        return
    import sys
    if sys.stdout is not None:
        return                          # 출력이 이어져 있으면(터미널·파이프) 자식도 그 출력을 써야 한다 — pythonw 일 때만 적용
    try:
        import ctypes
        if ctypes.windll.kernel32.GetConsoleWindow():
            return                      # 보이는 콘솔이 있으면 하위 프로세스도 그 창을 쓰므로 새 창이 안 뜬다
    except Exception:  # noqa: BLE001
        return
    orig = subprocess.Popen.__init__

    def __init__(self, *args, **kw):
        if not kw.get("creationflags"):
            kw["creationflags"] = subprocess.CREATE_NO_WINDOW
        orig(self, *args, **kw)

    subprocess.Popen.__init__ = __init__
    subprocess.Popen._ax_nowindow = True
