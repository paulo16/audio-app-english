@echo off
:: setup_startup.bat — Configure le démarrage auto + rappels Windows
:: À exécuter UNE SEULE FOIS en tant qu'administrateur

set "APP_DIR=%~dp0"
set "APP_DIR=%APP_DIR:~0,-1%"
set "PS_SCRIPT=%APP_DIR%\remind_english.ps1"
set "START_BAT=%APP_DIR%\start.bat"

echo ============================================
echo  Configuration English Learning App
echo ============================================
echo.

:: ---- 1. Démarrage automatique au login Windows ----
echo [1/5] Démarrage automatique de l'app au login...
schtasks /create /tn "EnglishApp_Startup" ^
  /tr "cmd.exe /c \"%START_BAT%\"" ^
  /sc ONLOGON ^
  /rl HIGHEST ^
  /f
if %errorlevel%==0 (echo     OK) else (echo     ERREUR - relancer en administrateur)

:: ---- 2. Rappel 6h00 ----
echo [2/5] Rappel matin 6h00...
schtasks /create /tn "EnglishReminder_0600" ^
  /tr "powershell.exe -WindowStyle Hidden -ExecutionPolicy Bypass -File \"%PS_SCRIPT%\" -Title \"Good Morning! 🌅\" -Message \"Start your day with 15 min of English practice!\"" ^
  /sc DAILY ^
  /st 06:00 ^
  /rl HIGHEST ^
  /f
if %errorlevel%==0 (echo     OK) else (echo     ERREUR)

:: ---- 3. Rappel 12h40 ----
echo [3/5] Rappel midi 12h40...
schtasks /create /tn "EnglishReminder_1240" ^
  /tr "powershell.exe -WindowStyle Hidden -ExecutionPolicy Bypass -File \"%PS_SCRIPT%\" -Title \"Lunch Break English 🎧\" -Message \"Perfect time for a 10-min English podcast or conversation!\"" ^
  /sc DAILY ^
  /st 12:40 ^
  /rl HIGHEST ^
  /f
if %errorlevel%==0 (echo     OK) else (echo     ERREUR)

:: ---- 4. Rappel 19h30 ----
echo [4/5] Rappel soir 19h30...
schtasks /create /tn "EnglishReminder_1930" ^
  /tr "powershell.exe -WindowStyle Hidden -ExecutionPolicy Bypass -File \"%PS_SCRIPT%\" -Title \"Evening Practice 🌙\" -Message \"Evening session time! Practice speaking for 15-20 minutes.\"" ^
  /sc DAILY ^
  /st 19:30 ^
  /rl HIGHEST ^
  /f
if %errorlevel%==0 (echo     OK) else (echo     ERREUR)

:: ---- 5. Rappel au démarrage du PC (notification) ----
echo [5/5] Notification au démarrage du PC...
schtasks /create /tn "EnglishReminder_Boot" ^
  /tr "powershell.exe -WindowStyle Hidden -ExecutionPolicy Bypass -File \"%PS_SCRIPT%\" -Title \"English App is running! 🚀\" -Message \"Your English Learning App started. Go to http://localhost:8502\"" ^
  /sc ONLOGON ^
  /delay 0001:00 ^
  /rl HIGHEST ^
  /f
if %errorlevel%==0 (echo     OK) else (echo     ERREUR)

echo.
echo ============================================
echo  Tâches planifiées créées avec succès !
echo.
echo  Rappels actifs :
echo    - Démarrage PC  : app lancée automatiquement
echo    - 06:00         : rappel matin
echo    - 12:40         : rappel midi
echo    - 19:30         : rappel soir
echo.
echo  Pour vérifier : Gestionnaire des tâches planifiées
echo    (taskschd.msc) chercher "English"
echo.
echo  Pour supprimer toutes les tâches :
echo    run uninstall_startup.bat
echo ============================================
pause
