Set sh = CreateObject("Wscript.Shell")
sh.CurrentDirectory = CreateObject("Scripting.FileSystemObject").GetParentFolderName(WScript.ScriptFullName)
If Not CreateObject("Scripting.FileSystemObject").FolderExists(sh.CurrentDirectory & "\.venv") Then
  MsgBox "Run install.bat first.", 48, "Staff Management"
  WScript.Quit 1
End If
sh.Run "cmd /c .venv\Scripts\activate.bat && python server.py", 0, False
sh.Run "http://127.0.0.1:8080", 1, False
