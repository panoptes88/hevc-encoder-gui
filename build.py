# -*- coding: utf-8 -*-
"""PyInstaller 打包脚本：调用 PyInstaller Python API。"""
import os
import sys
import shutil

os.chdir(os.path.dirname(os.path.abspath(__file__)))

# 清理旧产物
for p in ['build', 'main.spec']:
    if os.path.isdir(p):
        shutil.rmtree(p, ignore_errors=True)
    elif os.path.isfile(p):
        try:
            os.remove(p)
        except OSError:
            pass

from PyInstaller.__main__ import run as pyi_run

pyi_run([
    '--onefile',
    '--windowed',
    '--name', 'x265转码工具',
    '--noconfirm',
    '--clean',
    '--distpath', 'dist',
    '--workpath', 'build',
    '--specpath', '.',
    'main.py',
])

exe_path = os.path.join('dist', 'x265转码工具.exe')
if os.path.exists(exe_path):
    sz = os.path.getsize(exe_path) / 1024 / 1024
    print(f"BUILD_SUCCESS: {exe_path} ({sz:.1f}MB)")
else:
    print("BUILD_FAILED: exe not found")
    sys.exit(1)
