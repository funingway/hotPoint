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
# 项目级 Python 环境配置文件：内容可以是 conda 环境名或 python 绝对路径
ENV_CONFIG_FILE = PROJECT_DIR / ".python-env"
# 与项目相关的 conda 环境名候选（自动匹配用）
PROJECT_ENV_KEYWORDS = ("hot", "hotpoint", "hotspot")

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


def relaunch_with_python(python_path: str, env_label: str = "") -> int:
    """用指定 python 重新启动 start.py"""
    print(f"[OK] 使用环境: {env_label or python_path}")
    return subprocess.call([python_path, str(Path(__file__).resolve())])


# ============================================================
# Conda 环境扫描
# ============================================================
def find_conda() -> str | None:
    """查找 conda 可执行文件"""
    # 1. PATH 中的 conda
    c = shutil.which("conda")
    if c:
        return c
    # 2. 常见安装路径
    candidates = [
        r"D:\ProgramData\anaconda3\Scripts\conda.exe",
        r"D:\ProgramData\miniconda3\Scripts\conda.exe",
        r"C:\ProgramData\anaconda3\Scripts\conda.exe",
        r"C:\ProgramData\miniconda3\Scripts\conda.exe",
        os.path.expandvars(r"C:\Users\%USERNAME%\anaconda3\Scripts\conda.exe"),
        os.path.expandvars(r"C:\Users\%USERNAME%\miniconda3\Scripts\conda.exe"),
        os.path.expandvars(r"C:\Users\%USERNAME%\miniconda3\condabin\conda.bat"),
    ]
    for c in candidates:
        if Path(c).exists():
            return c
    return None


def list_conda_envs() -> dict[str, str]:
    """返回 {env_name: python_path}，扫描所有 conda 环境"""
    conda = find_conda()
    if not conda:
        return {}
    try:
        r = subprocess.run(
            [conda, "env", "list"],
            capture_output=True, text=True, timeout=10,
        )
        envs: dict[str, str] = {}
        for line in r.stdout.splitlines():
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            parts = line.split()
            # 格式: name path  或  name path  *  (当前激活)
            if len(parts) >= 2:
                name = parts[0]
                path = parts[1]
                if name == "base" or Path(path).exists():
                    if sys.platform == "win32":
                        py = Path(path) / "python.exe"
                    else:
                        py = Path(path) / "bin" / "python"
                    if py.exists():
                        envs[name] = str(py)
        return envs
    except Exception:
        return {}


def check_python_version(python_path: str, min_ver: tuple = (3, 10)) -> bool:
    """检查指定 python 是否 >= min_ver"""
    try:
        r = subprocess.run(
            [python_path, "-c", "import sys; print(sys.version_info[:2])"],
            capture_output=True, text=True, timeout=5,
        )
        if r.returncode == 0:
            ver = eval(r.stdout.strip())
            if isinstance(ver, tuple) and ver >= min_ver:
                return True
    except Exception:
        pass
    return False


def check_hotspot_installed(python_path: str) -> bool:
    """检查指定 python 是否已安装 hotspot 包（判断环境是否已配置好）"""
    try:
        r = subprocess.run(
            [python_path, "-c", "import hotspot; print(hotspot.__file__)"],
            capture_output=True, text=True, timeout=5,
        )
        return r.returncode == 0
    except Exception:
        return False


# ============================================================
# 项目环境自动匹配
# ============================================================
def read_env_config() -> str | None:
    """读取项目级环境配置文件 .python-env
    内容可以是：
      - conda 环境名（如 hot_env）
      - python 绝对路径
    """
    if not ENV_CONFIG_FILE.exists():
        return None
    try:
        content = ENV_CONFIG_FILE.read_text(encoding="utf-8").strip()
        return content if content else None
    except Exception:
        return None


def write_env_config(value: str) -> None:
    """写入项目级环境配置"""
    ENV_CONFIG_FILE.write_text(value + "\n", encoding="utf-8")


def find_project_python() -> tuple[str | None, str]:
    """按优先级查找项目应使用的 Python 环境。
    返回 (python_path, env_label)
    """
    # 1. 项目配置文件 .python-env
    cfg = read_env_config()
    if cfg:
        # 如果是绝对路径
        if Path(cfg).exists() and Path(cfg).is_file():
            return cfg, f"配置文件指定: {cfg}"
        # 否则当作 conda 环境名
        envs = list_conda_envs()
        if cfg in envs:
            return envs[cfg], f"conda 环境: {cfg}"
        # 也可能是相对路径
        p = PROJECT_DIR / cfg
        if p.exists() and p.is_file():
            return str(p), f"配置文件指定: {cfg}"

    # 2. 项目下 .venv
    if venv_python_exists():
        return get_venv_python(), f".venv: {VENV_DIR}"

    # 3. 扫描 conda 环境，匹配项目相关名称
    envs = list_conda_envs()
    for keyword in PROJECT_ENV_KEYWORDS:
        for name, py in envs.items():
            if keyword in name.lower():
                return py, f"conda 环境: {name}"

    return None, ""


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


def install_requirements(python_path: str | None = None) -> bool:
    py = python_path or get_venv_python()
    print(f"[安装] 依赖包（requirements.txt）到 {py} ...")
    subprocess.run([py, "-m", "pip", "install", "--upgrade", "pip"],
                   capture_output=True)
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
# 交互式环境选择
# ============================================================
def find_system_python() -> str | None:
    """找一个可用的系统 Python（>=3.10），用于创建 .venv"""
    candidates: list[str] = []
    # py launcher 优先
    for name in ("py", "python", "python3"):
        p = shutil.which(name)
        if p:
            candidates.append(p)
    # conda base
    conda = find_conda()
    if conda:
        envs = list_conda_envs()
        if "base" in envs:
            candidates.append(envs["base"])
    # 常见安装路径
    common_paths = [
        r"D:\ProgramData\anaconda3\python.exe",
        r"C:\ProgramData\anaconda3\python.exe",
        r"C:\ProgramData\miniconda3\python.exe",
        os.path.expandvars(r"C:\Users\%USERNAME%\anaconda3\python.exe"),
        os.path.expandvars(r"C:\Users\%USERNAME%\miniconda3\python.exe"),
        os.path.expandvars(r"C:\Python310\python.exe"),
        os.path.expandvars(r"C:\Python311\python.exe"),
        os.path.expandvars(r"C:\Python312\python.exe"),
        os.path.expandvars(r"C:\Python313\python.exe"),
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
        if check_python_version(cand):
            return cand
    return None


def interactive_select_env() -> tuple[str | None, str, str]:
    """交互式选择 Python 环境。
    返回 (python_path, env_label, env_config_value_to_save)
    env_config_value_to_save 为空字符串则不保存配置
    """
    print()
    print("-" * 60)
    print("  选择 Python 环境")
    print("-" * 60)

    # 收集所有候选环境
    options: list[tuple[str, str, str]] = []  # (python_path, label, config_value)

    # 1. 项目下 .venv
    if venv_python_exists():
        py = get_venv_python()
        ok = check_hotspot_installed(py)
        tag = " (已装 hotspot)" if ok else " (未装依赖)"
        options.append((py, f".venv 项目虚拟环境{tag}", ".venv"))

    # 2. 所有 conda 环境
    conda_envs = list_conda_envs()
    for name, py in conda_envs.items():
        ver_ok = check_python_version(py)
        if not ver_ok:
            continue
        installed = check_hotspot_installed(py)
        tag = " (已装 hotspot)" if installed else ""
        mark = " ★" if any(k in name.lower() for k in PROJECT_ENV_KEYWORDS) else ""
        options.append((py, f"conda: {name}{tag}{mark}", name))

    # 3. 系统 Python（用于新建 .venv）
    base_py = find_system_python()
    if base_py:
        options.append((base_py, "新建 .venv 虚拟环境（推荐，隔离干净）", "NEW_VENV"))

    if not options:
        print("[错误] 找不到任何 Python >= 3.10")
        print("       请从 https://www.python.org 安装 Python 3.10+ 后重试")
        return None, "", ""

    # 打印选项
    print()
    for i, (py, label, _) in enumerate(options, 1):
        print(f"  [{i}] {label}")
        print(f"      {py}")
    print(f"  [0] 退出")
    print()

    choice = input(f"请选择 (0-{len(options)}，默认 1): ").strip()
    if choice == "0":
        return None, "", ""
    try:
        idx = int(choice) if choice else 1
        if idx < 1 or idx > len(options):
            raise ValueError()
    except ValueError:
        print("[错误] 无效选择")
        return None, "", ""
    return options[idx - 1]


# ============================================================
# 一键安装
# ============================================================
def one_click_install(python_path: str, env_label: str,
                      env_config_value: str) -> bool:
    print()
    print("-" * 60)
    print(f"  配置环境: {env_label}")
    print("-" * 60)
    print(f"[OK] Python: {python_path}")

    # 如果选了新建 .venv
    if env_config_value == "NEW_VENV":
        if not venv_python_exists():
            if not create_venv(python_path):
                return False
        python_path = get_venv_python()
        env_config_value = ".venv"
        print(f"[OK] 切换到 .venv: {python_path}")

    # 安装依赖
    if not check_hotspot_installed(python_path):
        if not install_requirements(python_path):
            return False
    else:
        print("[OK] hotspot 依赖已安装")

    # 保存配置（下次自动使用）
    if env_config_value and env_config_value != "NEW_VENV":
        try:
            write_env_config(env_config_value)
            print(f"[OK] 已记住环境选择（写入 {ENV_CONFIG_FILE.name}），下次自动使用")
        except Exception as e:
            print(f"[提示] 保存环境配置失败: {e}（不影响本次运行）")

    # Ollama
    print()
    print("[检查] Ollama 状态...")
    if not ollama_available():
        print("[!] 未检测到 Ollama")
        ans = input("    是否自动下载并安装 Ollama？(y/n，默认 y): ").strip().lower()
        if ans in ("", "y", "yes"):
            install_ollama()
        else:
            print("[提示] 可稍后手动安装: https://ollama.com/download")

    if ollama_available():
        start_ollama_service()

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
def _same_python(a: str, b: str) -> bool:
    """比较两个 python 路径是否指向同一个文件（规范化 + 不区分大小写）"""
    try:
        pa = Path(a).resolve()
        pb = Path(b).resolve()
        return pa == pb or pa.name.lower() == pb.name.lower() and \
               pa.stat().st_size == pb.stat().st_size
    except Exception:
        return os.path.normcase(os.path.abspath(a)) == \
               os.path.normcase(os.path.abspath(b))


def main():
    os.chdir(str(PROJECT_DIR))
    print_banner()

    current_py = sys.executable
    print(f"[i] 当前 Python: {current_py}")

    # 情况 1：已在虚拟环境中运行（venv/conda 已激活）→ 直接启动
    if in_virtualenv():
        env_name = os.environ.get("VIRTUAL_ENV") or \
                   os.environ.get("CONDA_PREFIX") or sys.prefix
        print(f"[OK] 当前环境: {env_name}")
        if not check_hotspot_installed(current_py):
            print("[!] 当前环境未安装 hotspot 依赖，开始安装...")
            if not install_requirements(current_py):
                print("[错误] 依赖安装失败，请手动执行: "
                      f"{current_py} -m pip install -r requirements.txt")
                input("按回车退出...")
                return
        launch_web()
        return

    # 情况 2：自动查找项目环境（配置文件 / .venv / conda 环境名匹配）
    project_py, env_label = find_project_python()
    if project_py:
        # 关键防死循环：如果当前 python 已经是项目 python（如 conda 环境未激活但
        # 直接用其 python.exe 运行），直接启动，不再 relaunch
        if _same_python(current_py, project_py):
            print(f"[OK] 当前即为项目环境: {env_label}")
            if check_hotspot_installed(current_py):
                launch_web()
                return
            print("[!] 未安装 hotspot 依赖，开始安装...")
            if install_requirements(current_py):
                launch_web()
                return
            print("[错误] 依赖安装失败")
            input("按回车退出...")
            return

        # 当前 python 不是项目 python → 用项目 python 重启
        if check_hotspot_installed(project_py):
            print(f"[OK] 检测到项目环境: {env_label}")
            relaunch_with_python(project_py, env_label)
            return
        else:
            # 找到环境但没装依赖 → 询问是否安装
            print(f"[!] 检测到环境: {env_label}")
            print(f"    但尚未安装 hotspot 依赖")
            ans = input("    是否现在安装依赖？(y/n，默认 y): ").strip().lower()
            if ans in ("", "y", "yes"):
                if install_requirements(project_py):
                    relaunch_with_python(project_py, env_label)
                    return
            print("[提示] 进入手动选择模式...")

    # 情况 3：交互式选择环境
    py, label, cfg_val = interactive_select_env()
    if not py:
        print("[退出] 用户取消")
        return

    # 防死循环：如果选的环境就是当前 python，直接启动
    if _same_python(current_py, py) and check_hotspot_installed(py):
        if cfg_val and cfg_val not in ("NEW_VENV",):
            try:
                write_env_config(cfg_val)
            except Exception:
                pass
        print(f"[OK] 使用当前环境: {label}")
        launch_web()
        return

    # 如果选的环境已装好依赖，relaunch
    if check_hotspot_installed(py):
        if cfg_val and cfg_val != "NEW_VENV":
            try:
                write_env_config(cfg_val)
            except Exception:
                pass
        relaunch_with_python(py, label)
        return

    # 需要安装
    if one_click_install(py, label, cfg_val):
        final_py = get_venv_python() if cfg_val in ("NEW_VENV", ".venv") else py
        if cfg_val and cfg_val != "NEW_VENV":
            try:
                write_env_config(cfg_val)
            except Exception:
                pass
        # 防死循环：如果 final_py 就是当前 python，直接启动
        if _same_python(current_py, final_py):
            print()
            print("[启动] 启动 hotPoint...")
            launch_web()
        else:
            print()
            print("[启动] 使用配置好的环境启动 hotPoint...")
            relaunch_with_python(final_py, label)
    else:
        print("[错误] 安装未完成，请根据提示修复后重试")
        input("按回车退出...")


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
