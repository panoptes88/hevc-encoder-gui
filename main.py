# -*- coding: utf-8 -*-
"""
x265 批量视频转码工具
依赖：Python 3.8+，系统已安装 ffmpeg
"""

import tkinter as tk
from tkinter import ttk, filedialog, messagebox
import subprocess
import threading
import os
import json
import time
from pathlib import Path
from dataclasses import dataclass
from typing import List, Optional
from queue import Queue, Empty
from collections import deque

from dragdrop import enable_drop


# ── 常量 ──────────────────────────────────────────────────────────────────

COLORS = {
    "bg": "#1e1e1e",
    "surface": "#252526",
    "toolbar": "#2d2d30",
    "border": "#3c3c3c",
    "text": "#cccccc",
    "text_bright": "#ffffff",
    "accent": "#0078d4",
    "accent_hover": "#005a9e",
    "success": "#4ec94e",
    "error": "#f47174",
    "warning": "#f4c74e",
    "info": "#58c8ff",
}

FONTS = {
    "default": ("Segoe UI", 9),
    "heading": ("Segoe UI", 9, "bold"),
    "small": ("Segoe UI", 8),
    "large": ("Segoe UI", 11),
}

VIDEO_EXTS = "*.mp4 *.mkv *.mov *.avi *.ts *.m2ts *.wmv *.flv *.webm"
VIDEO_EXT_SET = {e[1:].lower() for e in VIDEO_EXTS.split()}
# 拖入文件夹时向下递归的最大层数，避免整块磁盘被扫
DROP_SCAN_DEPTH = 3

PRESETS = [
    "ultrafast", "superfast", "veryfast", "faster", "fast",
    "medium", "slow", "slower", "veryslow",
]


# ── ffmpeg 路径自动查找 ───────────────────────────────────────────────────

def find_ffmpeg():
    import shutil
    exe_dir = Path(__file__).parent
    local_ffmpeg = exe_dir / "ffmpeg" / "ffmpeg.exe"
    local_ffprobe = exe_dir / "ffmpeg" / "ffprobe.exe"
    if local_ffmpeg.exists() and local_ffprobe.exists():
        return str(local_ffmpeg), str(local_ffprobe)
    ffmpeg_path = shutil.which("ffmpeg")
    ffprobe_path = shutil.which("ffprobe")
    if ffmpeg_path and ffprobe_path:
        return ffmpeg_path, ffprobe_path
    default_bin = r"D:\Program Files (x86)\ffmpeg"
    return str(Path(default_bin) / "ffmpeg.exe"), str(Path(default_bin) / "ffprobe.exe")


FFMPEG_CMD, FFPROBE_CMD = find_ffmpeg()


# ── 数据模型 ──────────────────────────────────────────────────────────────

@dataclass
class VideoTask:
    input_path: str
    output_path: str = ""
    duration_sec: float = 0.0
    input_size: int = 0
    output_size: int = 0
    progress: float = 0.0
    current_time: float = 0.0
    estimated_size: int = 0
    status: str = "等待中"
    error_msg: str = ""
    speed: str = ""
    eta: str = ""
    codec: str = ""


# ── 视频探测 ──────────────────────────────────────────────────────────────

def probe_video(path: str) -> tuple:
    """返回 (时长秒, 文件字节, 编码格式)"""
    size = os.path.getsize(path) if os.path.exists(path) else 0
    codec = ""
    try:
        cmd = [
            FFPROBE_CMD, "-v", "quiet", "-print_format", "json",
            "-show_streams", "-show_format", path,
        ]
        result = subprocess.run(
            cmd, capture_output=True, text=True,
            encoding="utf-8", errors="replace", timeout=15,
            creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
        )
        data = json.loads(result.stdout)
        duration = float(data.get("format", {}).get("duration", 0))
        for stream in data.get("streams", []):
            if stream.get("codec_type") == "video":
                c = stream.get("codec_name", "").upper()
                if c == "H264":
                    codec = "H.264"
                elif c in ("H265", "HEVC"):
                    codec = "H.265"
                else:
                    codec = c
                break
        return duration, size, codec
    except Exception:
        return 0.0, size, codec


# ── 格式化工具 ────────────────────────────────────────────────────────────

def fmt_duration(seconds: float) -> str:
    if seconds <= 0:
        return "--:--"
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s = int(seconds % 60)
    return f"{h:02d}:{m:02d}:{s:02d}" if h > 0 else f"{m:02d}:{s:02d}"


def fmt_size(b: int) -> str:
    if b <= 0:
        return "—"
    for u in ("B", "KB", "MB", "GB"):
        if b < 1024:
            return f"{b:.1f} {u}"
        b /= 1024
    return f"{b:.1f} TB"


def fmt_eta(seconds: float) -> str:
    if seconds <= 0:
        return "—"
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s = int(seconds % 60)
    if h > 0:
        return f"{h}h {m:02d}m"
    if m > 0:
        return f"{m}m {s:02d}s"
    return f"{s}s"


# ── 主界面 ────────────────────────────────────────────────────────────────

class App(tk.Tk):
    COLUMNS = ["#", "文件名", "编码", "时长", "原大小", "进度", "速度", "预估大小", "最终大小", "状态", "剩余时间"]
    COL_WIDTHS = [40, 220, 70, 80, 90, 100, 70, 90, 90, 80, 90]

    def __init__(self):
        super().__init__()
        self.title("x265 批量转码工具")
        self.geometry("1200x650")
        self.minsize(960, 500)
        self.configure(bg=COLORS["bg"])

        self.tasks: List[VideoTask] = []
        self.task_map: dict = {}  # iid -> VideoTask
        self.running = False
        self.stop_flag = threading.Event()
        self.current_proc: Optional[subprocess.Popen] = None
        self.msg_queue: Queue = Queue()
        # 探测串行化：一次拖入大量文件时不会开出一堆线程
        self.probe_queue: Queue = Queue()

        # 转码设置
        self.crf_var = tk.StringVar(value="25")
        self.preset_var = tk.StringVar(value="medium")
        self.skip_h265_var = tk.BooleanVar(value=True)

        self._apply_theme()
        self._build_ui()
        self._init_file_drop()
        threading.Thread(target=self._probe_worker, daemon=True).start()
        self._poll_queue()

    # ── 主题 ──────────────────────────────────────────────────────────────

    def _apply_theme(self):
        style = ttk.Style(self)
        style.theme_use("clam")

        style.configure("Treeview",
                        background=COLORS["surface"], foreground=COLORS["text"],
                        rowheight=28, fieldbackground=COLORS["surface"],
                        font=FONTS["default"])
        style.configure("Treeview.Heading",
                        background=COLORS["toolbar"], foreground=COLORS["text_bright"],
                        font=FONTS["heading"])
        style.map("Treeview",
                  background=[("selected", COLORS["accent"])],
                  foreground=[("selected", COLORS["text_bright"])])

        style.configure("TProgressbar",
                        troughcolor=COLORS["border"],
                        background=COLORS["accent"],
                        thickness=14)

        style.configure("TButton",
                        background=COLORS["toolbar"], foreground=COLORS["text"],
                        font=FONTS["default"], padding=(10, 5))
        style.map("TButton",
                  background=[("active", COLORS["border"]), ("disabled", COLORS["bg"])],
                  foreground=[("disabled", "#666666")])

        style.configure("Accent.TButton",
                        background=COLORS["accent"], foreground=COLORS["text_bright"])
        style.map("Accent.TButton",
                  background=[("active", COLORS["accent_hover"]), ("disabled", "#444444")])

        style.configure("Danger.TButton",
                        background="#c42b1c", foreground=COLORS["text_bright"])
        style.map("Danger.TButton",
                  background=[("active", "#8b1a12")])

        style.configure("TEntry",
                        fieldbackground=COLORS["surface"],
                        background=COLORS["surface"],
                        foreground=COLORS["text_bright"],
                        insertcolor=COLORS["text_bright"],
                        bordercolor=COLORS["border"],
                        lightcolor=COLORS["border"],
                        darkcolor=COLORS["border"],
                        padding=4)
        style.map("TEntry",
                  fieldbackground=[("disabled", COLORS["bg"]),
                                   ("readonly", COLORS["surface"])],
                  foreground=[("disabled", "#666666")])

        style.configure("TCombobox",
                        fieldbackground=COLORS["surface"],
                        background=COLORS["toolbar"],
                        foreground=COLORS["text"],
                        arrowcolor=COLORS["text_bright"])
        # readonly 状态下文字颜色只认 map，不认 configure，否则会是主题的浅灰色
        style.map("TCombobox",
                  fieldbackground=[("readonly", COLORS["surface"]),
                                   ("disabled", COLORS["bg"])],
                  foreground=[("readonly", COLORS["text_bright"]),
                              ("disabled", "#666666")],
                  arrowcolor=[("readonly", COLORS["text_bright"])])
        # 下拉列表是普通 tk.Listbox，颜色取自选项数据库而不是 ttk 样式
        for opt, val in (("*TCombobox*Listbox.background", COLORS["surface"]),
                         ("*TCombobox*Listbox.foreground", COLORS["text"]),
                         ("*TCombobox*Listbox.selectBackground", COLORS["accent"]),
                         ("*TCombobox*Listbox.selectForeground", COLORS["text_bright"])):
            self.option_add(opt, val)

        style.configure("TLabel",
                        background=COLORS["bg"],
                        foreground=COLORS["text"],
                        font=FONTS["default"])

    # ── UI 构建 ───────────────────────────────────────────────────────────

    def _build_ui(self):
        self._build_toolbar()
        self._build_file_list()
        self._build_progress_panel()
        self._build_status_bar()

    def _build_toolbar(self):
        toolbar = tk.Frame(self, bg=COLORS["toolbar"], padx=10, pady=8)
        toolbar.pack(fill="x")

        # 文件操作按钮
        left = tk.Frame(toolbar, bg=COLORS["toolbar"])
        left.pack(side="left")

        ttk.Button(left, text="＋ 添加文件", command=self._add_files).pack(side="left", padx=2)
        ttk.Button(left, text="✕ 移除选中", command=self._remove_selected).pack(side="left", padx=2)
        ttk.Button(left, text="清空列表", command=self._clear_all).pack(side="left", padx=2)

        ttk.Separator(toolbar, orient="vertical").pack(side="left", fill="y", padx=8)

        # 转码设置
        mid = tk.Frame(toolbar, bg=COLORS["toolbar"])
        mid.pack(side="left")

        tk.Label(mid, text="CRF:", bg=COLORS["toolbar"], fg=COLORS["text"],
                 font=FONTS["default"]).pack(side="left")
        crf_entry = ttk.Entry(mid, textvariable=self.crf_var, width=4)
        crf_entry.pack(side="left", padx=(2, 8))

        tk.Label(mid, text="预设:", bg=COLORS["toolbar"], fg=COLORS["text"],
                 font=FONTS["default"]).pack(side="left")
        preset_combo = ttk.Combobox(mid, textvariable=self.preset_var,
                                    values=PRESETS, state="readonly", width=10)
        preset_combo.pack(side="left", padx=(2, 8))

        ttk.Checkbutton(mid, text="跳过 H.265", variable=self.skip_h265_var).pack(side="left")

        ttk.Separator(toolbar, orient="vertical").pack(side="left", fill="y", padx=8)

        # 输出目录
        tk.Label(toolbar, text="输出目录:", bg=COLORS["toolbar"], fg=COLORS["text"],
                 font=FONTS["default"]).pack(side="left")
        self.out_dir_var = tk.StringVar(value="（与源文件同目录）")
        ttk.Entry(toolbar, textvariable=self.out_dir_var, width=24).pack(side="left", padx=2)
        ttk.Button(toolbar, text="浏览", command=self._pick_out_dir).pack(side="left", padx=2)

        # 开始/停止
        right = tk.Frame(toolbar, bg=COLORS["toolbar"])
        right.pack(side="right")

        self.btn_stop = ttk.Button(right, text="■ 停止", command=self._stop,
                                   style="Danger.TButton")
        self.btn_stop.pack(side="right", padx=4)
        self.btn_stop.state(["disabled"])

        self.btn_start = ttk.Button(right, text="▶ 开始转码", command=self._start,
                                    style="Accent.TButton")
        self.btn_start.pack(side="right", padx=4)

    def _build_file_list(self):
        list_frame = tk.Frame(self, bg=COLORS["bg"])
        list_frame.pack(fill="both", expand=True, padx=10, pady=(8, 0))

        container = tk.Frame(list_frame, bg=COLORS["bg"])
        container.pack(fill="both", expand=True)
        self.drop_zone = container

        vsb = ttk.Scrollbar(container, orient="vertical")
        hsb = ttk.Scrollbar(container, orient="horizontal")

        self.tree = ttk.Treeview(
            container, columns=self.COLUMNS, show="headings",
            yscrollcommand=vsb.set, xscrollcommand=hsb.set,
            selectmode="extended",
        )
        vsb.config(command=self.tree.yview)
        hsb.config(command=self.tree.xview)

        for col, width in zip(self.COLUMNS, self.COL_WIDTHS):
            self.tree.heading(col, text=col)
            self.tree.column(col, width=width, minwidth=30, anchor="center")
        self.tree.column("文件名", anchor="w")

        vsb.pack(side="right", fill="y")
        hsb.pack(side="bottom", fill="x")
        self.tree.pack(fill="both", expand=True)

        # 空列表提示
        self.hint_label = tk.Label(
            container,
            text="将视频文件拖拽到此处，或点击「添加文件」",
            bg=COLORS["surface"], fg="#666666",
            font=FONTS["large"],
        )
        self.hint_label.place(relx=0.5, rely=0.5, anchor="center")

        # 状态颜色
        self.tree.tag_configure("done", foreground=COLORS["success"])
        self.tree.tag_configure("err", foreground=COLORS["error"])
        self.tree.tag_configure("active", foreground=COLORS["info"])
        self.tree.tag_configure("skip", foreground=COLORS["warning"])
        self.tree.tag_configure("stopped", foreground="#888888")

    def _build_progress_panel(self):
        panel = tk.Frame(self, bg=COLORS["surface"], padx=12, pady=10)
        panel.pack(fill="x", padx=10, pady=(8, 0))

        # 当前文件
        self.current_file_var = tk.StringVar(value="等待开始...")
        tk.Label(panel, textvariable=self.current_file_var,
                 bg=COLORS["surface"], fg=COLORS["text_bright"],
                 font=FONTS["default"]).pack(anchor="w")

        # 进度条
        self.progress_var = tk.DoubleVar(value=0)
        ttk.Progressbar(panel, variable=self.progress_var,
                         maximum=100, style="TProgressbar").pack(fill="x", pady=(4, 6))

        # 详细信息行
        info = tk.Frame(panel, bg=COLORS["surface"])
        info.pack(fill="x")

        self.progress_text_var = tk.StringVar(value="")
        tk.Label(info, textvariable=self.progress_text_var,
                 bg=COLORS["surface"], fg=COLORS["text"],
                 font=FONTS["default"]).pack(side="left")

        self.speed_var = tk.StringVar(value="")
        tk.Label(info, textvariable=self.speed_var,
                 bg=COLORS["surface"], fg=COLORS["text"],
                 font=FONTS["default"]).pack(side="left", padx=(20, 0))

        self.eta_var = tk.StringVar(value="")
        tk.Label(info, textvariable=self.eta_var,
                 bg=COLORS["surface"], fg=COLORS["text"],
                 font=FONTS["default"]).pack(side="left", padx=(20, 0))

        self.size_var = tk.StringVar(value="")
        tk.Label(info, textvariable=self.size_var,
                 bg=COLORS["surface"], fg=COLORS["text"],
                 font=FONTS["default"]).pack(side="right")

    def _build_status_bar(self):
        bar = tk.Frame(self, bg=COLORS["accent"], height=28)
        bar.pack(fill="x", side="bottom")

        self.status_var = tk.StringVar(value="就绪")
        tk.Label(bar, textvariable=self.status_var,
                 bg=COLORS["accent"], fg="white",
                 font=FONTS["default"], padx=12).pack(side="left", fill="y")

        self.overall_var = tk.StringVar(value="")
        tk.Label(bar, textvariable=self.overall_var,
                 bg=COLORS["accent"], fg="white",
                 font=FONTS["default"], padx=12).pack(side="right", fill="y")

    # ── 文件操作 ──────────────────────────────────────────────────────────

    def _add_files(self):
        paths = filedialog.askopenfilenames(
            title="选择视频文件",
            filetypes=[("视频文件", VIDEO_EXTS), ("所有文件", "*.*")],
        )
        for p in paths:
            self._enqueue_file(p)

    def _enqueue_file(self, path: str) -> bool:
        for t in self.tasks:
            if t.input_path == path:
                return False
        task = VideoTask(input_path=path)
        self.tasks.append(task)
        iid = str(id(task))
        self.task_map[iid] = task
        self._refresh_row(task)
        self.hint_label.place_forget()
        self.probe_queue.put(task)
        return True

    def _probe_worker(self):
        while True:
            task = self.probe_queue.get()
            try:
                dur, size, codec = probe_video(task.input_path)
                task.duration_sec = dur
                task.input_size = size
                task.codec = codec
            except Exception:
                pass
            self.msg_queue.put(("refresh", task))

    # ── 文件拖放 ──────────────────────────────────────────────────────────

    def _init_file_drop(self):
        # Tk 在 Windows 下给每个控件都建了独立 HWND，一次拖放只会投递给
        # 命中测试到的那一个窗口，所以整窗 + 列表容器 + Treeview 都要注册
        self.drop_enabled = False
        for w in (self, self.drop_zone, self.tree):
            if enable_drop(w, self._on_drop_event):
                self.drop_enabled = True

        if self.drop_enabled:
            self.hint_label.config(text="将视频文件或文件夹拖到窗口任意位置\n也可以点击「添加文件」")
        else:
            self.hint_label.config(text="点击「添加文件」添加视频")
            self.status_var.set("当前环境不支持文件拖放")

    def _on_drop_event(self, paths: List[str]):
        # 运行在窗口过程内，只做入队，界面更新由 _poll_queue 在主线程完成
        self.msg_queue.put(("drop", paths))

    def _add_dropped(self, raw_paths: List[str]):
        files, ignored = self._expand_dropped(raw_paths)
        before = len(self.tasks)
        for p in files:
            self._enqueue_file(p)
        added = len(self.tasks) - before

        parts = [f"拖放：新增 {added} 个文件"]
        dup = len(files) - added
        if dup:
            parts.append(f"已在列表中 {dup} 个")
        if ignored:
            parts.append(f"忽略 {ignored} 个不支持的项")
        self.status_var.set("，".join(parts))

    def _expand_dropped(self, paths: List[str]) -> tuple:
        """把拖入的条目展开成视频文件列表，返回 (文件列表, 被忽略的条目数)"""
        files: List[str] = []
        ignored = 0
        for p in paths:
            path = Path(p)
            if path.is_dir():
                found = self._walk_videos(path)
                if not found:
                    ignored += 1
                files.extend(found)
            elif path.suffix.lower() in VIDEO_EXT_SET:
                files.append(p)
            else:
                ignored += 1
        return files, ignored

    def _walk_videos(self, root: Path) -> List[str]:
        found: List[str] = []
        try:
            for dirpath, dirnames, filenames in os.walk(root):
                try:
                    depth = len(Path(dirpath).relative_to(root).parts)
                except ValueError:
                    depth = 0
                if depth >= DROP_SCAN_DEPTH:
                    dirnames[:] = []
                    continue
                for name in filenames:
                    if Path(name).suffix.lower() in VIDEO_EXT_SET:
                        found.append(os.path.join(dirpath, name))
        except Exception:
            pass
        return found

    def _remove_selected(self):
        if self.running:
            return
        for iid in self.tree.selection():
            task = self.task_map.pop(iid, None)
            if task and task in self.tasks:
                self.tasks.remove(task)
            self.tree.delete(iid)
        self._renumber_all()
        if not self.tasks:
            self.hint_label.place(relx=0.5, rely=0.5, anchor="center")

    def _clear_all(self):
        if self.running:
            return
        self.tasks.clear()
        self.task_map.clear()
        for iid in self.tree.get_children():
            self.tree.delete(iid)
        self.hint_label.place(relx=0.5, rely=0.5, anchor="center")

    def _pick_out_dir(self):
        d = filedialog.askdirectory(title="选择输出目录")
        if d:
            self.out_dir_var.set(d)

    # ── Treeview 刷新 ─────────────────────────────────────────────────────

    def _row_values(self, task: VideoTask, idx: int):
        progress_text = f"{task.progress * 100:.1f}%" if task.progress > 0 else "—"
        return (
            idx + 1,
            Path(task.input_path).name,
            task.codec or "—",
            fmt_duration(task.duration_sec),
            fmt_size(task.input_size),
            progress_text,
            task.speed or "—",
            fmt_size(task.estimated_size) if task.estimated_size > 0 else "—",
            fmt_size(task.output_size) if task.output_size > 0 else "—",
            task.status,
            task.eta or "—",
        )

    def _refresh_row(self, task: VideoTask):
        idx = self.tasks.index(task)
        iid = str(id(task))
        vals = self._row_values(task, idx)
        if self.tree.exists(iid):
            self.tree.item(iid, values=vals)
        else:
            self.tree.insert("", "end", iid=iid, values=vals)
        tag = {
            "完成": "done", "错误": "err", "处理中": "active",
            "已跳过": "skip", "已停止": "stopped",
        }.get(task.status, "")
        if tag:
            self.tree.item(iid, tags=(tag,))

    def _renumber_all(self):
        for i, task in enumerate(self.tasks):
            iid = str(id(task))
            if self.tree.exists(iid):
                vals = list(self.tree.item(iid, "values"))
                vals[0] = i + 1
                self.tree.item(iid, values=vals)

    # ── 转码逻辑 ──────────────────────────────────────────────────────────

    def _get_output_path(self, task: VideoTask) -> str:
        out_dir_str = self.out_dir_var.get().strip()
        src = Path(task.input_path)
        if out_dir_str and out_dir_str != "（与源文件同目录）":
            out_dir = Path(out_dir_str)
        else:
            out_dir = src.parent
        return str(out_dir / (src.stem + "_x265.mp4"))

    def _build_ffmpeg_cmd(self, task: VideoTask) -> list:
        crf = self.crf_var.get().strip() or "25"
        preset = self.preset_var.get() or "medium"
        return [
            FFMPEG_CMD, "-hide_banner", "-nostdin",
            "-i", task.input_path,
            "-map", "0:v:0",
            "-c:v", "libx265",
            "-preset", preset,
            "-crf", crf,
            "-x265-params",
            "colorprim=bt709:transfer=bt709:colormatrix=bt709:range=limited",
            "-map", "0:a:0?",
            "-c:a", "copy",
            "-map_metadata", "0",
            "-movflags", "+faststart",
            "-progress", "pipe:1",
            "-nostats",
            "-y",
            task.output_path,
        ]

    def _start(self):
        if not self.tasks:
            self.msg_queue.put(("info", "提示", "请先添加视频文件"))
            return

        if self.skip_h265_var.get():
            for t in self.tasks:
                if t.codec == "H.265" and t.status == "等待中":
                    t.status = "已跳过"
                    t.progress = 1.0
                    self.msg_queue.put(("refresh", t))
        else:
            # 取消勾选后，之前因「已是 H.265」被自动跳过的任务可重新转码
            for t in self.tasks:
                if t.codec == "H.265" and t.status == "已跳过":
                    t.status = "等待中"
                    t.progress = 0.0
                    self.msg_queue.put(("refresh", t))

        pending = [t for t in self.tasks if t.status in ("等待中", "错误")]
        if not pending:
            self.msg_queue.put(("info", "提示", "没有待处理的任务（已全部完成或是 H.265）"))
            return

        self.running = True
        self.stop_flag.clear()
        self.btn_start.state(["disabled"])
        self.btn_stop.state(["!disabled"])
        threading.Thread(target=self._run_all, daemon=True).start()

    def _stop(self):
        self.stop_flag.set()
        if self.current_proc and self.current_proc.poll() is None:
            try:
                self.current_proc.terminate()
            except Exception:
                pass
        self.status_var.set("已停止")

    def _run_all(self):
        tasks_to_run = [t for t in self.tasks if t.status in ("等待中", "错误")]
        total = len(tasks_to_run)
        for i, task in enumerate(tasks_to_run):
            if self.stop_flag.is_set():
                break
            self.msg_queue.put((
                "status_bar",
                f"正在处理 {i + 1}/{total}：{Path(task.input_path).name}",
                f"队列进度 {i + 1}/{total}",
            ))
            self._run_one(task)
        self.msg_queue.put(("done",))

    def _run_one(self, task: VideoTask):
        task.output_path = self._get_output_path(task)
        task.status = "处理中"
        task.progress = 0.0
        task.estimated_size = 0
        task.speed = ""
        task.eta = ""
        self.msg_queue.put(("refresh", task))
        self.msg_queue.put(("current_task", task))

        cmd = self._build_ffmpeg_cmd(task)
        flags = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
        proc = None
        # 保留 ffmpeg 最后若干行 stderr，供失败时展示
        stderr_tail: deque = deque(maxlen=400)
        try:
            proc = subprocess.Popen(
                cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                text=True, encoding="utf-8", errors="replace", bufsize=1,
                creationflags=flags,
            )
            self.current_proc = proc

            # 必须持续排空 stderr：源文件存在损坏帧时会刷出大量错误日志，
            # Windows 管道缓冲只有数 KB，不及时读取会导致 ffmpeg 写阻塞、整个转码挂死
            def _drain_stderr():
                try:
                    for line in proc.stderr:  # type: ignore
                        stderr_tail.append(line)
                except Exception:
                    pass

            stderr_thread = threading.Thread(target=_drain_stderr, daemon=True)
            stderr_thread.start()

            self._parse_progress(proc, task)
            returncode = proc.wait()
            stderr_thread.join(timeout=3)
            stderr_out = "".join(stderr_tail)

            if self.stop_flag.is_set():
                task.status = "已停止"
            elif returncode == 0:
                task.status = "完成"
                task.progress = 1.0
                if os.path.exists(task.output_path):
                    task.output_size = os.path.getsize(task.output_path)
            else:
                task.status = "错误"
                task.error_msg = f"ffmpeg 返回错误码 {returncode}\n{stderr_out[-1500:]}"
                self.msg_queue.put(("error", "转码失败", task.error_msg))
        except FileNotFoundError:
            task.status = "错误"
            task.error_msg = f"找不到 ffmpeg，请确认文件存在：\n{FFMPEG_CMD}"
            self.msg_queue.put(("error", "转码失败", task.error_msg))
        except Exception as e:
            # 任何异常（含 _parse_progress 抛错）都要确保终止 ffmpeg
            try:
                if proc and proc.poll() is None:
                    proc.terminate()
                    try:
                        proc.wait(timeout=5)
                    except subprocess.TimeoutExpired:
                        proc.kill()
            except Exception:
                pass
            task.status = "错误"
            stderr_out = "".join(stderr_tail)
            if stderr_out:
                task.error_msg = f"{str(e)}\n\nffmpeg 末尾日志：\n{stderr_out[-800:]}"
            else:
                task.error_msg = str(e)
            self.msg_queue.put(("error", "转码失败", task.error_msg))
        finally:
            self.current_proc = None
            task.eta = ""
            task.speed = ""
            self.msg_queue.put(("refresh", task))

    def _parse_progress(self, proc: subprocess.Popen, task: VideoTask):
        kv: dict = {}
        start_wall = time.time()

        for line in proc.stdout:  # type: ignore
            if self.stop_flag.is_set():
                break
            line = line.strip()
            if "=" not in line:
                continue
            key, _, val = line.partition("=")
            kv[key.strip()] = val.strip()

            if key.strip() == "progress":
                try:
                    try:
                        out_time_us_str = kv.get("out_time_us", "0") or "0"
                        out_time_us = int(out_time_us_str)
                    except ValueError:
                        out_time_us = 0
                    current_sec = out_time_us / 1_000_000

                    if task.duration_sec > 0:
                        task.progress = min(current_sec / task.duration_sec, 1.0)
                    task.current_time = current_sec

                    speed_str = kv.get("speed", "")
                    if speed_str and speed_str != "N/A":
                        task.speed = speed_str

                    total_size_str = kv.get("total_size", "0") or "0"
                    try:
                        written = int(total_size_str)
                    except ValueError:
                        written = 0
                    if written > 0 and task.progress > 0.01:
                        task.estimated_size = int(written / task.progress)

                    elapsed = time.time() - start_wall
                    if task.progress > 0.01 and elapsed > 2:
                        remaining = elapsed / task.progress * (1 - task.progress)
                        task.eta = fmt_eta(remaining)

                    self.msg_queue.put(("refresh", task))
                    self.msg_queue.put(("progress_update", task))

                    if val.strip() == "end":
                        task.progress = 1.0
                        break
                except Exception:
                    pass

                kv = {}

    # ── 消息队列轮询（主线程）────────────────────────────────────────────

    def _poll_queue(self):
        try:
            while True:
                msg = self.msg_queue.get_nowait()
                kind = msg[0]
                if kind == "refresh":
                    self._refresh_row(msg[1])
                elif kind == "drop":
                    self._add_dropped(msg[1])
                elif kind == "status_bar":
                    self.status_var.set(msg[1])
                    self.overall_var.set(msg[2])
                elif kind == "done":
                    self._on_all_done()
                elif kind == "current_task":
                    task = msg[1]
                    self.current_file_var.set(f"当前: {Path(task.input_path).name}")
                elif kind == "progress_update":
                    task = msg[1]
                    self.progress_var.set(task.progress * 100)
                    self.progress_text_var.set(f"{task.progress * 100:.1f}%")
                    self.speed_var.set(f"速度: {task.speed or '—'}")
                    self.eta_var.set(f"剩余: {task.eta or '—'}")
                    self.size_var.set(
                        f"预估: {fmt_size(task.estimated_size)}" if task.estimated_size > 0 else ""
                    )
                elif kind == "info":
                    messagebox.showinfo(msg[1], msg[2])
                elif kind == "error":
                    messagebox.showerror(msg[1], msg[2])
        except Empty:
            pass
        self.after(100, self._poll_queue)

    def _on_all_done(self):
        self.running = False
        self.btn_start.state(["!disabled"])
        self.btn_stop.state(["disabled"])

        done = sum(1 for t in self.tasks if t.status == "完成")
        err = sum(1 for t in self.tasks if t.status == "错误")
        skip = sum(1 for t in self.tasks if t.status == "已跳过")

        parts = [f"成功 {done} 个"]
        if skip:
            parts.append(f"跳过 {skip} 个")
        if err:
            parts.append(f"失败 {err} 个")

        self.status_var.set(f"全部完成 — {'，'.join(parts)}")
        self.overall_var.set("")
        self.current_file_var.set("等待开始...")
        self.progress_var.set(0)
        self.progress_text_var.set("")
        self.speed_var.set("")
        self.eta_var.set("")
        self.size_var.set("")


# ── 入口 ──────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    app = App()
    app.mainloop()

