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
WORKER_PYTHON = os.environ.get("TRANSLATE_IMAGE_WORKER_PYTHON", sys.executable)
WORKER_SCRIPT = os.environ.get("TRANSLATE_IMAGE_WORKER_SCRIPT", os.path.join(SCRIPT_DIR, "translate_image_worker.py"))
SUPPORTED_EXTENSIONS = (".png", ".jpg", ".jpeg", ".webp", ".bmp", ".tif", ".tiff")


class ImageTranslateGUI:
    def __init__(self, root):
        self.root = root
        self.root.title("Translate Image")
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

        main_frame = tk.Frame(root)
        main_frame.pack(padx=10, pady=10, fill="both", expand=True)

        tk.Label(main_frame, text="Selected Image Files:").grid(row=0, column=0, padx=10, pady=10, sticky="w")
        self.file_entry = tk.Entry(main_frame, width=56)
        self.file_entry.grid(row=0, column=1, padx=10, pady=10, sticky="ew")
        tk.Button(main_frame, text="Browse", command=self.browse_file).grid(row=0, column=2, padx=10, pady=10)

        tk.Label(main_frame, text="Source Language:").grid(row=1, column=0, padx=10, pady=10, sticky="w")
        self.source_var = tk.StringVar(value="auto")
        source_frame = tk.Frame(main_frame)
        source_frame.grid(row=1, column=1, columnspan=2, sticky="w")
        for label, value in [("Auto", "auto"), ("English", "en"), ("Japanese", "ja"), ("Chinese", "zh")]:
            tk.Radiobutton(source_frame, text=label, variable=self.source_var, value=value).pack(side="left", padx=(0, 10))

        tk.Label(main_frame, text="Target Language:").grid(row=2, column=0, padx=10, pady=10, sticky="w")
        self.language_var = tk.StringVar(value="zh")
        lang_frame = tk.Frame(main_frame)
        lang_frame.grid(row=2, column=1, columnspan=2, sticky="w")
        tk.Radiobutton(lang_frame, text="Chinese", variable=self.language_var, value="zh").pack(side="left")
        tk.Radiobutton(lang_frame, text="English", variable=self.language_var, value="en").pack(side="left", padx=10)
        tk.Radiobutton(lang_frame, text="Japanese", variable=self.language_var, value="ja").pack(side="left", padx=10)

        tk.Label(main_frame, text="Translation Mode:").grid(row=3, column=0, padx=10, pady=10, sticky="w")
        self.mode_var = tk.StringVar(value="both")
        mode_frame = tk.Frame(main_frame)
        mode_frame.grid(row=3, column=1, columnspan=2, sticky="w")
        tk.Radiobutton(mode_frame, text="Bilingual", variable=self.mode_var, value="dual").pack(side="left")
        tk.Radiobutton(mode_frame, text="Monolingual", variable=self.mode_var, value="mono").pack(side="left", padx=10)
        tk.Radiobutton(mode_frame, text="Both", variable=self.mode_var, value="both").pack(side="left", padx=10)

        tk.Label(main_frame, text="Image Backend:").grid(row=4, column=0, padx=10, pady=10, sticky="w")
        self.image_engine_var = tk.StringVar(value=os.environ.get("TRANSLATE_IMAGE_ENGINE", "simple-macos"))
        engine_frame = tk.Frame(main_frame)
        engine_frame.grid(row=4, column=1, columnspan=2, sticky="w")
        tk.Radiobutton(engine_frame, text="Simple macOS OCR", variable=self.image_engine_var, value="simple-macos").pack(side="left")
        tk.Radiobutton(engine_frame, text="Manga Translator", variable=self.image_engine_var, value="manga").pack(side="left", padx=10)

        tk.Label(main_frame, text="Text Engine:").grid(row=5, column=0, padx=10, pady=10, sticky="w")
        self.text_engine_var = tk.StringVar(value=os.environ.get("TRANSLATE_IMAGE_TEXT_ENGINE", "google"))
        text_engine_frame = tk.Frame(main_frame)
        text_engine_frame.grid(row=5, column=1, columnspan=2, sticky="w")
        for label, value in [("Google", "google"), ("Bing", "bing"), ("Ollama", "ollama")]:
            tk.Radiobutton(text_engine_frame, text=label, variable=self.text_engine_var, value=value).pack(side="left", padx=(0, 10))

        tk.Label(main_frame, text="Manga Backend:").grid(row=6, column=0, padx=10, pady=10, sticky="w")
        self.backend_var = tk.StringVar(value=os.environ.get("MANGA_TRANSLATOR_BACKEND", "offline"))
        backend_frame = tk.Frame(main_frame)
        backend_frame.grid(row=6, column=1, columnspan=2, sticky="w")
        for label, value in [("Offline", "offline"), ("Custom OpenAI", "custom_openai"), ("ChatGPT", "chatgpt"), ("DeepL", "deepl")]:
            tk.Radiobutton(backend_frame, text=label, variable=self.backend_var, value=value).pack(side="left", padx=(0, 10))

        self.use_gpu_var = tk.BooleanVar(value=False)
        tk.Checkbutton(main_frame, text="Use GPU if available", variable=self.use_gpu_var).grid(
            row=7, column=1, columnspan=2, sticky="w", padx=10, pady=4
        )

        tk.Label(main_frame, text="Program Output:").grid(row=8, column=0, padx=10, pady=10, sticky="w")
        self.output_text = tk.Text(main_frame, height=10, width=66, wrap=tk.WORD)
        self.output_text.grid(row=9, column=0, columnspan=3, padx=10, pady=10, sticky="nsew")
        self.output_text.config(state="disabled")

        scrollbar = tk.Scrollbar(main_frame, orient="vertical", command=self.output_text.yview)
        scrollbar.grid(row=9, column=3, sticky="ns")
        self.output_text.config(yscrollcommand=scrollbar.set)

        self.translate_button = tk.Button(main_frame, text="Translate", command=self.translate)
        self.translate_button.grid(row=10, column=1, pady=20)

        main_frame.grid_columnconfigure(1, weight=1)
        main_frame.grid_rowconfigure(9, weight=1)

        if self.files:
            self.file_entry.delete(0, tk.END)
            self.file_entry.insert(0, "; ".join(self.files))
            self.update_output(f"Files received from Automator: {', '.join(self.files)}")

    def browse_file(self):
        file_paths = filedialog.askopenfilenames(
            filetypes=[
                ("Supported Images", "*.png *.jpg *.jpeg *.webp *.bmp *.tif *.tiff"),
                ("PNG", "*.png"),
                ("JPEG", "*.jpg *.jpeg"),
                ("WebP", "*.webp"),
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
            messagebox.showerror("Error", "Please select at least one image file!")
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
            "--lang-in",
            self.source_var.get(),
            "--lang-out",
            self.language_var.get(),
            "--mode",
            self.mode_var.get(),
            "--image-engine",
            self.image_engine_var.get(),
            "--text-engine",
            self.text_engine_var.get(),
            "--mit-translator",
            self.backend_var.get(),
            *self.files,
        ]
        if self.use_gpu_var.get():
            cmd.insert(-len(self.files), "--use-gpu")
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
                messagebox.showerror("Translation Failed", "Some images failed to translate. See log for details.")
            else:
                messagebox.showinfo("Translation Complete", "Image translation completed.")


if __name__ == "__main__":
    root = tk.Tk()
    if sys.platform == "darwin" and NSApp is not None:
        try:
            app = NSApp()
            app.setActivationPolicy_(NSApplicationActivationPolicyAccessory)
        except Exception:
            pass
    app = ImageTranslateGUI(root)
    root.mainloop()
