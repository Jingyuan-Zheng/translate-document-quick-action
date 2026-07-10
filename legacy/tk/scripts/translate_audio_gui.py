import os
import subprocess
import sys
import threading
import tkinter as tk
from tkinter import filedialog, messagebox

try:
    from AppKit import NSApp, NSApplicationActivationPolicyAccessory
except Exception:
    NSApp = None
    NSApplicationActivationPolicyAccessory = None


SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
WORKER_PYTHON = os.environ.get("TRANSLATE_AUDIO_WORKER_PYTHON", sys.executable)
SUPPORTED_EXTENSIONS = (".aac", ".aif", ".aiff", ".flac", ".m4a", ".m4v", ".mov", ".mp3", ".mp4", ".wav")


def resolve_worker_script():
    candidates = [
        os.environ.get("TRANSLATE_AUDIO_WORKER_SCRIPT"),
        os.path.join(SCRIPT_DIR, "translate_audio_worker.py"),
        os.path.join(SCRIPT_DIR, ".translate_audio_worker.py"),
    ]
    for candidate in candidates:
        if candidate and os.path.exists(candidate):
            return candidate
    return candidates[1]


WORKER_SCRIPT = resolve_worker_script()


def bring_window_to_front(root):
    root.lift()
    root.focus_force()
    try:
        root.attributes("-topmost", True)
        root.after(1500, lambda: root.attributes("-topmost", False))
    except tk.TclError:
        pass


class AudioTranslateGUI:
    def __init__(self, root):
        self.root = root
        self.root.title("Transcribe Audio")
        self.root.geometry("760x580")
        self.root.minsize(640, 480)
        self.files = [f for f in sys.argv[1:] if f.lower().endswith(SUPPORTED_EXTENSIONS)]
        self.process = None

        screen_width = root.winfo_screenwidth()
        screen_height = root.winfo_screenheight()
        window_width = 760
        window_height = 580
        x = (screen_width - window_width) // 2
        y = (screen_height - window_height) // 2
        self.root.geometry(f"{window_width}x{window_height}+{x}+{y}")
        bring_window_to_front(self.root)

        main_frame = tk.Frame(root)
        main_frame.pack(padx=10, pady=10, fill="both", expand=True)

        tk.Label(main_frame, text="Selected Audio/Video Files:").grid(row=0, column=0, padx=10, pady=10, sticky="w")
        self.file_entry = tk.Entry(main_frame, width=56)
        self.file_entry.grid(row=0, column=1, padx=10, pady=10, sticky="ew")
        tk.Button(main_frame, text="Browse", command=self.browse_file).grid(row=0, column=2, padx=10, pady=10)

        tk.Label(main_frame, text="Action:").grid(row=1, column=0, padx=10, pady=10, sticky="w")
        self.operation_var = tk.StringVar(value="both")
        operation_frame = tk.Frame(main_frame)
        operation_frame.grid(row=1, column=1, columnspan=2, sticky="w")
        for label, value in [("Transcribe only", "transcribe"), ("Transcribe + translate", "both"), ("Translate output only", "translate")]:
            tk.Radiobutton(operation_frame, text=label, variable=self.operation_var, value=value).pack(side="left", padx=(0, 10))

        tk.Label(main_frame, text="Translation Engine:").grid(row=2, column=0, padx=10, pady=10, sticky="w")
        self.engine_var = tk.StringVar(value=os.environ.get("TRANSLATE_AUDIO_TEXT_ENGINE", "google"))
        engine_frame = tk.Frame(main_frame)
        engine_frame.grid(row=2, column=1, columnspan=2, sticky="w")
        for label, value in [("Google", "google"), ("Bing", "bing"), ("Ollama", "ollama")]:
            tk.Radiobutton(engine_frame, text=label, variable=self.engine_var, value=value).pack(side="left", padx=(0, 10))

        tk.Label(main_frame, text="Target Language:").grid(row=3, column=0, padx=10, pady=10, sticky="w")
        self.language_var = tk.StringVar(value="zh")
        lang_frame = tk.Frame(main_frame)
        lang_frame.grid(row=3, column=1, columnspan=2, sticky="w")
        for label, value in [("Chinese", "zh"), ("English", "en"), ("Japanese", "ja")]:
            tk.Radiobutton(lang_frame, text=label, variable=self.language_var, value=value).pack(side="left", padx=(0, 10))

        tk.Label(main_frame, text="Translation Output:").grid(row=4, column=0, padx=10, pady=10, sticky="w")
        self.mode_var = tk.StringVar(value="dual")
        mode_frame = tk.Frame(main_frame)
        mode_frame.grid(row=4, column=1, columnspan=2, sticky="w")
        for label, value in [("Bilingual", "dual"), ("Monolingual", "mono"), ("Both", "both")]:
            tk.Radiobutton(mode_frame, text=label, variable=self.mode_var, value=value).pack(side="left", padx=(0, 10))

        tk.Label(main_frame, text="MacWhisper Model:").grid(row=5, column=0, padx=10, pady=10, sticky="w")
        self.model_var = tk.StringVar(value=os.environ.get("MACWHISPER_MODEL", ""))
        self.model_entry = tk.Entry(main_frame, textvariable=self.model_var, width=56)
        self.model_entry.grid(row=5, column=1, columnspan=2, padx=10, pady=10, sticky="ew")

        self.stream_var = tk.BooleanVar(value=False)
        tk.Checkbutton(main_frame, text="Stream transcript while transcribing", variable=self.stream_var).grid(
            row=6, column=1, columnspan=2, sticky="w", padx=10, pady=4
        )

        tk.Label(main_frame, text="Program Output:").grid(row=7, column=0, padx=10, pady=10, sticky="w")
        self.output_text = tk.Text(main_frame, height=10, width=66, wrap=tk.WORD)
        self.output_text.grid(row=8, column=0, columnspan=3, padx=10, pady=10, sticky="nsew")
        self.output_text.config(state="disabled")

        scrollbar = tk.Scrollbar(main_frame, orient="vertical", command=self.output_text.yview)
        scrollbar.grid(row=8, column=3, sticky="ns")
        self.output_text.config(yscrollcommand=scrollbar.set)

        self.translate_button = tk.Button(main_frame, text="Start", command=self.translate)
        self.translate_button.grid(row=9, column=1, pady=20)

        main_frame.grid_columnconfigure(1, weight=1)
        main_frame.grid_rowconfigure(8, weight=1)

        if self.files:
            self.file_entry.delete(0, tk.END)
            self.file_entry.insert(0, "; ".join(self.files))
            self.update_output(f"Files received from Automator: {', '.join(self.files)}")

    def browse_file(self):
        file_paths = filedialog.askopenfilenames(
            filetypes=[
                ("Supported Audio/Video", "*.aac *.aif *.aiff *.flac *.m4a *.m4v *.mov *.mp3 *.mp4 *.wav"),
                ("Audio Files", "*.aac *.aif *.aiff *.flac *.m4a *.mp3 *.wav"),
                ("Video Files", "*.m4v *.mov *.mp4"),
            ]
        )
        if file_paths:
            self.files = [f for f in file_paths if f.lower().endswith(SUPPORTED_EXTENSIONS)]
            self.file_entry.delete(0, tk.END)
            self.file_entry.insert(0, "; ".join(self.files))
            self.update_output(f"Files selected: {', '.join(self.files)}")

    def update_output(self, message):
        self.output_text.config(state="normal")
        self.output_text.insert(tk.END, message + "\n")
        self.output_text.see(tk.END)
        self.output_text.config(state="disabled")
        self.root.update_idletasks()

    def translate(self):
        if not self.files:
            messagebox.showerror("Error", "Please select at least one audio or video file!")
            return
        if not os.path.exists(WORKER_SCRIPT):
            messagebox.showerror("Error", f"Worker script does not exist:\n{WORKER_SCRIPT}")
            return
        self.translate_button.config(state="disabled")
        threading.Thread(target=self.run_worker, daemon=True).start()

    def run_worker(self):
        cmd = [
            WORKER_PYTHON,
            WORKER_SCRIPT,
            "--operation",
            self.operation_var.get(),
            "--engine",
            self.engine_var.get(),
            "--lang-out",
            self.language_var.get(),
            "--mode",
            self.mode_var.get(),
        ]
        model = self.model_var.get().strip()
        if model:
            cmd.extend(["--model", model])
        if self.stream_var.get():
            cmd.append("--stream")
        cmd.extend(self.files)
        self.update_output(f"Running command: {' '.join(cmd)}")

        failed = False
        try:
            self.process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                encoding="utf-8",
                errors="replace",
            )
            for line in self.process.stdout:
                self.update_output(line.rstrip())
            failed = self.process.wait() != 0
        except Exception as exc:
            failed = True
            self.update_output(f"Error: {exc}")
        finally:
            self.translate_button.config(state="normal")
            if failed:
                messagebox.showerror("Audio Processing Failed", "Some files failed. See log for details.")
            else:
                messagebox.showinfo("Audio Processing Complete", "Audio processing completed.")


if __name__ == "__main__":
    root = tk.Tk()
    if sys.platform == "darwin" and NSApp is not None:
        try:
            app = NSApp()
            app.setActivationPolicy_(NSApplicationActivationPolicyAccessory)
        except Exception:
            pass
    app = AudioTranslateGUI(root)
    root.mainloop()
