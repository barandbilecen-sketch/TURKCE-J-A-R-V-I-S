' Jarvis'i siyah pencere olmadan baslatir (sadece arayuz gorunur).
Set fso = CreateObject("Scripting.FileSystemObject")
Set sh = CreateObject("WScript.Shell")
dir = fso.GetParentFolderName(WScript.ScriptFullName)
sh.CurrentDirectory = dir
args = ""
If WScript.Arguments.Count > 0 Then args = " " & WScript.Arguments(0)
pyw = dir & "\.venv\Scripts\pythonw.exe"
If Not fso.FileExists(pyw) Then
  MsgBox "Jarvis kurulu degil. Once Kurulum.bat dosyasini calistir.", 48, "Jarvis"
  WScript.Quit
End If
sh.Run """" & pyw & """ """ & dir & "\jarvis.py""" & args, 0, False
