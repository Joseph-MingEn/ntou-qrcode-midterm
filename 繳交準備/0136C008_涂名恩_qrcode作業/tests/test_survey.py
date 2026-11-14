import json
from pathlib import Path
import sys
import tempfile
import threading
import unittest
import urllib.error
import urllib.request

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
import qr_web


class SurveyTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        root = Path(self.temp.name)
        self.root = root
        site = root / 'site'
        site.mkdir()
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
        request = urllib.request.Request(self.base + '/api/survey', data=json.dumps(payload).encode('utf-8'),
                                         headers={'Content-Type': 'application/json'})
        return urllib.request.urlopen(request)

    def test_submit_and_retrieve_in_local_dashboard(self):
        with self.post({'rating': '滿意', 'comment': '畫面清楚\n謝謝'}) as res:
            result = json.load(res)
        self.assertTrue(result['time'])
        with urllib.request.urlopen(self.base + '/api/surveys') as res:
            data = json.load(res)
        self.assertEqual(data['total'], 1)
        self.assertEqual(data['records'][0]['rating'], '滿意')
        self.assertEqual(data['records'][0]['comment'], '畫面清楚\n謝謝')
        with urllib.request.urlopen(self.base + '/api/surveys?start=2099-01-01T00%3A00%3A00%2B00%3A00') as res:
            self.assertEqual(json.load(res)['total'], 0)
        self.assertTrue((self.root / 'surveys.jsonl').is_file())

    def test_bad_input_is_rejected_and_does_not_create_response(self):
        for payload in ({}, {'rating': '虛構', 'comment': ''}, {'rating': '滿意', 'comment': 'x' * 501},
                        {'rating': '滿意', 'comment': 2}, {'rating': '滿意', 'comment': '\x00'}):
            with self.subTest(payload=payload), self.assertRaises(urllib.error.HTTPError) as error:
                self.post(payload)
            self.assertEqual(error.exception.code, 400)
            error.exception.close()
        self.assertFalse((self.root / 'surveys.jsonl').exists())

    def test_local_host_restriction_on_get_and_head(self):
        for method in ('GET', 'HEAD'):
            request = urllib.request.Request(self.base + '/api/surveys', method=method, headers={'Host': 'elsewhere.example'})
            with self.assertRaises(urllib.error.HTTPError) as error:
                urllib.request.urlopen(request)
            self.assertEqual(error.exception.code, 403)
            error.exception.close()

if __name__ == '__main__':
    unittest.main()
