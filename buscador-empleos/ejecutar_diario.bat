@echo off
rem Corrida silenciosa diaria: la usa la tarea programada (programar_tarea.bat).
rem Sin pausa ni consola; la salida queda en log.txt.
chcp 65001 >nul
cd /d "%~dp0"
python buscador.py >> log.txt 2>&1
