import pathlib

# Windows BAT 文件必须使用 CRLF (\r\n) 换行，且在简体中文 Windows 下使用 GBK 编码
lines = [
    "@echo off",
    "title 股票综合看盘系统",
    'cd /d "D:\\股票看盘\\web"',
    "",
    'netstat -ano | findstr ":8001" | findstr "LISTENING" >nul',
    "if %errorlevel%==0 (",
    "    echo.",
    "    echo ========================================================",
    "    echo  [INFO] 看盘服务已在后台运行中，正在为您打开浏览器...",
    "    echo ========================================================",
    "    start http://127.0.0.1:8001",
    "    exit /b 0",
    ")",
    "",
    "echo ========================================================",
    "echo  股票综合看盘系统 (FastAPI) 正在启动...",
    "echo  9:25竞价雷达 + 持仓风控账本 + 缠论中枢可视化",
    "echo  浏览器访问地址: http://127.0.0.1:8001",
    "echo ========================================================",
    "start http://127.0.0.1:8001",
    "python main.py",
    "if %errorlevel% neq 0 (",
    "    py -3.12 main.py",
    ")",
    "pause",
    ""
]

content = "\r\n".join(lines).encode("gbk")

pathlib.Path(r"C:\Users\28769\Desktop\启动股票看盘.bat").write_bytes(content)
pathlib.Path(r"D:\股票看盘\一键启动股票看盘.bat").write_bytes(content)
print("Updated both BAT files with CRLF and GBK encoding!")
