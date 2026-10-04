"""Resident translation backends exposed only to authenticated loopback clients."""
from __future__ import annotations

import argparse
import contextlib
import importlib.util
import json
import os
from pathlib import Path
import queue
import secrets
import subprocess
import sys
import threading
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

DEFAULT_MODEL = os.environ.get('TRANSLATE_TEXT_MODEL', '')


def reference_backend():
    path = Path(__file__).parent / 'vendor/translate_text_backend.py'
    spec = importlib.util.spec_from_file_location('pdf_reference_backend', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    # The reference worker emits GUI events; route status to the PDF log instead.
    module.emit = lambda event, **payload: print(payload.get('text', event), file=sys.stderr, flush=True)
    return module


class AppleBackend:
    def __init__(self, source, target):
        helper = Path(__file__).parent.parent / 'Service Tools.app/Contents/Helpers/Apple PDF Translator.app/Contents/MacOS/ApplePDFTranslator'
        override = os.environ.get('PDF_APPLE_HELPER')
        if override:
            helper = Path(override)
        if not helper.is_file():
            raise RuntimeError('Apple PDF Translator helper is missing. Rebuild Service Tools.')
        self.process = subprocess.Popen([str(helper), '--source', source, '--target', target],
                                        stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                        text=True, encoding='utf-8')
        self.responses = queue.Queue()
        self.reader = threading.Thread(target=self._read, daemon=True)
        self.reader.start()
        try:
            reply = self.responses.get(timeout=300)
            if reply.get('event') != 'ready':
                raise RuntimeError(reply.get('error', 'Apple translation could not start.'))
        except Exception:
            self.close()
            raise

    def _read(self):
        for line in self.process.stdout:
            try:
                self.responses.put(json.loads(line))
            except json.JSONDecodeError:
                continue
        self.responses.put({'error': 'Apple translation helper exited.'})

    def translate(self, text):
        self.process.stdin.write(json.dumps({'text': text}, ensure_ascii=False) + '\n')
        self.process.stdin.flush()
        try:
            reply = self.responses.get(timeout=240)
        except queue.Empty:
            self.close()
            raise RuntimeError('Apple translation timed out; run the workflow again.')
        if 'error' in reply:
            raise RuntimeError(reply['error'])
        return reply['text']

    def close(self):
        if self.process.poll() is None:
            self.process.stdin.close()
            try:
                self.process.wait(timeout=3)
            except subprocess.TimeoutExpired:
                self.process.terminate()
                self.process.wait(timeout=3)


class CloudBackend:
    def __init__(self, engine):
        self.module = reference_backend()
        worker = self.module.TranslateWorker()
        services = {
            'google': worker._google_translator_chain(),
            'bing': [('Bing EPT', worker.get_cloud_translator('bing_ept')),
                     ('Bing web', worker.get_cloud_translator('bing'))],
            'deepl': [('DeepL web', worker.get_cloud_translator('deepl'))],
        }
        order = ['google', 'bing', 'deepl'] if engine == 'cloud' else [engine]
        self.paths = [entry for service in order for entry in services[service]]
        self.disabled = set()
        self.used = set()

    def translate(self, text, source, target):
        output = []
        # Stay below Bing's 1,000-character limit on every fallback path.
        for chunk in self.module.chunk_text(text, 900):
            for name, translator in self.paths:
                if name in self.disabled:
                    continue
                try:
                    result = translator.translate(chunk, source, target)
                    if not result.strip():
                        raise RuntimeError('Empty translation')
                    if name not in self.used:
                        print(f"Using {name}.", file=sys.stderr, flush=True)
                        self.used.add(name)
                    output.append(result)
                    break
                except Exception as exc:
                    self.disabled.add(name)
                    # Do not print exception URLs: they can include document text.
                    print(f'{name} unavailable ({type(exc).__name__}); trying the next path.', file=sys.stderr, flush=True)
            else:
                raise RuntimeError('Selected cloud translation paths are unavailable. Try Apple, another engine, or retry later.')
        return ''.join(output)

    def close(self):
        for _, translator in self.paths:
            session = getattr(translator, 'session', None)
            if session:
                session.close()


class GemmaBackend:
    def __init__(self, model):
        if not model or not Path(model).is_dir():
            raise RuntimeError('Choose a local TranslateGemma MLX model folder before translating.')
        from mlx_lm import load, stream_generate
        self.model, self.tokenizer = load(model)
        self.tokenizer.add_eos_token("<end_of_turn>")
        print("TranslateGemma model loaded.", flush=True)
        self.stream_generate = stream_generate

    def translate(self, text, source, target):
        payload = {'type': 'text', 'source_lang_code': source, 'target_lang_code': target,
                   'text': text, 'image': None}
        prompt = self.tokenizer.apply_chat_template([{'role': 'user', 'content': [payload]}],
                                                   tokenize=False, add_generation_prompt=True)
        output = []
        # Translation must complete; never silently return a token-limit truncation.
        for result in self.stream_generate(self.model, self.tokenizer, prompt, max_tokens=max(256, min(4096, len(text) * 4))):
            output.append(result.text)
            if getattr(result, 'finish_reason', None) == 'length':
                raise RuntimeError('TranslateGemma reached its output limit. Split the source paragraph into smaller sections.')
        return ''.join(output).strip()

    def close(self):
        self.model = self.tokenizer = None


class BackendServer:
    def __init__(self, engine, source, target, model=DEFAULT_MODEL):
        self.source, self.target = source, target
        self.token = secrets.token_urlsafe(32)
        self.lock = threading.Lock()
        print(f'Preparing {engine} translation backend...', flush=True)
        if engine == 'apple':
            self.backend = AppleBackend(source, target)
        elif engine == 'gemma':
            self.backend = GemmaBackend(model)
        else:
            self.backend = CloudBackend(engine)
        owner = self

        class Handler(BaseHTTPRequestHandler):
            def do_POST(self):
                if self.path != '/translate' or self.headers.get('Authorization') != 'Bearer ' + owner.token:
                    self.send_error(403)
                    return
                try:
                    length = int(self.headers.get('Content-Length', '0'))
                    if not 0 < length <= 2_000_000:
                        raise ValueError('Invalid request size')
                    text = json.loads(self.rfile.read(length))['text']
                    if not isinstance(text, str):
                        raise ValueError('Text must be a string')
                    with owner.lock:
                        if isinstance(owner.backend, AppleBackend):
                            result = owner.backend.translate(text)
                        else:
                            result = owner.backend.translate(text, owner.source, owner.target)
                    payload = json.dumps({'text': result}, ensure_ascii=False).encode('utf-8')
                    self.send_response(200)
                except Exception as exc:
                    print(f'Translation failed: {exc}', file=sys.stderr, flush=True)
                    payload = json.dumps({'error': str(exc)}).encode('utf-8')
                    self.send_response(502)
                self.send_header('Content-Type', 'application/json')
                self.send_header('Content-Length', str(len(payload)))
                self.end_headers()
                self.wfile.write(payload)

            def log_message(self, *_):
                pass

        try:
            self.server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
            self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
            self.thread.start()
        except Exception:
            self.backend.close()
            raise

    def command(self):
        import shlex
        return shlex.join([sys.executable, str(Path(__file__).resolve()), '--port',
                           str(self.server.server_port), '--token=' + self.token])

    def close(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=3)
        self.backend.close()

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.close()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--port', type=int, required=True)
    parser.add_argument('--token', required=True)
    args = parser.parse_args()
    data = json.dumps({'text': sys.stdin.read()}, ensure_ascii=False).encode('utf-8')
    request = urllib.request.Request(f'http://127.0.0.1:{args.port}/translate', data=data,
                                     headers={'Content-Type': 'application/json', 'Authorization': 'Bearer ' + args.token})
    # Loopback requests must never follow HTTP_PROXY/HTTPS_PROXY settings.
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    try:
        with opener.open(request, timeout=250) as response:
            print(json.load(response)['text'], end='')
    except Exception:
        print('Translation backend failed. See the PDF workflow log for details.', file=sys.stderr)
        return 1
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
