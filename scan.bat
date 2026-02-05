@echo off
setlocal enabledelayedexpansion
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0scan.ps1" %*
