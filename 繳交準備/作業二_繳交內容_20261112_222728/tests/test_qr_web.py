import json
import tempfile
import threading
import unittest
import urllib.request
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
import qr_web

class QRTests(unittest.TestCase):
    def test_url_validation(self):
        for value in ('', 'javascript:alert(1)', 'https://', 'http://a b'):
            with self.subTest(value=value), self.assertRaises(ValueError):
                qr_web.validate_url(value)
        self.assertEqual(qr_web.validate_url('https://example.com/a?q=1'), 'https://example.com/a?q=1')

    def test_make_decode_and_comparison(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / 'label.png'
            result = qr_web.make_qr('https://example.com/test', path, 'H', 'Example')
            self.assertTrue(path.is_file())
            self.assertEqual(result['decoded'], 'https://example.com/test')
            self.assertTrue(result['matches'])
            self.assertEqual(result['modules'], 17 + 4 * result['version'])
            self.assertGreater(result['bytes'], 0)
            self.assertEqual(qr_web.decode_image(path), 'https://example.com/test')

    def test_all_levels_are_generated_and_decoded(self):
        with tempfile.TemporaryDirectory() as d:
            rows = qr_web.compare_levels('https://example.com/', Path(d))
            self.assertEqual([r['level'] for r in rows], list('LMQH'))
            self.assertTrue(all(r['matches'] for r in rows))
            self.assertEqual(len(list(Path(d).glob('*.png'))), 4)

    def test_missing_image_is_error(self):
        with self.assertRaises(ValueError):
            qr_web.decode_image(Path('/not/a/real/qr.png'))

class ServerTests(unittest.TestCase):
    def test_request_log_includes_all_requests_and_agent(self):
        with tempfile.TemporaryDirectory() as d:
            site = Path(d) / 'site'; site.mkdir()
            (site / 'index.html').write_text('hello', encoding='utf-8')
            log = Path(d) / 'connections.jsonl'
            server = qr_web.create_server('127.0.0.1', 0, site, log)
            thread = threading.Thread(target=server.serve_forever, daemon=True); thread.start()
            try:
                url = f'http://127.0.0.1:{server.server_port}/'
                for path in ('', 'missing'):
                    try:
                        with urllib.request.urlopen(urllib.request.Request(url + path, headers={'User-Agent':'TestAgent'})) as response:
                            response.read()
                    except urllib.error.HTTPError as exc:
                        exc.close()
            finally:
                server.shutdown(); thread.join(); server.server_close()
            records = [json.loads(line) for line in log.read_text().splitlines()]
            self.assertEqual(len(records), 2)
            self.assertEqual([r['status'] for r in records], [200, 404])
            self.assertTrue(all(r['ip'] == '127.0.0.1' and r['user_agent'] == 'TestAgent' and r['time'] for r in records))

if __name__ == '__main__':
    unittest.main()
