import io
import json
import shlex
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import pdf_translation_bridge as bridge
import translation_pdf_worker as worker


class PathTranslator:
    def __init__(self, fail=False):
        self.fail = fail
        self.calls = []
    def translate(self, text, source, target):
        self.calls.append(text)
        if self.fail:
            raise RuntimeError('unavailable')
        return text.upper()


class CloudTests(unittest.TestCase):
    def test_fallback_skips_failed_path_and_preserves_long_text(self):
        backend = bridge.CloudBackend.__new__(bridge.CloudBackend)
        backend.module = bridge.reference_backend()
        failed, good = PathTranslator(True), PathTranslator()
        backend.paths = [('unavailable', failed), ('available', good)]
        backend.disabled = set()
        backend.used = set()
        original = 'abc' * 1300
        self.assertEqual(backend.translate(original, 'en', 'zh'), original.upper())
        self.assertEqual(len(failed.calls), 1)
        self.assertTrue(all(len(text) <= 900 for text in good.calls))

    def test_explicit_provider_does_not_contact_other_services(self):
        for engine, names in [('google', ['Google']), ('bing', ['Bing']), ('deepl', ['DeepL'])]:
            backend = bridge.CloudBackend(engine)
            self.assertTrue(all(any(name.startswith(prefix) for prefix in names) for name, _ in backend.paths))
            backend.close()

    def test_all_paths_fail_explicitly(self):
        backend = bridge.CloudBackend.__new__(bridge.CloudBackend)
        backend.module = bridge.reference_backend()
        backend.paths = [('failed', PathTranslator(True))]
        backend.disabled = set()
        backend.used = set()
        with self.assertRaisesRegex(RuntimeError, 'unavailable'):
            backend.translate('hello', 'en', 'zh')


class ServerTests(unittest.TestCase):
    def test_real_cli_roundtrip_and_negative_prefix_token(self):
        class FakeBackend:
            def __init__(self, _): pass
            def translate(self, text, source, target): return '译文：' + text
            def close(self): pass
        with patch.object(bridge, 'CloudBackend', FakeBackend), bridge.BackendServer('google', 'en', 'zh') as server:
            server.token = '-token-leading-dash'
            reply = subprocess.run(shlex.split(server.command()), input='Hello\nworld', text=True, capture_output=True)
            self.assertEqual(reply.returncode, 0, reply.stderr)
            self.assertEqual(reply.stdout, '译文：Hello\nworld')
            bad = shlex.split(server.command())
            bad[-1] = '--token=wrong'
            reply = subprocess.run(bad, input='Hello', text=True, capture_output=True)
            self.assertNotEqual(reply.returncode, 0)


class OutputTests(unittest.TestCase):
    def test_pdf_output_modes_and_stale_files(self):
        for mode in ('mono', 'dual', 'both'):
            with tempfile.TemporaryDirectory() as root:
                path = Path(root) / 'input.pdf'
                path.write_bytes(b'input')
                # A previous successful output must be preserved.
                previous = Path(root) / 'input_CN.pdf'
                previous.write_bytes(b'previous')
                staging = Path(root) / 'staging'
                staging.mkdir()
                class FakeProcess:
                    def __init__(self, command, **kwargs):
                        self.stdout = io.StringIO('done\n')
                        self.returncode = 0
                        self.command = command
                        for kind in ('mono', 'dual'):
                            if '--no-' + kind not in command:
                                (staging / f'input.no_watermark.zh.{kind}.pdf').write_bytes(kind.encode())
                    def wait(self, **_): return 0
                    def poll(self): return 0
                with patch.object(worker.subprocess, 'Popen', FakeProcess):
                    result = worker._translate_pdf('pdf2zh', str(path), 'apple', 'zh', mode, 'bridge', str(staging))
                self.assertEqual(len(result), 2 if mode == 'both' else 1)
                self.assertEqual(previous.read_bytes(), b'previous')
                self.assertTrue(all(Path(item).is_file() for item in result))

    def test_cancellation_terminates_the_pdf_process_group(self):
        class InterruptedOutput:
            def __iter__(self):
                raise KeyboardInterrupt
        class RunningProcess:
            pid = 12345
            stdout = InterruptedOutput()
            def __init__(self, *_args, **_kwargs): pass
            def poll(self): return None
            def wait(self, **_kwargs): return 0
        with tempfile.TemporaryDirectory() as root:
            with patch.object(worker.subprocess, 'Popen', RunningProcess), patch.object(worker.os, 'killpg') as stop:
                with self.assertRaises(KeyboardInterrupt):
                    worker._translate_pdf('pdf2zh', str(Path(root) / 'input.pdf'), 'apple', 'zh', 'both', 'bridge', root)
                stop.assert_called_once_with(12345, worker.signal.SIGTERM)

    def test_missing_generated_files_cannot_reuse_previous_translation(self):
        with tempfile.TemporaryDirectory() as root:
            path = Path(root) / 'input.pdf'
            path.write_bytes(b'input')
            (Path(root) / 'input_CN.pdf').write_bytes(b'old')
            staging = Path(root) / 'staging'
            staging.mkdir()
            class FakeProcess:
                stdout = io.StringIO('no output\n')
                def __init__(self, *_args, **_kwargs): pass
                def wait(self): return 0
                def poll(self): return 0
            with patch.object(worker.subprocess, 'Popen', FakeProcess):
                with self.assertRaisesRegex(RuntimeError, 'Expected 2 output files'):
                    worker._translate_pdf('pdf2zh', str(path), 'apple', 'zh', 'both', 'bridge', str(staging))


if __name__ == '__main__':
    unittest.main()
