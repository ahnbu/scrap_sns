Option Explicit

Dim shell, fso, repoRoot, indexUrl, restartScript, restartCommand

Set shell = CreateObject("WScript.Shell")
Set fso = CreateObject("Scripting.FileSystemObject")

repoRoot = fso.GetParentFolderName(WScript.ScriptFullName)
indexUrl = "http://localhost:5000/"
restartScript = repoRoot & "\scripts\restart_viewer_server.ps1"

If fso.FileExists(restartScript) Then
    restartCommand = "powershell.exe -NoProfile -ExecutionPolicy Bypass -File " & Chr(34) & restartScript & Chr(34) & " -ProjectRoot " & Chr(34) & repoRoot & Chr(34)
    If shell.Run(restartCommand, 0, True) <> 0 Then
        MsgBox "SNS Viewer 서버 재시작에 실패했습니다. 5000번 포트를 다른 프로세스가 사용 중이거나 구버전 server.py가 남아 있을 수 있습니다. 해당 프로세스를 종료한 뒤 다시 시도하세요.", vbExclamation, "SNS Feed Viewer"
        WScript.Quit 1
    End If
Else
    shell.Run "cmd /c cd /d " & Chr(34) & repoRoot & Chr(34) & " && python scrap_sns_server.py", 0, False
    WScript.Sleep 3000
End If

shell.Run "cmd /c start " & Chr(34) & Chr(34) & " " & indexUrl, 0, False
