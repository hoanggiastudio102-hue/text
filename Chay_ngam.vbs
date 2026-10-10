' Chay AutoContentGemini hoan toan an (khong cua so, khong mo trinh duyet). Log: logs\server.log
Set fso = CreateObject("Scripting.FileSystemObject")
dir = fso.GetParentFolderName(WScript.ScriptFullName)
Set sh = CreateObject("WScript.Shell")
sh.CurrentDirectory = dir
py = dir & "\.venv\Scripts\pythonw.exe"
If Not fso.FileExists(py) Then
    MsgBox "Chua cai dat. Hay chay Cai_dat.bat truoc.", 48, "AutoContentGemini"
    WScript.Quit
End If
' da chay roi thi thoi
Set ex = sh.Exec("cmd /c netstat -ano | findstr "":5002 "" | findstr LISTENING")
If Len(ex.StdOut.ReadAll) > 0 Then WScript.Quit
sh.Environment("Process")("AUTOGEMINI_DEBUG") = "0"
sh.Environment("Process")("PYTHONUTF8") = "1"
sh.Run """" & py & """ app.py", 0, False
