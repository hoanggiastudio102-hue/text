' Chay Chay_ngam.bat o che do an (khong hien cua so den)
Set fso = CreateObject("Scripting.FileSystemObject")
dir = fso.GetParentFolderName(WScript.ScriptFullName)
Set sh = CreateObject("WScript.Shell")
sh.CurrentDirectory = dir
sh.Run "cmd /c """ & dir & "\Chay_ngam.bat""", 0, False
