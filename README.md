# HEVC Encoder GUI

基于 Python + Tkinter 的 H.265/HEVC 批量视频转码工具

---

## 功能特点

- ✅ 批量转码（支持 MP4、MKV、MOV、AVI、TS、M2TS、WMV、FLV、WebM 等格式）
- ✅ 自动检测源视频编码（H.264 自动转 H.265，H.265 自动跳过）
- ✅ 实时进度显示（速度/剩余时间/预估输出大小）
- ✅ 拖拽添加文件支持
- ✅ 自动查找 ffmpeg（支持同目录或系统 PATH）
- ✅ **纯 CPU 压制**，无需 GPU 加速

---

## 界面预览

![界面截图](https://i.loi.li/j/0/2026/06/6a2032b45f98d.png)

---

## 环境要求

- Python 3.8+
- ffmpeg 和 ffprobe（需要在系统 PATH 或 `./ffmpeg/` 目录下）

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

1. 启动程序后，拖拽视频文件到列表中，或点击「+ Add Files」添加
2. 可选：设置输出目录（默认为源文件同目录）
3. 点击「▶ Start」开始转码
4. 转码完成的文件会在文件名后添加 `_hevc.mp4` 后缀

---

## 修改压制参数

所有压制参数都在 `main.py` 文件的 `build_ffmpeg_cmd` 函数中，你可以根据需要修改：

```python
def build_ffmpeg_cmd(task: VideoTask) -> List[str]:
    return [
        FFMPEG_CMD, "-hide_banner", "-nostdin",
        "-i", task.input_path,
        "-map", "0:v:0",
        "-c:v", "libx265",           # 使用 x265 编码器
        "-preset", "medium",         # 预设速度（ultrafast, superfast, veryfast, faster, fast, medium, slow, slower, veryslow）
        "-crf", "25",                # CRF 值（越小画质越好，文件越大，推荐 22-28）
        "-x265-params",
        "colorprim=bt709:transfer=bt709:colormatrix=bt709:range=limited",  # 色彩空间参数
        "-map", "0:a:0?",            # 复制音频流
        "-c:a", "copy",
        "-map_metadata", "0",        # 保留元数据
        "-movflags", "+faststart",   # 优化 MP4 格式（适合网络播放）
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

---

## 打包为 EXE

如果你需要将程序打包成独立的可执行文件（EXE），方便在没有 Python 环境的电脑上运行：

### 步骤 1：安装 PyInstaller

```bash
pip install pyinstaller
```

### 步骤 2：执行打包命令

```bash
pyinstaller --onefile --windowed --name "HEVC-Encoder" main.py
```

### 参数说明

| 参数 | 说明 |
|------|------|
| `--onefile` | 将所有文件打包成单个 EXE 文件 |
| `--windowed` | 不显示控制台窗口（GUI 程序专用） |
| `--name` | 指定输出文件名 |

### 打包结果

执行完命令后，会生成以下文件：

```
dist/
└── HEVC-Encoder.exe    # 可执行文件
```

### 使用打包后的 EXE

1. **运行 EXE**：直接双击 `HEVC-Encoder.exe` 即可启动程序
2. **ffmpeg 依赖**：运行 EXE 的电脑上需要安装 ffmpeg，或者将 ffmpeg 放在 EXE 同目录的 `./ffmpeg/` 文件夹中

### 完整打包示例

```bash
# 安装依赖
pip install pyinstaller

# 打包
pyinstaller --onefile --windowed --name "HEVC-Encoder" main.py

# 运行（打包后）
./dist/HEVC-Encoder.exe
```

---

## 技术说明

- **编码器**: x265 (libx265)
- **预设**: medium
- **CRF**: 25
- **色彩空间**: BT.709
- **输出格式**: MP4 (H.265 + AAC)

---

## 许可证

MIT License
