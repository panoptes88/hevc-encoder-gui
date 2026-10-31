@echo off
chcp 65001 >nul
echo ============================================
echo x265 批量转码工具 - 打包脚本
echo ============================================
echo.

if exist ".venv\Scripts\activate.bat" (
    call .venv\Scripts\activate.bat
)

echo 检查 PyInstaller...
pip install pyinstaller -q

echo 清理旧构建...
if exist build rmdir /s /q build
if exist dist rmdir /s /q dist

echo 开始打包...
pyinstaller "x265转码工具.spec" --noconfirm

if %ERRORLEVEL% EQU 0 (
    echo.
    echo ============================================
    echo 打包成功！
    echo 输出文件：dist\x265转码工具.exe
    echo.
    echo 使用说明：
    echo 1. 将 ffmpeg 文件夹复制到 dist 目录中
    echo    dist\
    echo    ├── x265转码工具.exe
    echo    └── ffmpeg\
    echo        ├── ffmpeg.exe
    echo        └── ffprobe.exe
    echo 2. 直接发送 dist 文件夹给朋友即可使用
    echo ============================================
) else (
    echo.
    echo 打包失败，请检查错误信息
)
pause

