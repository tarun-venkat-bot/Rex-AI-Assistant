Option Explicit

Dim shell, folder, command
Set shell = CreateObject("WScript.Shell")

folder = Left(WScript.ScriptFullName, Len(WScript.ScriptFullName) - Len(WScript.ScriptName))
shell.CurrentDirectory = folder
command = "cmd /c Start_Rex.bat"
shell.Run command, 0, False

Set shell = Nothing
