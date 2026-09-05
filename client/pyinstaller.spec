# -*- mode: python ; coding: utf-8 -*-
"""lambchat_sandbox daemon 的 PyInstaller 打包 spec（onefile 单文件产物）。

入口 client/lambchat_sandbox/__main__.py 与 ``python -m lambchat_sandbox`` 等价；
包内仅依赖 stdlib + httpx，hiddenimports 无需手工列举（Analysis 按入口可达性收集，
pytest/mypy 等 dev 依赖天然不会被打进来）。

路径基准：PyInstaller 执行 spec 时不切换 cwd，spec 内相对路径会随调用目录漂移，
因此统一用内置 ``SPECPATH``（spec 所在目录 client/）反推仓库根，
保证从任意 cwd（Makefile / 脚本 / CI）调用都稳定。

瘦身 excludes（xref 实测，2026-09）：dev venv 里 httpx[cli] 的可选链会拖进
rich→pygments→PIL→numpy→yaml、click、zstandard，anyio 拖进 uvloop/_pytest，
全部是条件导入（运行时才 import、缺失即降级），daemon 的运行路径不触发；
不排除时 onefile 产物 50MB（未压缩 139.6MB，numpy+zstandard+uvloop+pillow 占 104MB）。
psutil 不在此列：procsup.py（Windows 父进程监视）模块级硬依赖，排除即崩。
"""

from pathlib import Path

REPO_ROOT = Path(SPECPATH).resolve().parent

a = Analysis(
    [str(REPO_ROOT / "client/lambchat_sandbox/__main__.py")],
    pathex=[str(REPO_ROOT / "client")],
    binaries=[],
    datas=[],
    hiddenimports=[],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        # httpx[cli] 可选链（rich→pygments→PIL→numpy→yaml、markdown_it）。
        # psutil 曾误列于此（当作 rich 链传递依赖），实为 procsup.py 硬依赖。
        "rich",
        "pygments",
        "markdown_it",
        "PIL",
        "numpy",
        "yaml",
        "click",
        "zstandard",
        # anyio 可选事件循环与 pytest 插件
        "uvloop",
        "_pytest",
    ],
    noarchive=False,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name="lambchat-daemon",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
