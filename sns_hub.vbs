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
        MsgBox "SNS Viewer restart failed. Port 5000 is busy. Close the process and try again.", vbExclamation, "SNS Feed Viewer"
        WScript.Quit 1
    End If
Else
    shell.Run "cmd /c cd /d " & Chr(34) & repoRoot & Chr(34) & " && python scrap_sns_server.py", 0, False
    WScript.Sleep 3000
End If

shell.Run "node ""D:\vibe-coding\_usage\log-usage.mjs"" scrap_sns", 0, False
shell.Run "cmd /c start " & Chr(34) & Chr(34) & " " & indexUrl, 0, False
