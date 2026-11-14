#!/usr/bin/env python3
"""產生、解碼 QR Code，並提供可記錄 HTTP 請求的本機網站。"""
import argparse
from datetime import datetime
from functools import partial
import heapq
import ipaddress
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import socket
import sys
import threading
from urllib.parse import urlsplit
from uuid import uuid4

import cv2
import qrcode
from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parents[1]
RESULTS = ROOT / 'results'
LEVELS = {'L': qrcode.constants.ERROR_CORRECT_L, 'M': qrcode.constants.ERROR_CORRECT_M,
          'Q': qrcode.constants.ERROR_CORRECT_Q, 'H': qrcode.constants.ERROR_CORRECT_H}


def now():
    return datetime.now().astimezone().isoformat(timespec='seconds')


def validate_url(url):
    try:
        parts = urlsplit(url)
        if (parts.scheme not in ('http', 'https') or not parts.hostname or
                parts.username is not None or parts.password is not None or
                any(c.isspace() or ord(c) < 32 for c in url)):
            raise ValueError
        _ = parts.port
    except ValueError:
        raise ValueError('請輸入有效的 HTTP 或 HTTPS 網址（不可含空白或帳密）。') from None
    return url


def decode_image(path):
    image = cv2.imread(str(path))
    if image is None:
        raise ValueError(f'無法讀取圖片：{path}')
    try:
        value, _, _ = cv2.QRCodeDetector().detectAndDecode(image)
    except cv2.error as exc:
        raise ValueError(f'解碼失敗：{exc}') from exc
    return value


def make_qr(url, path, level='M', label=''):
    validate_url(url)
    if level not in LEVELS:
        raise ValueError('容錯等級必須是 L、M、Q 或 H。')
    qr = qrcode.QRCode(error_correction=LEVELS[level], box_size=10, border=4)
    qr.add_data(url); qr.make(fit=True)
    image = qr.make_image(fill_color='black', back_color='white').convert('RGB')
    if label:
        # 標籤置於完整的 QR 靜區之外，不覆蓋任何模組。
        try:
            font = ImageFont.truetype('/System/Library/Fonts/Supplemental/Arial Unicode.ttf', 24)
        except OSError:
            font = ImageFont.load_default(size=20)
        draw = ImageDraw.Draw(image)
        bounds = draw.textbbox((0, 0), label, font=font)
        text_width, text_height = bounds[2]-bounds[0], bounds[3]-bounds[1]
        canvas = Image.new('RGB', (max(image.width, text_width+30), image.height+text_height+30), 'white')
        canvas.paste(image, ((canvas.width-image.width)//2, 0))
        ImageDraw.Draw(canvas).text(((canvas.width-text_width)//2, image.height+10-bounds[1]), label, fill='black', font=font)
        image = canvas
    path = Path(path)
    if path.suffix.lower() != '.png':
        raise ValueError('輸出檔名必須為 .png。')
    path.parent.mkdir(parents=True, exist_ok=True)
    image.save(path, 'PNG')
    decoded = decode_image(path)
    return {'url': url, 'file': str(path), 'version': qr.version, 'modules': 17 + 4*qr.version,
            'level': level, 'pixels': [image.width, image.height], 'bytes': path.stat().st_size,
            'label': label, 'decoded': decoded, 'matches': decoded == url}


def compare_levels(url, directory):
    directory = Path(directory); directory.mkdir(parents=True, exist_ok=True)
    return [make_qr(url, directory / f'qr_{level}.png', level) for level in 'LMQH']


def save_result(mode, data):
    RESULTS.mkdir(parents=True, exist_ok=True)
    stem = f'qr_{mode}_{datetime.now().strftime("%Y%m%d_%H%M%S")}_{uuid4().hex[:6]}'
    payload = {'mode': mode, 'time': now(), **data}
    (RESULTS / f'{stem}.json').write_text(json.dumps(payload, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
    (RESULTS / f'{stem}.md').write_text(f'# {mode} 執行紀錄\n\n時間：{payload["time"]}\n\n```json\n{json.dumps(payload, ensure_ascii=False, indent=2)}\n```\n', encoding='utf-8')
    return stem


def is_local_admin(ip, host, port):
    """後台僅提供本機來源與本機 Host，避免 LAN 洩露及任意 Host。"""
    try:
        if not ipaddress.ip_address(ip).is_loopback:
            return False
    except ValueError:
        return False
    return host.lower() in {f'localhost:{port}', f'127.0.0.1:{port}'}


def read_visit_history(directory, limit=1000):
    """讀取所有服務執行紀錄；統計網站請求並保留最新的有限筆。"""
    records, sequence = [], 0
    site_requests = home_requests = invalid_records = unreadable_files = 0
    for path in sorted(Path(directory).glob('connections_*.jsonl')):
        try:
            with path.open(encoding='utf-8') as stream:
                for line in stream:
                    try:
                        row = json.loads(line)
                        if not isinstance(row, dict) or not all(
                            isinstance(row.get(k), str) for k in ('time', 'ip', 'user_agent', 'method', 'path')
                        ) or not isinstance(row.get('status'), int):
                            raise ValueError('invalid record')
                        parsed = datetime.fromisoformat(row['time'])
                        if parsed.tzinfo is None:
                            raise ValueError('time has no timezone')
                        stamp = parsed.timestamp()
                    except (ValueError, TypeError, OverflowError, OSError):
                        invalid_records += 1
                        continue
                    if row['path'] in ('/admin', '/api/visits'):
                        continue
                    site_requests += 1
                    if row['path'] == '/' and row['method'] == 'GET':
                        home_requests += 1
                    row['source'] = path.name
                    sequence += 1
                    item = (stamp, sequence, row)
                    if len(records) < limit:
                        heapq.heappush(records, item)
                    elif limit and item[:2] > records[0][:2]:
                        heapq.heapreplace(records, item)
        except (OSError, UnicodeError):
            unreadable_files += 1
    return {'site_requests': site_requests, 'home_requests': home_requests,
            'invalid_records': invalid_records, 'unreadable_files': unreadable_files,
            'truncated': site_requests > len(records),
            'records': [item[2] for item in sorted(records, reverse=True)]}


class LoggedHandler(SimpleHTTPRequestHandler):
    def __init__(self, *args, directory, log_path, log_lock, **kwargs):
        self.log_path, self.log_lock = log_path, log_lock
        super().__init__(*args, directory=str(directory), **kwargs)

    def do_GET(self):
        path = urlsplit(self.path).path
        if path in ('/admin', '/api/visits'):
            if not is_local_admin(self.client_address[0], self.headers.get('Host', ''), self.server.server_port):
                self.send_error(403, 'Local access only')
                return
            try:
                if path == '/admin':
                    body = (ROOT / 'src' / 'admin.html').read_bytes()
                    content_type = 'text/html; charset=utf-8'
                else:
                    with self.log_lock:
                        data = read_visit_history(self.log_path.parent)
                    body = json.dumps(data, ensure_ascii=False).encode('utf-8')
                    content_type = 'application/json; charset=utf-8'
            except OSError:
                self.send_error(500, 'Unable to load dashboard data')
                return
            self.send_response(200)
            self.send_header('Content-Type', content_type)
            self.send_header('Content-Length', str(len(body)))
            self.send_header('Cache-Control', 'no-store')
            self.send_header('X-Content-Type-Options', 'nosniff')
            self.end_headers()
            self.wfile.write(body)
            return
        super().do_GET()

    def do_HEAD(self):
        if urlsplit(self.path).path in ('/admin', '/api/visits'):
            if not is_local_admin(self.client_address[0], self.headers.get('Host', ''), self.server.server_port):
                self.send_error(403, 'Local access only')
            else:
                self.send_error(405, 'Method not allowed')
            return
        super().do_HEAD()

    def log_request(self, code='-', size='-'):
        # 不記錄 query string，避免不必要資料進入紀錄。
        record = {'time': now(), 'ip': self.client_address[0],
                  'user_agent': self.headers.get('User-Agent', '')[:500],
                  'method': self.command, 'path': urlsplit(self.path).path[:500], 'status': int(code)}
        with self.log_lock, self.log_path.open('a', encoding='utf-8') as stream:
            stream.write(json.dumps(record, ensure_ascii=False)+'\n')


def create_server(host, port, site, log_path):
    log_path = Path(log_path); log_path.parent.mkdir(parents=True, exist_ok=True)
    return ThreadingHTTPServer((host, port), partial(LoggedHandler, directory=site, log_path=log_path, log_lock=threading.Lock()))


def local_ip():
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
        try:
            sock.connect(('192.0.2.1', 80))  # 僅查路由選擇，不傳送資料。
            return sock.getsockname()[0]
        except OSError:
            return '127.0.0.1'


def main(argv=None):
    parser = argparse.ArgumentParser(description='QR Code 網址、解碼與本機網頁')
    sub = parser.add_subparsers(dest='mode', required=True)
    p = sub.add_parser('make'); p.add_argument('--url', required=True); p.add_argument('--out', required=True); p.add_argument('--level', choices=list(LEVELS), default='M'); p.add_argument('--label', default='')
    p = sub.add_parser('decode'); p.add_argument('image'); p.add_argument('--expect')
    p = sub.add_parser('compare'); p.add_argument('--url', required=True); p.add_argument('--out-dir', default='images/compare')
    p = sub.add_parser('serve'); p.add_argument('--port', type=int, default=8000); p.add_argument('--host-ip', default=None, help='手機可連線的電腦 IPv4 位址'); p.add_argument('--out', default='images/qr_site.png')
    args = parser.parse_args(argv)
    try:
        if args.mode == 'make':
            data = make_qr(args.url, args.out, args.level, args.label)
            save_result('make', data); print(json.dumps(data, ensure_ascii=False, indent=2))
            return 0 if data['matches'] else 1
        if args.mode == 'decode':
            value = decode_image(args.image)
            data = {'file': args.image, 'decoded': value, 'expected': args.expect, 'matches': value == args.expect if args.expect is not None else None}
            save_result('decode', data); print(json.dumps(data, ensure_ascii=False, indent=2))
            return 0 if value and (args.expect is None or value == args.expect) else 1
        if args.mode == 'compare':
            rows = compare_levels(args.url, args.out_dir); save_result('compare', {'results': rows}); print(json.dumps(rows, ensure_ascii=False, indent=2))
            return 0 if all(row['matches'] for row in rows) else 1
        ip = args.host_ip or local_ip()
        if not 0 <= args.port <= 65535:
            raise ValueError('埠號必須介於 0 和 65535。')
        stamp = datetime.now().strftime('%Y%m%d_%H%M%S') + '_' + uuid4().hex[:6]
        log = RESULTS / f'connections_{stamp}.jsonl'
        server = create_server('0.0.0.0', args.port, ROOT / 'site', log)
        try:
            url = f'http://{ip}:{server.server_port}/'; validate_url(url)
            data = make_qr(url, args.out, 'H', 'Local website')
            if not data['matches']:
                raise ValueError('網站 QR Code 無法解碼，服務未啟動。')
            save_result('serve', {'event': 'started', 'qr': data, 'connection_log': str(log)})
            print(f'網站：{url}\n後台（僅限本機）：http://127.0.0.1:{server.server_port}/admin\nQR 圖片：{args.out}\n連線紀錄：{log}\n按 Ctrl+C 結束。', flush=True)
            try:
                server.serve_forever()
            except KeyboardInterrupt:
                print('\n服務已停止。')
        finally:
            server.server_close()
            if 'data' in locals() and data.get('matches'):
                count = sum(1 for _ in log.open(encoding='utf-8')) if log.exists() else 0
                save_result('serve', {'event':'stopped', 'url':url, 'connection_log':str(log), 'requests':count})
        return 0
    except (ValueError, OSError, qrcode.exceptions.DataOverflowError) as exc:
        print(f'錯誤：{exc}', file=sys.stderr); return 1

if __name__ == '__main__':
    raise SystemExit(main())
