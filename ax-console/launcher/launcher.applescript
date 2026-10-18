-- AX 발행 콘솔 바탕화면 실행 아이콘. 실제 일은 USB 의 open_console.sh 가 한다.
set script_path to "/Volumes/USB256/devAPP/AutoSNS/ax-console/launcher/open_console.sh"
tell application "System Events" to set usb_ok to exists disk item script_path
if not usb_ok then
	display alert "USB256 이 연결돼 있지 않습니다" message "AX 발행 콘솔은 USB256 에 있습니다. USB 를 연결한 뒤 다시 실행하세요." as warning
	return
end if
do shell script "/bin/bash " & quoted form of script_path & " > /dev/null 2>&1 &"
