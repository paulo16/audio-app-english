@echo off
title English Learning App
cd /d "%~dp0"
echo Starting English Learning App...
start http://localhost:8502
.venv\Scripts\python.exe -m streamlit run app.py --server.port 8502 --server.headless true
pause
