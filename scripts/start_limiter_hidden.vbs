Set WshShell = CreateObject("WScript.Shell")
WshShell.Run "wsl -d Ubuntu-20.04 -- bash -c ""export DISPLAY=:0 && cd /home/hiroki/Portfolio/pc_limiter && python3 main.py >> /tmp/pc_limiter.log 2>&1""", 0, False
