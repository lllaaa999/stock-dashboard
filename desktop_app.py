# -*- coding: utf-8 -*-
"""
股票综合看盘系统 · 七层雷达 (AlphaPulse) 桌面端原生启动器
=========================================================
支持三种运行态：
1. PyInstaller 打包后的独立 `.exe` 免安装桌面软件
2. 安装了 `pywebview` 时的 Windows WebView2 原生独立窗口
3. 未安装 `pywebview` 时自动调用 Edge / Chrome 的 `--app` 沉浸式独立软件窗口（无地址栏/标签栏）
"""
import os
import sys
import time
import socket
import threading
import subprocess
import webbrowser
import urllib.request


def _setup_paths() -> str:
    """配置源码或 PyInstaller 冻结态下的模块搜索路径与数据目录"""
    if getattr(sys, "frozen", False):
        # PyInstaller 解压/运行根目录
        bundle_dir = getattr(sys, "_MEIPASS", os.path.dirname(sys.executable))
        exe_dir = os.path.dirname(sys.executable)
    else:
        bundle_dir = os.path.dirname(os.path.abspath(__file__))
        exe_dir = bundle_dir

    # 将根目录、web、scripts 加入 sys.path
    for sub in ("", "web", "scripts"):
        p = os.path.join(bundle_dir, sub) if sub else bundle_dir
        if os.path.isdir(p) and p not in sys.path:
            sys.path.insert(0, p)

    # 数据目录优先放在可执行文件同级 data/ 下，保证升级 exe 不丢失自选股与复盘数据
    external_data = os.path.join(exe_dir, "data")
    bundled_data = os.path.join(bundle_dir, "data")
    if os.path.isdir(external_data):
        os.environ.setdefault("STOCK_DATA_HOME", external_data)
    elif os.path.isdir(bundled_data):
        os.environ.setdefault("STOCK_DATA_HOME", bundled_data)

    return bundle_dir


def _find_free_port(preferred: int = 8001) -> int:
    """优先使用 8001 端口，若已被占用则自动寻找空闲端口，避免端口冲突闪退"""
    for port in (preferred, 8000, 8008, 8088, 0):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            try:
                s.bind(("127.0.0.1", port))
                return s.getsockname()[1]
            except OSError:
                continue
    return preferred


def _wait_for_server(url: str, timeout: float = 15.0) -> bool:
    """等待本地 FastAPI 服务就绪"""
    deadline = time.time() + timeout
    health_url = f"{url}/api/health"
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(health_url, timeout=1.0) as resp:
                if resp.status == 200:
                    return True
        except Exception:
            time.sleep(0.15)
    return False


def _open_standalone_browser_app(url: str) -> subprocess.Popen | None:
    """调用系统自带的 Edge 或 Chrome 以 --app 无边框独立软件模式打开"""
    candidates = [
        os.path.expandvars(r"%ProgramFiles(x86)%\Microsoft\Edge\Application\msedge.exe"),
        os.path.expandvars(r"%ProgramFiles%\Microsoft\Edge\Application\msedge.exe"),
        os.path.expandvars(r"%LocalAppData%\Microsoft\Edge\Application\msedge.exe"),
        os.path.expandvars(r"%ProgramFiles%\Google\Chrome\Application\chrome.exe"),
        os.path.expandvars(r"%ProgramFiles(x86)%\Google\Chrome\Application\chrome.exe"),
        os.path.expandvars(r"%LocalAppData%\Google\Chrome\Application\chrome.exe"),
    ]
    for browser_exe in candidates:
        if os.path.isfile(browser_exe):
            try:
                return subprocess.Popen(
                    [
                        browser_exe,
                        f"--app={url}",
                        "--window-size=1480,920",
                        "--disable-features=Translate",
                    ]
                )
            except Exception:
                continue
    webbrowser.open(url)
    return None


def main() -> None:
    _setup_paths()
    port = _find_free_port(int(os.environ.get("PORT", "8001")))
    host = "127.0.0.1"
    url = f"http://{host}:{port}"

    import uvicorn
    from web.main import app

    server_config = uvicorn.Config(
        app,
        host=host,
        port=port,
        log_level="warning",
        access_log=False,
    )
    server = uvicorn.Server(server_config)

    server_thread = threading.Thread(target=server.run, name="AlphaPulseServer", daemon=True)
    server_thread.start()

    print(f"[AlphaPulse] 正在启动本地量化引擎 ({url}) ...", flush=True)
    _wait_for_server(url, timeout=15.0)
    print(f"[AlphaPulse] 量化引擎已就绪：{url}", flush=True)

    # 优先使用 pywebview 原生桌面窗口（关闭窗口即退出整个程序）
    try:
        import webview  # type: ignore

        webview.create_window(
            title="股票综合看盘系统 · 七层雷达 (AlphaPulse)",
            url=url,
            width=1480,
            height=920,
            min_size=(1100, 720),
            background_color="#131722",
            text_select=True,
        )
        webview.start()
        server.should_exit = True
        return
    except ImportError:
        pass
    except Exception as e:
        print(f"[AlphaPulse] 原生窗口回退为独立应用窗口模式: {e}", flush=True)

    # 零额外依赖回退：使用 Edge / Chrome 的 --app 独立窗口模式
    _open_standalone_browser_app(url)
    print("[AlphaPulse] 桌面窗口已打开。按 Ctrl+C 可停止后台服务。", flush=True)
    try:
        while server_thread.is_alive():
            time.sleep(0.5)
    except KeyboardInterrupt:
        server.should_exit = True


if __name__ == "__main__":
    main()
