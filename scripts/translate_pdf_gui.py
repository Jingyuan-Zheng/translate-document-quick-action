import tkinter as tk
from tkinter import filedialog, messagebox, ttk
import subprocess
import os
import sys
import re
import shutil
from io import StringIO

# macOS-specific import for hiding Dock icon
if sys.platform == 'darwin':
    try:
        from AppKit import NSApp
        from AppKit import NSApplicationActivationPolicyAccessory
    except Exception:
        NSApp = None
        NSApplicationActivationPolicyAccessory = None
else:
    NSApp = None
    NSApplicationActivationPolicyAccessory = None

PDF2ZH_BIN = os.environ.get("PDF2ZH_NEXT_BIN") or shutil.which("pdf2zh_next")


def bring_window_to_front(root):
    root.lift()
    root.focus_force()
    try:
        root.attributes("-topmost", True)
        root.after(1500, lambda: root.attributes("-topmost", False))
    except tk.TclError:
        pass


LANGUAGE_OUTPUT_CODES = {
    "auto": "AUTO",
    "zh": "CN",
    "zh-cn": "CN",
    "zh-hans": "CN",
    "zh-tw": "TW",
    "zh-hant": "TW",
    "cn": "CN",
    "en": "EN",
    "de": "DE",
    "fr": "FR",
    "es": "ES",
    "it": "IT",
    "pt": "PT",
    "ja": "JA",
    "jp": "JA",
    "ko": "KO",
    "kr": "KO",
    "ru": "RU",
    "uk": "UK",
    "pl": "PL",
    "nl": "NL",
    "sv": "SV",
    "no": "NO",
    "da": "DA",
    "fi": "FI",
    "tr": "TR",
    "ar": "AR",
    "he": "HE",
    "el": "EL",
}
LATIN_LANGUAGE_HINTS = {
    "DE": {"der", "die", "das", "und", "ist", "nicht", "ein", "eine", "mit", "für", "auf", "ich", "sie", "wir"},
    "FR": {"le", "la", "les", "des", "est", "une", "avec", "pour", "dans", "pas", "nous", "vous", "être"},
    "ES": {"el", "la", "los", "las", "que", "para", "con", "una", "por", "como", "esta", "este", "pero"},
    "IT": {"il", "lo", "la", "gli", "che", "per", "con", "una", "sono", "come", "questo", "questa", "non"},
    "PT": {"que", "para", "com", "uma", "não", "como", "esta", "este", "por", "são", "mais", "foi"},
    "EN": {"the", "and", "that", "with", "this", "for", "you", "are", "not", "have", "will", "from", "they", "was"},
}


def output_lang_code(lang):
    normalized = (lang or "auto").strip().lower().replace("_", "-")
    return LANGUAGE_OUTPUT_CODES.get(normalized, normalized.split("-")[0].upper())


def detect_source_lang_code(text):
    sample = text[:20000]
    if not sample.strip():
        return "AUTO"
    counts = {
        "CN": len(re.findall(r"[\u4e00-\u9fff]", sample)),
        "JA": len(re.findall(r"[\u3040-\u30ff]", sample)),
        "KO": len(re.findall(r"[\uac00-\ud7af]", sample)),
        "RU": len(re.findall(r"[\u0400-\u04ff]", sample)),
        "EL": len(re.findall(r"[\u0370-\u03ff]", sample)),
        "AR": len(re.findall(r"[\u0600-\u06ff]", sample)),
        "HE": len(re.findall(r"[\u0590-\u05ff]", sample)),
    }
    lang, count = max(counts.items(), key=lambda item: item[1])
    if count >= 5:
        return lang
    words = re.findall(r"[a-zA-ZÀ-ÿ]+", sample.lower())
    if not words:
        return "AUTO"
    word_counts = {code: sum(1 for word in words if word in hints) for code, hints in LATIN_LANGUAGE_HINTS.items()}
    lang, count = max(word_counts.items(), key=lambda item: item[1])
    if count > 0:
        return lang
    if re.search(r"[äöüß]", sample, re.IGNORECASE):
        return "DE"
    if re.search(r"[àâçéèêëîïôùûüÿœ]", sample, re.IGNORECASE):
        return "FR"
    if re.search(r"[áéíñóúü¿¡]", sample, re.IGNORECASE):
        return "ES"
    return "EN"


def extract_pdf_text(file_path):
    try:
        import fitz

        text_parts = []
        with fitz.open(file_path) as document:
            for page in document[: min(5, document.page_count)]:
                text_parts.append(page.get_text("text"))
        return "\n".join(text_parts)
    except Exception:
        return ""


def output_path(input_path, suffix, ext=".pdf"):
    directory = os.path.dirname(input_path) or "."
    base = os.path.splitext(os.path.basename(input_path))[0]
    candidate = os.path.join(directory, f"{base}{suffix}{ext}")
    if not os.path.exists(candidate):
        return candidate
    index = 1
    while True:
        candidate = os.path.join(directory, f"{base}{suffix}.{index}{ext}")
        if not os.path.exists(candidate):
            return candidate
        index += 1


class PDFTranslateGUI:
    def __init__(self, root):
        self.root = root
        self.root.title("Translate PDF")
        self.root.geometry("700x550")
        self.root.minsize(600, 450)

        # Center the window
        screen_width = root.winfo_screenwidth()
        screen_height = root.winfo_screenheight()
        window_width = 700
        window_height = 550
        x = (screen_width - window_width) // 2
        y = (screen_height - window_height) // 2
        self.root.geometry(f"{window_width}x{window_height}+{x}+{y}")
        bring_window_to_front(self.root)

        # Main frame with padding
        main_frame = tk.Frame(root)
        main_frame.pack(padx=10, pady=10, fill="both", expand=True)

        # File selection
        tk.Label(main_frame, text="Selected PDF Files:").grid(row=0, column=0, padx=10, pady=10, sticky="w")
        self.file_entry = tk.Entry(main_frame, width=50)
        self.file_entry.grid(row=0, column=1, padx=10, pady=10, sticky="w")
        tk.Button(main_frame, text="Browse", command=self.browse_file).grid(row=0, column=2, padx=10, pady=10)

        # Translation Engine selection
        tk.Label(main_frame, text="Translation Engine:").grid(row=1, column=0, padx=10, pady=10, sticky="w")
        self.engine_var = tk.StringVar(value="google")
        engine_frame = tk.Frame(main_frame)
        engine_frame.grid(row=1, column=1, columnspan=2, sticky="w")
        tk.Radiobutton(engine_frame, text="Google", variable=self.engine_var, value="google").pack(side="left")
        tk.Radiobutton(engine_frame, text="Bing", variable=self.engine_var, value="bing").pack(side="left", padx=10)
        
        # Language selection
        tk.Label(main_frame, text="Target Language:").grid(row=2, column=0, padx=10, pady=10, sticky="w")
        self.language_var = tk.StringVar(value="zh")
        lang_frame = tk.Frame(main_frame)
        lang_frame.grid(row=2, column=1, columnspan=2, sticky="w")
        tk.Radiobutton(lang_frame, text="Chinese", variable=self.language_var, value="zh").pack(side="left")
        tk.Radiobutton(lang_frame, text="English", variable=self.language_var, value="en").pack(side="left", padx=10)

        # Mode selection
        tk.Label(main_frame, text="Translation Mode:").grid(row=3, column=0, padx=10, pady=10, sticky="w")
        self.mode_var = tk.StringVar(value="both")
        mode_frame = tk.Frame(main_frame)
        mode_frame.grid(row=3, column=1, columnspan=2, sticky="w")
        tk.Radiobutton(mode_frame, text="Bilingual", variable=self.mode_var, value="dual").pack(side="left")
        tk.Radiobutton(mode_frame, text="Monolingual", variable=self.mode_var, value="mono").pack(side="left", padx=10)
        tk.Radiobutton(mode_frame, text="Both", variable=self.mode_var, value="both").pack(side="left", padx=10)

        # Output log
        tk.Label(main_frame, text="Program Output:").grid(row=4, column=0, padx=10, pady=10, sticky="w")
        self.output_text = tk.Text(main_frame, height=10, width=60, wrap=tk.WORD)
        self.output_text.grid(row=5, column=0, columnspan=3, padx=10, pady=10, sticky="nsew")
        self.output_text.config(state="disabled")

        # Scrollbar for output text
        scrollbar = tk.Scrollbar(main_frame, orient="vertical", command=self.output_text.yview)
        scrollbar.grid(row=5, column=3, sticky="ns")
        self.output_text.config(yscrollcommand=scrollbar.set)

        # Translate button
        tk.Button(main_frame, text="Translate", command=self.translate).grid(row=6, column=1, pady=20)

        # Configure grid weights for resizing
        main_frame.grid_columnconfigure(1, weight=1)
        main_frame.grid_rowconfigure(5, weight=1)

        # Check for files passed via Automator
        self.files = [f for f in sys.argv[1:] if f.lower().endswith('.pdf')]
        if self.files:
            self.file_entry.delete(0, tk.END)
            self.file_entry.insert(0, "; ".join(self.files))
            self.update_output(f"Files received from Automator: {', '.join(self.files)}")

    def browse_file(self):
        file_paths = filedialog.askopenfilenames(filetypes=[("PDF Files", "*.pdf")])
        if file_paths:
            self.files = list(file_paths)
            self.file_entry.delete(0, tk.END)
            self.file_entry.insert(0, "; ".join(self.files))
            self.update_output(f"Files selected: {', '.join(self.files)}")

    def update_output(self, message):
        self.output_text.config(state="normal")
        self.output_text.insert(tk.END, message + "\n")
        self.output_text.see(tk.END)
        self.output_text.config(state="disabled")
        self.root.update()

    def translate(self):
        if not hasattr(self, 'files') or not self.files:
            messagebox.showerror("Error", "Please select at least one PDF file!")
            return
        if not PDF2ZH_BIN:
            messagebox.showerror("Error", "pdf2zh_next was not found. Install pdf2zh-next or set PDF2ZH_NEXT_BIN.")
            return

        target_language = self.language_var.get()
        mode = self.mode_var.get()
        engine = self.engine_var.get()
        
        # Store translation results
        success_messages = []
        failed_files = []

        for file_path in self.files:
            if not os.path.exists(file_path):
                self.update_output(f"Error: File does not exist: {file_path}")
                failed_files.append(file_path)
                continue

            # Output directory is the same as input file
            output_dir = os.path.dirname(file_path) or "."
            base_name = os.path.splitext(os.path.basename(file_path))[0]
            
            source_code = detect_source_lang_code(extract_pdf_text(file_path))
            target_code = output_lang_code(target_language)
            dual_output = output_path(file_path, f"_{source_code}_{target_code}", ".pdf")
            mono_output = output_path(file_path, f"_{target_code}", ".pdf")

            # Redirect stdout and stderr
            output_buffer = StringIO()
            sys.stdout = output_buffer
            sys.stderr = output_buffer

            try:
                self.update_output(f"\nTranslating: {file_path}")
                cmd = [
                    PDF2ZH_BIN,
                    file_path,
                    "--lang-out", target_language,
                    "--translate-table-text",
                    "--skip-scanned-detection",
                    "--enhance-compatibility",
                    "--output", output_dir
                ]
                
                # Add translation engine
                if engine == "google":
                    cmd.append("--google")
                elif engine == "bing":
                    cmd.append("--bing")
                
                self.update_output(f"Running command: {' '.join(cmd)}")
                
                process = subprocess.Popen(
                    cmd, 
                    stdout=subprocess.PIPE, 
                    stderr=subprocess.STDOUT, 
                    text=True,
                    encoding='utf-8',
                    errors='replace'
                )
                
                # Real-time output
                while True:
                    line = process.stdout.readline()
                    if not line and process.poll() is not None:
                        break
                    if line:
                        self.update_output(line.strip())
                        sys.stdout.write(line)

                return_code = process.wait()

                # Restore standard output
                sys.stdout = sys.__stdout__
                sys.stderr = sys.__stderr__

                # Get full output for debugging
                full_output = output_buffer.getvalue()
                
                # Check for generated files
                generated_files = []
                
                # Possible output filenames from pdf2zh_next
                possible_dual_files = [
                    os.path.join(output_dir, f"{base_name}.no_watermark.{target_language}.dual.pdf"),
                    os.path.join(output_dir, f"{base_name}.dual.pdf"),
                    dual_output
                ]
                possible_mono_files = [
                    os.path.join(output_dir, f"{base_name}.no_watermark.{target_language}.mono.pdf"),
                    os.path.join(output_dir, f"{base_name}.mono.pdf"),
                    mono_output
                ]

                if mode in ["dual", "both"]:
                    for f in possible_dual_files:
                        if os.path.exists(f):
                            try:
                                if f != dual_output:
                                    os.rename(f, dual_output)
                                    self.update_output(f"Renamed {os.path.basename(f)} to {os.path.basename(dual_output)}")
                                generated_files.append(dual_output)
                            except OSError as e:
                                self.update_output(f"Error renaming {f}: {str(e)}")
                            break
                
                if mode in ["mono", "both"]:
                    for f in possible_mono_files:
                        if os.path.exists(f):
                            try:
                                if f != mono_output:
                                    os.rename(f, mono_output)
                                    self.update_output(f"Renamed {os.path.basename(f)} to {os.path.basename(mono_output)}")
                                generated_files.append(mono_output)
                            except OSError as e:
                                self.update_output(f"Error renaming {f}: {str(e)}")
                            break
                
                # Verify if files were generated
                if generated_files:
                    success_msg = f"Success: Generated files for '{os.path.basename(file_path)}' using {engine.upper()} engine:"
                    for f in generated_files:
                        success_msg += f"\n  • {os.path.basename(f)}"
                    success_messages.append(success_msg)
                    self.update_output(success_msg)
                else:
                    failed_files.append(file_path)
                    error_msg = f"Error: No output files generated for {file_path} using {engine.upper()} engine"
                    self.update_output(error_msg)
                    self.update_output("Command output:")
                    self.update_output(full_output)
                    # Debug: List files in output directory
                    dir_contents = os.listdir(output_dir)
                    self.update_output(f"Output directory contents: {', '.join(dir_contents)}")

            except Exception as e:
                failed_files.append(file_path)
                self.update_output(f"Error: {str(e)}")
                sys.stdout = sys.__stdout__
                sys.stderr = sys.__stderr__

            finally:
                # Ensure standard output is always restored
                sys.stdout = sys.__stdout__
                sys.stderr = sys.__stderr__

        # Display summary
        if success_messages or failed_files:
            summary = "Translation Summary:\n\n"
            
            if success_messages:
                summary += "✓ Successfully translated:\n"
                for msg in success_messages:
                    file_name = msg.split("'")[1]
                    summary += f"  - {file_name}\n"
            
            if failed_files:
                summary += "\n✗ Failed to translate:\n"
                for file_path in failed_files:
                    file_name = os.path.basename(file_path)
                    summary += f"  - {file_name}\n"
                summary += "\nSee log for details."
            
            messagebox.showinfo("Translation Complete", summary)

if __name__ == "__main__":
    root = tk.Tk()
    
    # Hide Dock icon (macOS only)
    if sys.platform == 'darwin' and NSApp is not None:
        try:
            app = NSApp()
            app.setActivationPolicy_(NSApplicationActivationPolicyAccessory)
        except Exception as e:
            print(f"Error setting activation policy: {e}")
    
    app = PDFTranslateGUI(root)
    root.mainloop()
