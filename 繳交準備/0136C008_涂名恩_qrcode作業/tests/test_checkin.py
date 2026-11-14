import json
from pathlib import Path
import sys
import tempfile
import threading
import unittest
import urllib.error
import urllib.parse
import urllib.request

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
import qr_web


class CheckinTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        root = Path(self.temp.name)
        site = root / 'site'
        site.mkdir()
        (site / 'index.html').write_text('public page')
        self.root = root
        self.server = qr_web.create_server('127.0.0.1', 0, site, root / 'connections_test.jsonl')
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.base = f'http://127.0.0.1:{self.server.server_port}'

    def tearDown(self):
        self.server.shutdown()
        self.thread.join()
        self.server.server_close()
        self.temp.cleanup()

    def post(self, payload):
        request = urllib.request.Request(self.base + '/api/checkin', data=json.dumps(payload).encode(),
            headers={'Content-Type': 'application/json', 'X-Forwarded-For': '1.2.3.4'})
        return urllib.request.urlopen(request)

    def test_checkin_records_model_and_actual_source_ip(self):
        with self.post({'model': '  iPad Air M6  ', 'ip': '9.9.9.9'}) as response:
            data = json.load(response)
        self.assertEqual(data['ip'], '127.0.0.1')
        with urllib.request.urlopen(self.base + '/api/checkins') as response:
            records = json.load(response)['records']
        self.assertEqual(len(records), 1)
        self.assertEqual(records[0]['model'], 'iPad Air M6')
        self.assertEqual(records[0]['ip'], '127.0.0.1')
        self.assertTrue(records[0]['time'])
        with urllib.request.urlopen(self.base + '/api/checkins?start=2099-01-01T00%3A00%3A00%2B00%3A00') as response:
            self.assertEqual(json.load(response)['records'], [])
        request = urllib.request.Request(self.base + '/api/checkins', headers={'Host': 'evil.example'})
        with self.assertRaises(urllib.error.HTTPError) as error:
            urllib.request.urlopen(request)
        self.assertEqual(error.exception.code, 403)

    def test_rejects_bad_models_without_creating_checkin(self):
        for model in ('', '   ', 'x' * 81, 'a\nb', 5):
            with self.subTest(model=model):
                with self.assertRaises(urllib.error.HTTPError) as error:
                    self.post({'model': model})
                self.assertEqual(error.exception.code, 400)
        with urllib.request.urlopen(self.base + '/api/checkins') as response:
            self.assertEqual(json.load(response)['records'], [])

    def test_admin_endpoint_head_is_not_exposed(self):
        request = urllib.request.Request(self.base + '/api/checkins', method='HEAD', headers={'Host': 'evil.example'})
        with self.assertRaises(urllib.error.HTTPError) as error:
            urllib.request.urlopen(request)
        self.assertEqual(error.exception.code, 403)

if __name__ == '__main__':
    unittest.main()
