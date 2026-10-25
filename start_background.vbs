Set WshShell = CreateObject("WScript.Shell")
strPath = CreateObject("Scripting.FileSystemObject").GetParentFolderName(WScript.ScriptFullName)
WshShell.CurrentDirectory = strPath

' Launch pythonw without terminal window
WshShell.Run "pythonw app.py", 0, False

' Open dashboard in browser
WScript.Sleep 1500
WshShell.Run "http://localhost:5001"
