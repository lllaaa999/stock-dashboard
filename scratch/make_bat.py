import os

bat_text = """@echo off
set STOCK_DATA_HOME=D:\\股票看盘\\data
title 股票看盘 · 七层雷达 v2.2 终端服务
cd /d "D:\\股票看盘"

netstat -ano | findstr ":8001" | findstr "LISTENING" >nul
if %errorlevel%==0 (
    echo ========================================================
    echo  [INFO] 看盘服务已在后台运行中，正在为您打开浏览器...
    echo ========================================================
    start http://127.0.0.1:8001
    exit /b 0
)

echo ========================================================
echo  股票综合看盘系统 (FastAPI) 正在启动...
echo  9:25竞价雷达 + 持仓风控账本 + 缠论中枢可视化
echo  浏览器访问地址: http://127.0.0.1:8001
echo ========================================================
start "" cmd /c "timeout /t 2 /nobreak >nul & start http://127.0.0.1:8001"
python web/main.py
pause
"""

for target in [r"D:\股票看盘\一键启动股票看盘.bat", r"C:\Users\28769\Desktop\一键启动股票看盘.bat"]:
    with open(target, "wb") as f:
        f.write(bat_text.replace("\n", "\r\n").encode("gbk"))
print("GBK BAT generated successfully")
