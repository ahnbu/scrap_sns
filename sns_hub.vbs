Option Explicit

Dim shell, fso, repoRoot, statusUrl, indexUrl
Dim attempt

Set shell = CreateObject("WScript.Shell")
Set fso = CreateObject("Scripting.FileSystemObject")

repoRoot = fso.GetParentFolderName(WScript.ScriptFullName)
statusUrl = "http://localhost:5000/api/status"
indexUrl = "http://localhost:5000/"

If Not IsServerReady(statusUrl) Then
    shell.Run "cmd /c cd /d " & Chr(34) & repoRoot & Chr(34) & " && python server.py", 0, False

    For attempt = 1 To 10
        If IsServerReady(statusUrl) Then
            Exit For
        End If
        WScript.Sleep 1000
    Next
End If

shell.Run "cmd /c start " & Chr(34) & Chr(34) & " " & indexUrl, 0, False

Function IsServerReady(url)
    On Error Resume Next

    Dim http
    Set http = CreateObject("MSXML2.XMLHTTP")
    http.Open "GET", url, False
    http.Send

    IsServerReady = (Err.Number = 0 And http.Status = 200)

    Err.Clear
    On Error GoTo 0
End Function
