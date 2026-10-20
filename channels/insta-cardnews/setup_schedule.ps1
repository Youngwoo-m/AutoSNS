# 매주 지정 요일/시각에 run.bat 을 실행하는 Windows 작업 스케줄러 등록 스크립트.
# 사용법(관리자 PowerShell 권장):  powershell -ExecutionPolicy Bypass -File setup_schedule.ps1
# 기본: 매주 금요일 18:30 (네이버 블로그 18:00 과 겹치지 않게 30분 뒤).

$TaskName = "InstaCardNewsWeeklyAutoPost"
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Definition
$BatPath = Join-Path $ScriptDir "run.bat"

if (-not (Test-Path $BatPath)) {
    Write-Error "run.bat 을 찾을 수 없습니다: $BatPath"
    exit 1
}

# 기존 작업이 있으면 제거 후 재등록
$existing = Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
if ($existing) {
    Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false
    Write-Host "기존 작업 제거됨: $TaskName"
}

$action = New-ScheduledTaskAction -Execute $BatPath
$trigger = New-ScheduledTaskTrigger -Weekly -DaysOfWeek Friday -At 6:30PM
$settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries -ExecutionTimeLimit (New-TimeSpan -Minutes 30)
$principal = New-ScheduledTaskPrincipal -UserId $env:USERNAME -LogonType Interactive -RunLevel Limited

Register-ScheduledTask -TaskName $TaskName -Action $action -Trigger $trigger `
    -Settings $settings -Principal $principal `
    -Description "재난안전 뉴스 → Gamma 카드 → 인스타그램 캐러셀 자동 게시 (매주 금 18:30)"

Write-Host ""
Write-Host "등록 완료: '$TaskName' (매주 금요일 18:30)"
Write-Host "지금 바로 테스트하려면:  Start-ScheduledTask -TaskName $TaskName"
Write-Host "삭제하려면:            Unregister-ScheduledTask -TaskName $TaskName -Confirm:`$false"
