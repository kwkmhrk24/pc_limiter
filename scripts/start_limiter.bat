@echo off
REM ============================================
REM PC Limiter - 起動スクリプト
REM WSL2上のPC Limiterをバックグラウンドで起動する
REM ============================================

REM WSLg用にDISPLAYを明示設定して起動
start /min wsl -d Ubuntu-20.04 -- bash -c "export DISPLAY=:0 && cd /home/hiroki/Portfolio/pc_limiter && python3 main.py >> /tmp/pc_limiter.log 2>&1"
