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


class DashboardTests(unittest.TestCase):
    def test_local_admin_host_validation(self):
        for ip, host, expected in [
            ('127.0.0.1', 'localhost:8000', True),
            ('127.0.0.1', '127.0.0.1:8000', True),
            ('192.168.1.2', 'localhost:8000', False),
            ('127.0.0.1', 'evil.example:8000', False),
            ('127.0.0.1', 'localhost:9999', False),
        ]:
            with self.subTest(ip=ip, host=host):
                self.assertEqual(qr_web.is_local_admin(ip, host, 8000), expected)

    def test_history_excludes_admin_traffic_and_reports_corruption(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            entries = [
                {'time':'2026-01-01T00:00:00+08:00','ip':'10.0.0.1','user_agent':'phone','method':'GET','path':'/','status':200},
                {'time':'2026-01-01T00:00:01+08:00','ip':'10.0.0.1','user_agent':'phone','method':'GET','path':'/favicon.ico','status':404},
                {'time':'2026-01-01T00:00:02+08:00','ip':'127.0.0.1','user_agent':'browser','method':'GET','path':'/api/visits','status':200},
            ]
            (root/'connections_1.jsonl').write_text('\n'.join(json.dumps(r) for r in entries)+'\n{bad json\n')
            (root/'unrelated.jsonl').write_text(json.dumps(entries[0])+'\n')
            result = qr_web.read_visit_history(root)
            self.assertEqual(result['site_requests'], 2)
            self.assertEqual(result['home_requests'], 1)
            self.assertEqual(result['invalid_records'], 1)
            self.assertEqual(len(result['records']), 2)
            self.assertEqual(result['records'][0]['path'], '/favicon.ico')

    def test_history_caps_output_but_counts_every_request(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            row = {'time':'2026-01-01T00:00:00+08:00','ip':'10.0.0.1','user_agent':'phone','method':'GET','path':'/','status':200}
            (root/'connections_1.jsonl').write_text((json.dumps(row)+'\n') * 5)
            result = qr_web.read_visit_history(root, limit=2)
            self.assertEqual(result['site_requests'], 5)
            self.assertEqual(result['home_requests'], 5)
            self.assertEqual(len(result['records']), 2)
            self.assertTrue(result['truncated'])

    def test_dashboard_and_api_access(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d); site=root/'site'; site.mkdir()
            (site/'index.html').write_text('public page')
            log=root/'connections_current.jsonl'
            server=qr_web.create_server('127.0.0.1',0,site,log)
            thread=threading.Thread(target=server.serve_forever,daemon=True); thread.start()
            base=f'http://127.0.0.1:{server.server_port}'
            try:
                with urllib.request.urlopen(base+'/') as response:
                    self.assertEqual(response.read(), b'public page')
                with urllib.request.urlopen(base+'/admin') as response:
                    self.assertIn('連線紀錄',response.read().decode())
                with urllib.request.urlopen(base+'/api/visits') as response:
                    data=json.load(response)
                    self.assertEqual(data['home_requests'],1)
                    self.assertEqual(data['site_requests'],1)
                for path in ('/admin','/api/visits'):
                    req=urllib.request.Request(base+path,headers={'Host':'evil.example'})
                    with self.assertRaises(urllib.error.HTTPError) as caught:
                        urllib.request.urlopen(req)
                    self.assertEqual(caught.exception.code,403)
                    caught.exception.close()
                with self.assertRaises(urllib.error.HTTPError) as caught:
                    urllib.request.urlopen(base+'/admin.html')
                self.assertEqual(caught.exception.code,404); caught.exception.close()
            finally:
                server.shutdown(); thread.join(); server.server_close()

if __name__ == '__main__':
    unittest.main()
