"""hotPoint 启动器

一键启动 hotPoint Web 界面 + Ollama 服务。
首次运行自动检测 Python 虚拟环境，若无则引导用户一键安装。
运行方式：双击 start.bat 或 python start.py
"""
import os
import shutil
import socket
import subprocess
import sys
import threading
import time
import webbrowser
from pathlib import Path

# ============================================================
# 配置区
# ============================================================
OLLAMA_URL = "http://localhost:11434"
DEFAULT_MODEL = "batiai/gemma4-12b:q4"
WEB_PORT = 8000
PROJECT_DIR = Path(__file__).parent.resolve()
VENV_DIR = PROJECT_DIR / ".venv"
REQUIREMENTS_FILE = PROJECT_DIR / "requirements.txt"
OLLAMA_INSTALLER_URL = "https://ollama.com/download/OllamaSetup.exe"
OLLAMA_INSTALLER_PATH = PROJECT_DIR / "OllamaSetup.exe"

# Windows 控制台 UTF-8 输出
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass


def print_banner():
    print()
    print("=" * 60)
    print("  hotPoint · 热点情报终端")
    print("=" * 60)


# ============================================================
# 虚拟环境检测
# ============================================================
def in_virtualenv() -> bool:
    """判断当前是否运行在虚拟环境中"""
    if os.environ.get("VIRTUAL_ENV"):
        return True
    if os.environ.get("CONDA_PREFIX"):
        return True
    if sys.prefix != sys.base_prefix:
        return True
    return False


def venv_python_exists() -> bool:
    """检查项目 .venv 是否已创建"""
    if sys.platform == "win32":
        return (VENV_DIR / "Scripts" / "python.exe").exists()
    return (VENV_DIR / "bin" / "python").exists()


def get_venv_python() -> str:
    if sys.platform == "win32":
        return str(VENV_DIR / "Scripts" / "python.exe")
    return str(VENV_DIR / "bin" / "python")


def relaunch_in_venv() -> int:
    """用 .venv 的 python 重新启动 start.py"""
    py = get_venv_python()
    print(f"[OK] 使用虚拟环境: {VENV_DIR}")
    return subprocess.call([py, str(Path(__file__).resolve())])


# ============================================================
# 系统Python查找
# ============================================================
def find_system_python() -> str | None:
    """找一个可用的系统 Python（>=3.10）"""
    candidates: list[str] = [sys.executable]
    for name in ("python", "python3", "py"):
        p = shutil.which(name)
        if p:
            candidates.append(p)
    # 常见 conda / 官方安装路径
    common_paths = [
        r"D:\ProgramData\anaconda3\python.exe",
        r"C:\ProgramData\anaconda3\python.exe",
        r"C:\ProgramData\miniconda3\python.exe",
        os.path.expandvars(r"C:\Users\%USERNAME%\anaconda3\python.exe"),
        os.path.expandvars(r"C:\Users\%USERNAME%\miniconda3\python.exe"),
        os.path.expandvars(r"C:\Python310\python.exe"),
        os.path.expandvars(r"C:\Python311\python.exe"),
        os.path.expandvars(r"C:\Python312\python.exe"),
        os.path.expandvars(r"C:\Users\%USERNAME%\AppData\Local\Programs\Python\Python310\python.exe"),
        os.path.expandvars(r"C:\Users\%USERNAME%\AppData\Local\Programs\Python\Python311\python.exe"),
        os.path.expandvars(r"C:\Users\%USERNAME%\AppData\Local\Programs\Python\Python312\python.exe"),
    ]
    for c in common_paths:
        if Path(c).exists():
            candidates.append(c)

    seen: set[str] = set()
    for cand in candidates:
        cand = os.path.abspath(cand)
        if cand in seen:
            continue
        seen.add(cand)
        try:
            r = subprocess.run(
                [cand, "-c", "import sys; print(sys.version_info[:2])"],
                capture_output=True, text=True, timeout=5,
            )
            if r.returncode == 0:
                ver = eval(r.stdout.strip())
                if isinstance(ver, tuple) and ver >= (3, 10):
                    return cand
        except Exception:
            continue
    return None


# ============================================================
# venv 创建 + 依赖安装
# ============================================================
def create_venv(base_python: str) -> bool:
    print(f"[创建] 虚拟环境 .venv（基础 Python: {base_python}）")
    r = subprocess.run([base_python, "-m", "venv", str(VENV_DIR)])
    if r.returncode != 0:
        print("[错误] 创建虚拟环境失败")
        return False
    print("[OK] 虚拟环境已创建")
    return True


def install_requirements() -> bool:
    py = get_venv_python()
    print("[安装] 依赖包（requirements.txt）...")
    r = subprocess.run(
        [py, "-m", "pip", "install", "--upgrade", "pip"],
        capture_output=True,
    )
    r = subprocess.run(
        [py, "-m", "pip", "install", "-r", str(REQUIREMENTS_FILE)],
    )
    if r.returncode != 0:
        print(f"[错误] 依赖安装失败，请手动执行: {py} -m pip install -r requirements.txt")
        return False
    print("[OK] 依赖已安装")
    return True


# ============================================================
# Ollama 检测/安装/启动
# ============================================================
def ollama_available() -> bool:
    return shutil.which("ollama") is not None


def ollama_service_running() -> bool:
    try:
        import httpx
        r = httpx.get(f"{OLLAMA_URL}/api/tags", timeout=2.0)
        return r.status_code == 200
    except Exception:
        return False


def download_ollama_installer() -> bool:
    import httpx
    print(f"[下载] Ollama 安装包: {OLLAMA_INSTALLER_URL}")
    try:
        with httpx.stream("GET", OLLAMA_INSTALLER_URL, timeout=180.0,
                          follow_redirects=True) as r:
            r.raise_for_status()
            total = int(r.headers.get("content-length", 0))
            downloaded = 0
            with open(OLLAMA_INSTALLER_PATH, "wb") as f:
                for chunk in r.iter_bytes(8192):
                    f.write(chunk)
                    downloaded += len(chunk)
                    if total:
                        pct = downloaded * 100 // total
                        print(f"\r[下载] {pct}% ({downloaded // 1024 // 1024} MB)", end="")
            print()
        print(f"[OK] 安装包已下载: {OLLAMA_INSTALLER_PATH}")
        return True
    except Exception as e:
        print(f"[错误] 下载失败: {e}")
        print(f"       请手动下载: {OLLAMA_INSTALLER_URL}")
        return False


def install_ollama() -> bool:
    if sys.platform != "win32":
        print("[提示] 非 Windows 平台请手动安装 Ollama: https://ollama.com/download")
        return False

    if not OLLAMA_INSTALLER_PATH.exists():
        if not download_ollama_installer():
            return False

    print("[安装] 启动 Ollama 安装程序（请在弹出的窗口中完成安装）...")
    subprocess.run([str(OLLAMA_INSTALLER_PATH)])
    input("安装完成后按回车继续...")

    # 刷新 PATH（当前进程）
    import pathlib
    env_path = os.environ.get("PATH", "")
    for p in [r"C:\Users\{}\AppData\Local\Programs\Ollama".format(os.environ.get("USERNAME", ""))]:
        if p not in env_path:
            os.environ["PATH"] = env_path + os.pathsep + p

    if ollama_available():
        print("[OK] Ollama 已安装")
        return True
    print("[警告] Ollama 可能未正确安装，请检查 PATH 后重试")
    return False


def start_ollama_service() -> bool:
    if not ollama_available():
        return False
    if ollama_service_running():
        print("[OK] Ollama 服务已在运行")
        return True

    print("[启动] Ollama 服务...")
    if sys.platform == "win32":
        subprocess.Popen(
            ["cmd", "/k", "ollama serve"],
            creationflags=subprocess.CREATE_NEW_CONSOLE,
            cwd=str(PROJECT_DIR),
        )
    else:
        subprocess.Popen(["ollama", "serve"])

    print("[等待] Ollama 启动中...")
    for _ in range(15):
        time.sleep(1)
        if ollama_service_running():
            print("[OK] Ollama 服务已启动")
            return True
    print("[警告] Ollama 启动超时")
    return False


def check_model(model: str) -> bool:
    try:
        import httpx
        r = httpx.get(f"{OLLAMA_URL}/api/tags", timeout=2.0)
        tags = r.text
        # 兼容不同模型名写法
        key = model.split(":")[0]
        return key in tags
    except Exception:
        return False


def pull_model(model: str) -> bool:
    print(f"[拉取] ollama pull {model}")
    print("       （首次拉取较大，请耐心等待）")
    r = subprocess.run(["ollama", "pull", model])
    if r.returncode == 0:
        print(f"[OK] 模型 {model} 已就绪")
        return True
    print(f"[警告] 模型拉取失败，可稍后手动执行: ollama pull {model}")
    return False


# ============================================================
# 一键安装
# ============================================================
def one_click_install() -> bool:
    print()
    print("-" * 60)
    print("  一键安装配置环境")
    print("-" * 60)

    # 1. 找系统 Python
    base_py = find_system_python()
    if not base_py:
        print("[错误] 找不到 Python >= 3.10")
        print("       请从 https://www.python.org 安装 Python 3.10+ 后重试")
        input("按回车退出...")
        return False
    print(f"[OK] 检测到系统 Python: {base_py}")

    # 2. 创建 venv
    if not venv_python_exists():
        if not create_venv(base_py):
            return False
    else:
        print(f"[OK] 虚拟环境已存在: {VENV_DIR}")

    # 3. 安装依赖
    if not install_requirements():
        return False

    # 4. Ollama
    print()
    print("[检查] Ollama 状态...")
    if not ollama_available():
        print("[!] 未检测到 Ollama")
        ans = input("    是否自动下载并安装 Ollama？(y/n，默认 y): ").strip().lower()
        if ans in ("", "y", "yes"):
            install_ollama()
        else:
            print("[提示] 可稍后手动安装: https://ollama.com/download")

    # 5. 启动 Ollama 服务
    if ollama_available():
        start_ollama_service()

    # 6. 拉取模型
    model = DEFAULT_MODEL
    if ollama_service_running():
        if not check_model(model):
            print(f"[!] 模型 {model} 未下载")
            ans = input(f"    是否现在拉取 {model}？(y/n，默认 y): ").strip().lower()
            if ans in ("", "y", "yes"):
                pull_model(model)
            else:
                print(f"[提示] 可稍后手动执行: ollama pull {model}")
        else:
            print(f"[OK] 模型 {model} 已就绪")

    print()
    print("=" * 60)
    print("[OK] 环境配置完成")
    print("=" * 60)
    return True


# ============================================================
# Web 启动
# ============================================================
def find_available_port(start: int, max_attempts: int = 20) -> int:
    for port in range(start, start + max_attempts):
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                s.bind(("127.0.0.1", port))
                return port
        except OSError:
            continue
    raise RuntimeError(f"无法找到可用端口（{start}-{start + max_attempts - 1} 均被占用）")


def open_browser_delayed(url: str, delay: float = 2.0):
    def _open():
        time.sleep(delay)
        webbrowser.open(url)
    threading.Thread(target=_open, daemon=True).start()


def launch_web():
    port = find_available_port(WEB_PORT)
    if port != WEB_PORT:
        print(f"[!] 端口 {WEB_PORT} 被占用，自动切换到 {port}")

    url = f"http://127.0.0.1:{port}"
    print()
    print("=" * 60)
    print(f"  启动 Web 界面: {url}")
    print("-" * 60)
    print("  功能：搜索抓取 / 报告档案 / 配置管理 / 数据源管理")
    print("  按 Ctrl+C 停止服务")
    print("=" * 60)
    print()

    open_browser_delayed(url, delay=2.0)
    subprocess.run(
        [sys.executable, "-m", "hotspot", "web", "--port", str(port)],
        cwd=str(PROJECT_DIR),
    )


# ============================================================
# 主流程
# ============================================================
def main():
    os.chdir(str(PROJECT_DIR))
    print_banner()

    # 情况 1：已在虚拟环境中运行
    if in_virtualenv():
        env_name = os.environ.get("VIRTUAL_ENV") or \
                   os.environ.get("CONDA_PREFIX") or sys.prefix
        print(f"[OK] 当前虚拟环境: {env_name}")
        launch_web()
        return

    # 情况 2：.venv 已存在但当前不在其中 → 用 .venv 重启
    if venv_python_exists():
        relaunch_in_venv()
        return

    # 情况 3：无虚拟环境 → 交互提示
    print()
    print("[!] 未检测到 Python 虚拟环境")
    print("    hotPoint 推荐在独立虚拟环境中运行，避免污染系统 Python")
    print()
    print("    [1] 一键安装配置环境（创建 .venv + 安装依赖 + 检测/安装 Ollama）")
    print("    [2] 退出")
    print()
    choice = input("请选择 (1/2，默认 1): ").strip()
    if choice in ("", "1"):
        if one_click_install():
            if venv_python_exists():
                print()
                print("[启动] 使用新创建的虚拟环境启动 hotPoint...")
                relaunch_in_venv()
        else:
            print("[错误] 安装未完成，请根据提示修复后重试")
            input("按回车退出...")
    else:
        print("[退出] 用户取消")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n[中断] Web 服务已停止")
        print("[提示] Ollama 服务仍在后台运行，如需停止请关闭 Ollama 窗口")
    except Exception as e:
        print(f"\n[错误] {e}")
        import traceback
        traceback.print_exc()
        input("按回车退出...")
