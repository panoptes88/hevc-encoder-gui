"""
HEVC Encoder GUI - Batch H.265/HEVC Video Encoder
Requires: Python 3.8+, ffmpeg (in PATH or ./ffmpeg/ directory)
"""

import tkinter as tk
from tkinter import ttk, filedialog, messagebox
import subprocess
import threading
import os
import re
import json
import time
from pathlib import Path

# Auto-detect ffmpeg
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
from dataclasses import dataclass, field
from typing import List, Optional
from queue import Queue, Empty


# ─────────────────────────── Data Model ───────────────────────────

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
    status: str = "Pending"
    error_msg: str = ""
    speed: str = ""
    eta: str = ""
    codec: str = ""


# ─────────────────────────── FFprobe ──────────────────────────────

def probe_video(path: str) -> tuple[float, int, str]:
    """Returns (duration_sec, file_bytes, codec)"""
    size = os.path.getsize(path) if os.path.exists(path) else 0
    codec = ""
    try:
        cmd = [
            FFPROBE_CMD, "-v", "quiet",
            "-print_format", "json",
            "-show_streams", "-show_format",
            path
        ]
        result = subprocess.run(
            cmd, capture_output=True, text=True, encoding='utf-8', errors='replace', timeout=15,
            creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
        )
        data = json.loads(result.stdout)
        duration = float(data.get("format", {}).get("duration", 0))
        for stream in data.get("streams", []):
            if stream.get("codec_type") == "video":
                codec = stream.get("codec_name", "").upper()
                if codec == "H264":
                    codec = "H.264"
                elif codec == "H265" or codec == "HEVC":
                    codec = "H.265"
                break
        return duration, size, codec
    except Exception:
        return 0.0, size, codec


def fmt_duration(seconds: float) -> str:
    if seconds <= 0:
        return "--:--"
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s = int(seconds % 60)
    if h > 0:
        return f"{h:02d}:{m:02d}:{s:02d}"
    return f"{m:02d}:{s:02d}"


def fmt_size(bytes_val: int) -> str:
    if bytes_val <= 0:
        return "—"
    for unit in ("B", "KB", "MB", "GB"):
        if bytes_val < 1024:
            return f"{bytes_val:.1f} {unit}"
        bytes_val /= 1024
    return f"{bytes_val:.1f} TB"


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


# ─────────────────────────── Build Command ─────────────────────────

def build_ffmpeg_cmd(task: VideoTask) -> List[str]:
    return [
        FFMPEG_CMD, "-hide_banner", "-nostdin",
        "-i", task.input_path,
        "-map", "0:v:0",
        "-c:v", "libx265",
        "-preset", "medium",
        "-crf", "25",
        "-x265-params",
        "colorprim=bt709:transfer=bt709:colormatrix=bt709:range=limited",
        "-map", "0:a:0?",
        "-c:a", "copy",
        "-map_metadata", "0",
        "-movflags", "+faststart",
        "-y",
        task.output_path,
    ]


# ─────────────────────────── Main UI ────────────────────────────────

class App(tk.Tk):
    COL_WIDTHS = {
        "#":       40,
        "File":   220,
        "Codec":   70,
        "Duration":80,
        "Size":    90,
        "Progress":100,
        "Speed":    70,
        "Est.Size": 90,
        "Out Size": 90,
        "Status":   80,
        "ETA":      90,
    }
    COLUMNS = list(COL_WIDTHS.keys())

    def __init__(self):
        super().__init__()
        self.title("HEVC Encoder GUI")
        self.geometry("1100x600")
        self.minsize(900, 480)
        self.configure(bg="#1e1e1e")

        self.tasks: List[VideoTask] = []
        self.running = False
        self.stop_flag = threading.Event()
        self.current_proc: Optional[subprocess.Popen] = None
        self.msg_queue: Queue = Queue()

        self._build_ui()
        self._poll_queue()

    # ── UI Build ───────────────────────────────────────────────────

    def _build_ui(self):
        style = ttk.Style(self)
        style.theme_use("clam")
        style.configure("Treeview",
                        background="#2d2d2d",
                        foreground="#e0e0e0",
                        rowheight=28,
                        fieldbackground="#2d2d2d",
                        font=("Segoe UI", 9))
        style.configure("Treeview.Heading",
                        background="#3c3c3c",
                        foreground="#ffffff",
                        font=("Segoe UI", 9, "bold"))
        style.map("Treeview", background=[("selected", "#0078d4")])
        style.configure("TProgressbar",
                        troughcolor="#3c3c3c",
                        background="#0078d4",
                        thickness=8)
        style.configure("TButton",
                        background="#0078d4",
                        foreground="white",
                        font=("Segoe UI", 10),
                        padding=(12, 6))
        style.map("TButton",
                  background=[("active", "#005a9e"), ("disabled", "#555555")],
                  foreground=[("disabled", "#aaaaaa")])
        style.configure("Danger.TButton",
                        background="#c42b1c",
                        foreground="white",
                        font=("Segoe UI", 10),
                        padding=(12, 6))
        style.map("Danger.TButton",
                  background=[("active", "#8b1a12")])

        # Toolbar
        toolbar = tk.Frame(self, bg="#2d2d2d", pady=8)
        toolbar.pack(fill="x", padx=10, pady=(10, 0))

        ttk.Button(toolbar, text="+ Add Files",
                   command=self._add_files).pack(side="left", padx=4)
        ttk.Button(toolbar, text="Remove Selected",
                   command=self._remove_selected).pack(side="left", padx=4)
        ttk.Button(toolbar, text="Clear All",
                   command=self._clear_all).pack(side="left", padx=4)

        # Output directory
        tk.Label(toolbar, text="  Output:",
                 bg="#2d2d2d", fg="#cccccc",
                 font=("Segoe UI", 9)).pack(side="left")
        self.out_dir_var = tk.StringVar(value="(Same as source)")
        tk.Entry(toolbar, textvariable=self.out_dir_var,
                 width=24, bg="#3c3c3c", fg="#e0e0e0",
                 insertbackground="white", relief="flat",
                 font=("Segoe UI", 9)).pack(side="left", padx=2)
        ttk.Button(toolbar, text="Browse",
                   command=self._pick_out_dir).pack(side="left", padx=2)

        self.btn_start = ttk.Button(toolbar, text="▶  Start",
                                    command=self._start)
        self.btn_start.pack(side="right", padx=4)
        self.btn_stop = ttk.Button(toolbar, text="■  Stop",
                                   command=self._stop,
                                   style="Danger.TButton")
        self.btn_stop.pack(side="right", padx=4)
        self.btn_stop.state(["disabled"])

        # File list
        list_frame = tk.Frame(self, bg="#1e1e1e")
        list_frame.pack(fill="both", expand=True, padx=10, pady=8)

        vsb = ttk.Scrollbar(list_frame, orient="vertical")
        hsb = ttk.Scrollbar(list_frame, orient="horizontal")

        self.tree = ttk.Treeview(
            list_frame,
            columns=self.COLUMNS,
            show="headings",
            yscrollcommand=vsb.set,
            xscrollcommand=hsb.set,
            selectmode="extended"
        )
        vsb.config(command=self.tree.yview)
        hsb.config(command=self.tree.xview)

        for col in self.COLUMNS:
            self.tree.heading(col, text=col)
            self.tree.column(col, width=self.COL_WIDTHS[col],
                             minwidth=30, anchor="center")
        self.tree.column("File", anchor="w")

        vsb.pack(side="right", fill="y")
        hsb.pack(side="bottom", fill="x")
        self.tree.pack(fill="both", expand=True)

        # Drop hint
        self.hint_label = tk.Label(
            list_frame,
            text="Drag & drop video files here, or click Add Files",
            bg="#2d2d2d", fg="#888888",
            font=("Segoe UI", 12)
        )
        self.hint_label.place(relx=0.5, rely=0.5, anchor="center")

        # Status bar
        status_bar = tk.Frame(self, bg="#007acc", height=28)
        status_bar.pack(fill="x", side="bottom")
        self.status_var = tk.StringVar(value="Ready")
        tk.Label(status_bar, textvariable=self.status_var,
                 bg="#007acc", fg="white",
                 font=("Segoe UI", 9),
                 padx=12).pack(side="left", fill="y")

        self.overall_var = tk.StringVar(value="")
        tk.Label(status_bar, textvariable=self.overall_var,
                 bg="#007acc", fg="white",
                 font=("Segoe UI", 9),
                 padx=12).pack(side="right", fill="y")

        # Drag & drop (Windows)
        try:
            self.tree.drop_target_register("DND_Files")  # type: ignore
            self.tree.dnd_bind("<<Drop>>", self._on_drop)  # type: ignore
        except Exception:
            pass

    # ── File Operations ───────────────────────────────────────────

    def _add_files(self):
        paths = filedialog.askopenfilenames(
            title="Select Video Files",
            filetypes=[
                ("Video Files", "*.mp4 *.mkv *.mov *.avi *.ts *.m2ts *.wmv *.flv *.webm"),
                ("All Files", "*.*"),
            ]
        )
        for p in paths:
            self._enqueue_file(p)

    def _on_drop(self, event):
        paths = self.tk.splitlist(event.data)
        for p in paths:
            if os.path.isfile(p):
                self._enqueue_file(p)

    def _enqueue_file(self, path: str):
        for t in self.tasks:
            if t.input_path == path:
                return
        task = VideoTask(input_path=path)
        self.tasks.append(task)
        self._refresh_row(task)
        self.hint_label.place_forget()
        threading.Thread(target=self._probe_task, args=(task,),
                         daemon=True).start()

    def _probe_task(self, task: VideoTask):
        dur, size, codec = probe_video(task.input_path)
        task.duration_sec = dur
        task.input_size = size
        task.codec = codec
        self.msg_queue.put(("refresh", task))

    def _remove_selected(self):
        if self.running:
            return
        for iid in self.tree.selection():
            idx = int(self.tree.item(iid, "values")[0]) - 1
            if 0 <= idx < len(self.tasks):
                self.tasks[idx] = None  # type: ignore
            self.tree.delete(iid)
        self.tasks = [t for t in self.tasks if t is not None]
        self._renumber_all()
        if not self.tasks:
            self.hint_label.place(relx=0.5, rely=0.5, anchor="center")

    def _clear_all(self):
        if self.running:
            return
        self.tasks.clear()
        for iid in self.tree.get_children():
            self.tree.delete(iid)
        self.hint_label.place(relx=0.5, rely=0.5, anchor="center")

    def _pick_out_dir(self):
        d = filedialog.askdirectory(title="Select Output Directory")
        if d:
            self.out_dir_var.set(d)

    # ── Treeview Refresh ────────────────────────────────────────────

    def _row_values(self, task: VideoTask, idx: int):
        progress_text = f"{task.progress*100:.1f}%" if task.progress > 0 else "—"
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
        tag = {"Done": "done", "Error": "err", "Processing": "active", "Skipped": "skip"}.get(task.status, "")
        if tag:
            self.tree.tag_configure("done", foreground="#4ec94e")
            self.tree.tag_configure("err",  foreground="#f47174")
            self.tree.tag_configure("active", foreground="#58c8ff")
            self.tree.tag_configure("skip", foreground="#f4c74e")
            self.tree.item(iid, tags=(tag,))

    def _renumber_all(self):
        for i, task in enumerate(self.tasks):
            iid = str(id(task))
            if self.tree.exists(iid):
                vals = list(self.tree.item(iid, "values"))
                vals[0] = i + 1
                self.tree.item(iid, values=vals)

    # ── Encoding Logic ──────────────────────────────────────────────

    def _get_output_path(self, task: VideoTask) -> str:
        out_dir_str = self.out_dir_var.get().strip()
        src = Path(task.input_path)
        if out_dir_str and out_dir_str != "(Same as source)":
            out_dir = Path(out_dir_str)
        else:
            out_dir = src.parent
        out_name = src.stem + "_hevc.mp4"
        return str(out_dir / out_name)

    def _start(self):
        if not self.tasks:
            messagebox.showinfo("Info", "Please add video files first!")
            return
        for t in self.tasks:
            if t.codec == "H.265" and t.status == "Pending":
                t.status = "Skipped"
                t.progress = 1.0
                self._refresh_row(t)
        pending = [t for t in self.tasks if t.status in ("Pending", "Error")]
        if not pending:
            messagebox.showinfo("Info", "No pending tasks (all completed or already H.265).")
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
        self.status_var.set("Stopped")

    def _run_all(self):
        tasks_to_run = [t for t in self.tasks if t.status in ("Pending", "Error")]
        total = len(tasks_to_run)
        for i, task in enumerate(tasks_to_run):
            if self.stop_flag.is_set():
                break
            self.msg_queue.put(("status_bar",
                                f"Processing {i+1}/{total}: {Path(task.input_path).name}",
                                f"Queue: {i+1}/{total}"))
            self._run_one(task)
        self.msg_queue.put(("done",))

    def _run_one(self, task: VideoTask):
        task.output_path = self._get_output_path(task)
        task.status = "Processing"
        task.progress = 0.0
        task.estimated_size = 0
        task.speed = ""
        task.eta = ""
        self.msg_queue.put(("refresh", task))

        cmd = build_ffmpeg_cmd(task)
        flags = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
        try:
            proc = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                encoding='utf-8',
                errors='replace',
                bufsize=1,
                creationflags=flags
            )
            self.current_proc = proc
            self._parse_progress(proc, task)
            returncode = proc.wait()
            if self.stop_flag.is_set():
                task.status = "Stopped"
            elif returncode == 0:
                task.status = "Done"
                task.progress = 1.0
                if os.path.exists(task.output_path):
                    task.output_size = os.path.getsize(task.output_path)
            else:
                task.status = "Error"
                stderr_out = ""
                try:
                    stderr_out = proc.stderr.read() if proc.stderr else ""
                except Exception as e2:
                    stderr_out = f"<Read failed: {e2}>"
                task.error_msg = f"ffmpeg exited with code {returncode}\n\n{stderr_out[:800] if stderr_out else 'No error details'}"
                messagebox.showerror("Encoding Failed", task.error_msg)
        except FileNotFoundError:
            task.status = "Error"
            task.error_msg = f"ffmpeg not found. Please ensure ffmpeg is installed:\n{FFMPEG_CMD}"
            messagebox.showerror("Encoding Failed", task.error_msg)
        except Exception as e:
            task.status = "Error"
            task.error_msg = str(e)
            messagebox.showerror("Encoding Failed", task.error_msg)
        finally:
            self.current_proc = None
            task.eta = ""
            task.speed = ""
            self.msg_queue.put(("refresh", task))

    def _parse_progress(self, proc: subprocess.Popen, task: VideoTask):
        time_re = re.compile(r"time=(\d+):(\d+):(\d+)\.(\d+)")
        speed_re = re.compile(r"speed=([0-9.]+)x")
        size_re = re.compile(r"size=\s*([0-9]+)kB")

        start_wall = time.time()
        last_refresh = time.time()

        for line in proc.stderr:  # type: ignore
            if self.stop_flag.is_set():
                break

            line = line.strip()

            time_match = time_re.search(line)
            if time_match:
                h = int(time_match.group(1))
                m = int(time_match.group(2))
                s = int(time_match.group(3))
                ms = int(time_match.group(4))
                current_sec = h * 3600 + m * 60 + s + ms / 100
                task.current_time = current_sec

                if task.duration_sec > 0:
                    task.progress = min(current_sec / task.duration_sec, 1.0)

            speed_match = speed_re.search(line)
            if speed_match:
                task.speed = f"{speed_match.group(1)}x"

            size_match = size_re.search(line)
            if size_match and task.progress > 0.01:
                written_kb = int(size_match.group(1))
                written = written_kb * 1024
                task.estimated_size = int(written / task.progress)

            now = time.time()
            if now - last_refresh > 0.5:
                last_refresh = now
                elapsed = now - start_wall
                if task.progress > 0.01 and elapsed > 2:
                    remaining = elapsed / task.progress * (1 - task.progress)
                    task.eta = fmt_eta(remaining)
                self.msg_queue.put(("refresh", task))

    # ── Message Queue ───────────────────────────────────────────────

    def _poll_queue(self):
        try:
            while True:
                msg = self.msg_queue.get_nowait()
                if msg[0] == "refresh":
                    self._refresh_row(msg[1])
                elif msg[0] == "status_bar":
                    self.status_var.set(msg[1])
                    self.overall_var.set(msg[2])
                elif msg[0] == "done":
                    self._on_all_done()
        except Empty:
            pass
        self.after(120, self._poll_queue)

    def _on_all_done(self):
        self.running = False
        self.btn_start.state(["!disabled"])
        self.btn_stop.state(["disabled"])
        done = sum(1 for t in self.tasks if t.status == "Done")
        err = sum(1 for t in self.tasks if t.status == "Error")
        self.status_var.set(f"Done! {done} succeeded" +
                            (f", {err} failed" if err else ""))
        self.overall_var.set("")
        if err:
            failed = [Path(t.input_path).name for t in self.tasks if t.status == "Error"]
            messagebox.showwarning(
                "Some files failed",
                "The following files failed to encode:\n" + "\n".join(failed) +
                "\n\nPlease check the file format or console output."
            )


# ─────────────────────────── Entry Point ─────────────────────────────

if __name__ == "__main__":
    app = App()
    app.mainloop()
