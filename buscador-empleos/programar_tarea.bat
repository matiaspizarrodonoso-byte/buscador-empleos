@echo off
rem Crea una tarea programada de Windows que corre el buscador todos los
rem dias a las 9:00 con tu usuario. Ejecutar UNA SOLA VEZ.
rem Para borrar la tarea despues: schtasks /delete /tn "Buscador de Empleos" /f
cd /d "%~dp0"
schtasks /create /tn "Buscador de Empleos" /tr "\"%~dp0ejecutar_diario.bat\"" /sc daily /st 09:00 /f
echo.
echo Listo. El buscador correra todos los dias a las 09:00.
echo Revisa el resultado en empleos.xlsx y los mensajes en log.txt.
pause
