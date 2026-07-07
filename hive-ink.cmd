@echo off
REM HIVE OS - Launch with Ink frontend
cd /d "%~dp0"
node hive-frontend\dist\index.js %*
