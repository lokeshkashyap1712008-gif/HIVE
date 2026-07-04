@echo off
REM Run HIVE server in background with NO console window
REM pythonw.exe has no console - perfect for a web server
"C:\Users\lokes\AppData\Local\Programs\Python\Python313\pythonw.exe" "%~dp0main.py" %*