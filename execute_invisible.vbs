Set WshShell = CreateObject("WScript.Shell")
' 0 = Hide Window, 1 = Show Window
' run_viewer.bat를 숨김 모드로 실행합니다.
WshShell.Run "run_viewer.bat", 0
Set WshShell = Nothing
