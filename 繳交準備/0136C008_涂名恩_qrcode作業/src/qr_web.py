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
from urllib.parse import parse_qs, urlsplit
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


def make_qr(url, path, level='M', label='', logo=None):
    validate_url(url)
    if level not in LEVELS:
        raise ValueError('容錯等級必須是 L、M、Q 或 H。')
    if logo is not None and level != 'H':
        raise ValueError('中央 Logo 必須使用 H 容錯等級。')
    path = Path(path)
    if path.suffix.lower() != '.png':
        raise ValueError('輸出檔名必須為 .png。')
    logo_image = None
    if logo is not None and logo != 'builtin':
        if Path(logo).resolve() == path.resolve():
            raise ValueError('輸出圖片不可覆寫原始 Logo。')
        try:
            with Image.open(logo) as source:
                logo_image = source.convert('RGBA')
        except (OSError, ValueError) as exc:
            raise ValueError(f'無法讀取 Logo 圖檔：{logo}') from exc
    qr = qrcode.QRCode(error_correction=LEVELS[level], box_size=10, border=4)
    qr.add_data(url); qr.make(fit=True)
    image = qr.make_image(fill_color='black', back_color='white').convert('RGB')
    if logo is not None:
        # 避免覆蓋定位圖案及外部靜區，中心標記占資料區邊長約 18%。
        side = max(1, round(qr.modules_count * 10 * .18))
        left = (image.width - side) // 2
        top = (image.height - side) // 2
        draw = ImageDraw.Draw(image)
        draw.rounded_rectangle((left, top, left + side - 1, top + side - 1), radius=max(1, side//6), fill='white')
        inset = max(2, side//9)
        box = (left + inset, top + inset, left + side - inset - 1, top + side - inset - 1)
        if logo_image is None:
            draw.rounded_rectangle(box, radius=max(1, side//7), fill='#176b57')
            margin = max(3, side//4)
            draw.ellipse((left+margin, top+margin, left+side-margin, top+side-margin), outline='white', width=max(2, side//14))
            draw.line((left+side*.58, top+side*.58, left+side*.72, top+side*.72), fill='white', width=max(2, side//14))
        else:
            logo_image.thumbnail((side-2*inset, side-2*inset), Image.Resampling.LANCZOS)
            image.paste(logo_image, (left+(side-logo_image.width)//2, top+(side-logo_image.height)//2), logo_image)
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
    path.parent.mkdir(parents=True, exist_ok=True)
    image.save(path, 'PNG')
    decoded = decode_image(path)
    return {'url': url, 'file': str(path), 'version': qr.version, 'modules': 17 + 4*qr.version,
            'level': level, 'pixels': [image.width, image.height], 'bytes': path.stat().st_size,
            'label': label, 'logo': ('builtin' if logo == 'builtin' else 'custom') if logo is not None else None,
            'decoded': decoded, 'matches': decoded == url}


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


def read_visit_history(directory, limit=1000, start=None, end=None):
    """讀取所有服務執行紀錄；統計網站請求並保留最新的有限筆。"""
    if any(value is not None and (not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None) for value in (start, end)):
        raise ValueError('時間必須包含時區。')
    if start is not None and end is not None and start >= end:
        raise ValueError('結束時間必須晚於開始時間。')
    start_stamp = start.timestamp() if start is not None else None
    end_stamp = end.timestamp() if end is not None else None
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
                    if row['path'] in ('/admin', '/api/visits', '/api/checkins', '/api/surveys'):
                        continue
                    if (start_stamp is not None and stamp < start_stamp) or (end_stamp is not None and stamp >= end_stamp):
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


def parse_visit_range(query):
    """解析含時區的起點及排他終點；空值、重複或顛倒的範圍均拒絕。"""
    params = parse_qs(query, keep_blank_values=True, max_num_fields=10)
    if set(params) - {'start', 'end'} or any(len(values) != 1 for values in params.values()):
        raise ValueError('invalid parameters')
    result = []
    for key in ('start', 'end'):
        if key not in params:
            result.append(None)
            continue
        value = datetime.fromisoformat(params[key][0])
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError('timezone required')
        result.append(value)
    start, end = result
    if start is not None and end is not None and start >= end:
        raise ValueError('invalid range')
    return start, end


def read_records(directory, filename, required_fields, start=None, end=None, limit=1000):
    """先篩選符合時段的資料，再取最新紀錄。"""
    records, count, invalid = [], 0, 0
    path = Path(directory) / filename
    if not path.exists():
        return {'records': [], 'total': 0, 'invalid_records': 0, 'truncated': False}
    with path.open(encoding='utf-8') as stream:
        for line in stream:
            try:
                row = json.loads(line)
                if not isinstance(row, dict) or not all(isinstance(row.get(k), str) for k in required_fields):
                    raise ValueError('invalid record')
                parsed = datetime.fromisoformat(row['time'])
                if parsed.tzinfo is None or parsed.utcoffset() is None:
                    raise ValueError('timezone required')
                stamp = parsed.timestamp()
            except (ValueError, TypeError, OverflowError, OSError):
                invalid += 1
                continue
            if (start is not None and stamp < start.timestamp()) or (end is not None and stamp >= end.timestamp()):
                continue
            count += 1
            item = (stamp, count, row)
            if len(records) < limit:
                heapq.heappush(records, item)
            elif limit and item[:2] > records[0][:2]:
                heapq.heapreplace(records, item)
    return {'records': [item[2] for item in sorted(records, reverse=True)], 'total': count,
            'invalid_records': invalid, 'truncated': count > len(records)}


def read_checkins(directory, start=None, end=None, limit=1000):
    return read_records(directory, 'checkins.jsonl', ('time', 'model', 'ip'), start, end, limit)


class LoggedHandler(SimpleHTTPRequestHandler):
    def __init__(self, *args, directory, log_path, log_lock, **kwargs):
        self.log_path, self.log_lock = log_path, log_lock
        super().__init__(*args, directory=str(directory), **kwargs)

    def do_GET(self):
        path = urlsplit(self.path).path
        if path in ('/admin', '/api/visits', '/api/checkins', '/api/surveys'):
            if not is_local_admin(self.client_address[0], self.headers.get('Host', ''), self.server.server_port):
                self.send_error(403, 'Local access only')
                return
            try:
                if path == '/admin':
                    body = (ROOT / 'src' / 'admin.html').read_bytes()
                    content_type = 'text/html; charset=utf-8'
                else:
                    try:
                        start, end = parse_visit_range(urlsplit(self.path).query)
                    except (ValueError, OverflowError):
                        self.send_error(400, 'Invalid time range')
                        return
                    with self.log_lock:
                        if path == '/api/checkins':
                            data = read_checkins(self.log_path.parent, start=start, end=end)
                        elif path == '/api/surveys':
                            data = read_records(self.log_path.parent, 'surveys.jsonl', ('time', 'rating', 'comment'), start=start, end=end)
                        else:
                            data = read_visit_history(self.log_path.parent, start=start, end=end)
                    body = json.dumps(data, ensure_ascii=False).encode('utf-8')
                    content_type = 'application/json; charset=utf-8'
            except (OSError, UnicodeError):
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

    def do_POST(self):
        path = urlsplit(self.path).path
        if path not in ('/api/checkin', '/api/survey'):
            self.send_error(404, 'Not found')
            return
        try:
            if self.headers.get_content_type() != 'application/json':
                raise ValueError('invalid content type')
            size = int(self.headers.get('Content-Length', ''))
            if size < 1 or size > 4096:
                raise ValueError('invalid body size')
            data = json.loads(self.rfile.read(size).decode('utf-8'))
            if not isinstance(data, dict):
                raise ValueError('invalid data')
            if path == '/api/checkin':
                model = data.get('model')
                if not isinstance(model, str):
                    raise ValueError('invalid model')
                model = model.strip()
                if not model or len(model) > 80 or any(ord(c) < 32 or ord(c) == 127 for c in model):
                    raise ValueError('invalid model')
                record = {'time': now(), 'model': model, 'ip': self.client_address[0]}
                filename = 'checkins.jsonl'
            else:
                rating, comment = data.get('rating'), data.get('comment', '')
                if not isinstance(rating, str) or rating not in ('非常滿意', '滿意', '普通', '不滿意'):
                    raise ValueError('invalid rating')
                if not isinstance(comment, str) or len(comment) > 500 or any((ord(c) < 32 and c not in '\n\r\t') or ord(c) == 127 for c in comment):
                    raise ValueError('invalid comment')
                record = {'time': now(), 'rating': rating, 'comment': comment.strip()}
                filename = 'surveys.jsonl'
        except (ValueError, UnicodeError):
            self.send_error(400, 'Invalid submission')
            return
        try:
            with self.log_lock, (self.log_path.parent / filename).open('a', encoding='utf-8') as stream:
                stream.write(json.dumps(record, ensure_ascii=False) + '\n')
        except OSError:
            self.send_error(500, 'Unable to save submission')
            return
        body = json.dumps(record, ensure_ascii=False).encode('utf-8')
        self.send_response(200)
        self.send_header('Content-Type', 'application/json; charset=utf-8')
        self.send_header('Content-Length', str(len(body)))
        self.send_header('Cache-Control', 'no-store')
        self.end_headers()
        self.wfile.write(body)

    def do_HEAD(self):
        if urlsplit(self.path).path in ('/admin', '/api/visits', '/api/checkins', '/api/surveys'):
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
    p = sub.add_parser('make'); p.add_argument('--url', required=True); p.add_argument('--out', required=True); p.add_argument('--level', choices=list(LEVELS)); p.add_argument('--label', default=''); p.add_argument('--logo', nargs='?', const='builtin', help='中央 Logo，可省略路徑使用內建標記')
    p = sub.add_parser('decode'); p.add_argument('image'); p.add_argument('--expect')
    p = sub.add_parser('compare'); p.add_argument('--url', required=True); p.add_argument('--out-dir', default='images/compare')
    p = sub.add_parser('serve'); p.add_argument('--port', type=int, default=8000); p.add_argument('--host-ip', default=None, help='手機可連線的電腦 IPv4 位址'); p.add_argument('--out', default='images/qr_site.png')
    args = parser.parse_args(argv)
    try:
        if args.mode == 'make':
            data = make_qr(args.url, args.out, args.level or ('H' if args.logo is not None else 'M'), args.label, logo=args.logo)
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
