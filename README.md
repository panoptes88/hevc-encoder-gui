# HEVC Encoder GUI

基于 Python + Tkinter 的 H.265/HEVC 批量视频转码工具（Windows 桌面端）

---

## 功能特点

- ✅ 批量转码（支持 MP4、MKV、MOV、AVI、TS、M2TS、WMV、FLV、WebM 等格式）
- ✅ 添加文件后由后台线程探测时长 / 大小 / 编码，界面不卡顿
- ✅ 已是 H.265 的文件默认自动跳过（取消「跳过 H.265」后可重新转码）
- ✅ CRF 与 x265 预设可在界面直接调整，无需改代码
- ✅ 拖拽添加：文件或文件夹都可以拖进窗口，文件夹自动递归查找视频（最多 3 层）
- ✅ 深色主题界面，任务状态用颜色区分（完成 / 处理中 / 跳过 / 错误）
- ✅ 实时进度显示（速度 / 剩余时间 / 预估大小 / 最终大小）
- ✅ 转码中可随时停止，出错的任务可重试
- ✅ 自动查找 ffmpeg（支持同目录 `./ffmpeg/`、系统 PATH 或默认安装路径）
- ✅ **纯 CPU 压制**，无需 GPU 加速
- ✅ 拖放零第三方依赖（Win32 `WM_DROPFILES`），PyInstaller 单文件打包无需额外收集 tcl/tk 库

---

## 界面预览

![界面截图](https://i.loi.li/j/0/2026/06/6a2032b45f98d.png)

---

## 环境要求

- Windows（拖放功能依赖 Win32 API，其他系统能运行但没有拖放）
- Python 3.8+
- ffmpeg 和 ffprobe（需要在系统 PATH 或 `./ffmpeg/` 目录下）

运行时**不依赖任何第三方 Python 包**，只用标准库（tkinter / ctypes / subprocess）。

---

## 安装运行

### 1. 安装 Python

下载并安装 Python 3.8+：https://www.python.org/downloads/

### 2. 安装 ffmpeg

**方法一：使用包管理器**

**Windows**（使用 winget）：
```powershell
winget install ffmpeg
```

**macOS**（使用 Homebrew）：
```bash
brew install ffmpeg
```

**Linux**（Debian/Ubuntu）：
```bash
sudo apt install ffmpeg
```

**方法二：手动下载二进制文件**

如果你不想使用包管理器，可以直接下载预编译的 ffmpeg 二进制文件：

1. **下载地址**：https://github.com/BtbN/FFmpeg-Builds/releases
2. **选择版本**：下载适合你系统的版本（如 `ffmpeg-master-latest-win64-gpl.zip`）
3. **解压**：将下载的压缩包解压到任意目录（如 `D:\Program Files\ffmpeg`）
4. **配置 PATH**：将 ffmpeg 的 `bin` 目录添加到系统环境变量 `PATH` 中

也可以把 `ffmpeg.exe`、`ffprobe.exe` 直接放进程序目录下的 `ffmpeg\` 文件夹，程序会优先使用它。

**验证安装**：

打开命令提示符或终端，运行以下命令验证 ffmpeg 是否安装成功：
```bash
ffmpeg --version
```

### 3. 运行程序

```bash
python main.py
```

---

## 使用说明

1. 点击「＋ 添加文件」选择视频，或直接把**文件 / 文件夹**拖到窗口任意位置
2. 按需调整工具栏的 **CRF**（默认 25）和 **预设**（默认 medium）
   - 勾选「跳过 H.265」时，源文件已是 H.265 的任务会标成「已跳过」
3. 可选：填写输出目录（默认为源文件同目录）
4. 点击「▶ 开始转码」开始，随时可点「■ 停止」中断当前任务
5. 转码完成的文件会在原文件名后加 `_x265.mp4` 后缀

---

## 修改压制参数

### 界面可调参数

- **CRF**：恒定质量因子，默认 25，推荐 22–28（越小画质越好、文件越大）
- **预设**：`ultrafast` → `veryslow`，默认 `medium`

这两个值会直接传给 ffmpeg 的 `-crf` 和 `-preset`，不需要改代码。

### 修改其余参数

其他压制参数在 `main.py` 中 `App` 类的 `_build_ffmpeg_cmd` 方法里：

```python
def _build_ffmpeg_cmd(self, task: VideoTask) -> list:
    crf = self.crf_var.get().strip() or "25"
    preset = self.preset_var.get() or "medium"
    return [
        FFMPEG_CMD, "-hide_banner", "-nostdin",
        "-i", task.input_path,
        "-map", "0:v:0",
        "-c:v", "libx265",           # 使用 x265 编码器
        "-preset", preset,           # 预设速度（界面可选）
        "-crf", crf,                 # CRF 值（界面可选）
        "-x265-params",
        "colorprim=bt709:transfer=bt709:colormatrix=bt709:range=limited",  # 色彩空间参数
        "-map", "0:a:0?",            # 复制音频流
        "-c:a", "copy",
        "-map_metadata", "0",        # 保留元数据
        "-movflags", "+faststart",   # 优化 MP4 格式（适合网络播放）
        "-progress", "pipe:1",       # 供界面解析进度
        "-nostats",
        "-y",                        # 覆盖输出文件
        task.output_path,
    ]
```

### 常用参数说明

| 参数 | 说明 | 推荐值 |
|------|------|--------|
| `-preset` | 编码速度/压缩率权衡 | `medium`（平衡）|
| `-crf` | 恒定质量因子 | `22-28`（25 为默认）|
| `-x265-params` | x265 高级参数 | 保持默认即可 |
| `-c:a copy` | 音频直接复制，不重新编码 | 保持默认 |

---

## 打包为 EXE

### 方式一：双击 `打包.bat`（推荐）

自动激活 `.venv`、安装 PyInstaller、按 `x265转码工具.spec` 打包到 `dist\`。

### 方式二：运行打包脚本

```bash
python build.py
```

同样输出到 `dist\x265转码工具.exe`。

### 方式三：手动执行 PyInstaller

```bash
pip install pyinstaller
pyinstaller --onefile --windowed --name "x265转码工具" main.py
```

### 打包结果与使用

```
dist/
└── x265转码工具.exe    # 可执行文件
```

使用打包后的 EXE：

1. 直接双击运行
2. **ffmpeg 依赖**：把 ffmpeg 放在 EXE 同目录的 `ffmpeg\` 文件夹中，或安装到系统 PATH

```
dist\
├── x265转码工具.exe
└── ffmpeg\
    ├── ffmpeg.exe
    └── ffprobe.exe
```

---

## 项目结构

| 文件 | 说明 |
|------|------|
| `main.py` | 主程序：界面、任务队列、转码流程 |
| `dragdrop.py` | Windows 原生文件拖放支持（ctypes + `WM_DROPFILES`） |
| `build.py` | 通过 PyInstaller Python API 打包 |
| `x265转码工具.spec` | PyInstaller 打包配置 |
| `打包.bat` | 一键打包脚本（Windows） |

---

## 技术说明

- **编码器**: x265 (libx265)
- **预设**: medium（界面可改）
- **CRF**: 25（界面可改）
- **色彩空间**: BT.709
- **输出格式**: MP4（H.265 + 原音频直通）
- **界面**: Tkinter + ttk 深色主题，无第三方依赖
- **拖放**: Win32 `DragAcceptFiles` + 子类化窗口过程接收 `WM_DROPFILES`
- **进度**: 解析 `ffmpeg -progress pipe:1` 的输出，不阻塞主线程

---

## 许可证

MIT License
