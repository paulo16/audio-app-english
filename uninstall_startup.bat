@echo off
:: uninstall_startup.bat — Supprime toutes les tâches planifiées English Learning
echo Suppression des tâches planifiées English Learning...
schtasks /delete /tn "EnglishApp_Startup"       /f 2>nul
schtasks /delete /tn "EnglishReminder_0600"     /f 2>nul
schtasks /delete /tn "EnglishReminder_1240"     /f 2>nul
schtasks /delete /tn "EnglishReminder_1930"     /f 2>nul
schtasks /delete /tn "EnglishReminder_Boot"     /f 2>nul
echo Toutes les tâches supprimées.
pause
