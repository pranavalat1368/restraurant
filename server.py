import json
import os
from datetime import datetime, timezone
from http import HTTPStatus
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse


ROOT = Path(__file__).resolve().parent
DATA_DIR = ROOT / 'data'
RESERVATIONS_FILE = DATA_DIR / 'reservations.json'
MENU_FILE = DATA_DIR / 'menu.json'
PORT = int(os.environ.get('PORT', '3000'))

TABLES = [
    {'number': 1, 'capacity': 2},
    {'number': 2, 'capacity': 2},
    {'number': 3, 'capacity': 4},
    {'number': 4, 'capacity': 4},
    {'number': 5, 'capacity': 6},
    {'number': 6, 'capacity': 6},
    {'number': 7, 'capacity': 8},
    {'number': 8, 'capacity': 8},
]


def ensure_json_file(file_path: Path, default_value):
    file_path.parent.mkdir(parents=True, exist_ok=True)
    if not file_path.exists():
        file_path.write_text(json.dumps(default_value, indent=2), encoding='utf-8')


def read_json_file(file_path: Path, fallback):
    try:
        return json.loads(file_path.read_text(encoding='utf-8'))
    except Exception:
        return fallback


def write_json_file(file_path: Path, value):
    file_path.write_text(json.dumps(value, indent=2), encoding='utf-8')


def pick_available_table(reservations, reservation_date, guests):
    occupied_tables = {
        reservation.get('tableNumber')
        for reservation in reservations
        if reservation.get('date') == reservation_date and reservation.get('status') in {'confirmed', 'pending'}
    }

    for table in TABLES:
        if table['capacity'] >= guests and table['number'] not in occupied_tables:
            return table

    return None


ensure_json_file(MENU_FILE, {
    'categories': ['starters', 'pasta', 'mains', 'desserts'],
    'items': []
})
ensure_json_file(RESERVATIONS_FILE, [])


class RestaurantHandler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(ROOT), **kwargs)

    def end_headers(self):
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type')
        self.send_header('Access-Control-Allow-Methods', 'GET, POST, OPTIONS')
        super().end_headers()

    def do_OPTIONS(self):
        self.send_response(HTTPStatus.NO_CONTENT)
        self.end_headers()

    def do_GET(self):
        parsed_path = urlparse(self.path)

        if parsed_path.path == '/api/health':
            return self.send_json(HTTPStatus.OK, {'ok': True, 'service': 'bella-cucina-backend'})

        if parsed_path.path == '/api/menu':
            menu = read_json_file(MENU_FILE, {'categories': [], 'items': []})
            return self.send_json(HTTPStatus.OK, menu)

        if parsed_path.path == '/api/reservations':
            reservations = read_json_file(RESERVATIONS_FILE, [])
            return self.send_json(HTTPStatus.OK, {'count': len(reservations), 'reservations': reservations})

        if parsed_path.path == '/':
            self.path = '/index.html'

        return super().do_GET()

    def do_POST(self):
        parsed_path = urlparse(self.path)

        if parsed_path.path != '/api/reservations':
            return self.send_error(HTTPStatus.NOT_FOUND, 'Not found')

        content_length = int(self.headers.get('Content-Length', '0'))
        raw_body = self.rfile.read(content_length).decode('utf-8') if content_length else '{}'

        try:
            payload = json.loads(raw_body)
        except json.JSONDecodeError:
            return self.send_json(HTTPStatus.BAD_REQUEST, {
                'ok': False,
                'message': 'Request body must be valid JSON.'
            })

        name = str(payload.get('name', '')).strip()
        phone = str(payload.get('phone', '')).strip()
        email = str(payload.get('email', '')).strip()
        date = str(payload.get('date', '')).strip()
        guests_value = payload.get('guests', '')
        occasion = str(payload.get('occasion', '')).strip()
        notes = str(payload.get('notes', '')).strip()

        try:
            guests = int(guests_value)
        except (TypeError, ValueError):
            guests = 0

        if not name or not phone or not date or guests < 1:
            return self.send_json(HTTPStatus.BAD_REQUEST, {
                'ok': False,
                'message': 'Please provide your name, phone, date, and a valid guest count.'
            })

        reservations = read_json_file(RESERVATIONS_FILE, [])
        table = pick_available_table(reservations, date, guests)

        if table is None:
            return self.send_json(HTTPStatus.OK, {
                'ok': False,
                'message': 'Sorry, no table is available for that date and party size.'
            })

        reservation = {
            'id': f"res_{int(datetime.now(tz=timezone.utc).timestamp() * 1000)}",
            'name': name,
            'phone': phone,
            'email': email,
            'date': date,
            'guests': guests,
            'occasion': occasion,
            'notes': notes,
            'createdAt': datetime.now(tz=timezone.utc).isoformat(),
            'status': 'confirmed',
            'tableNumber': table['number'],
            'tableCapacity': table['capacity']
        }

        reservations.insert(0, reservation)
        write_json_file(RESERVATIONS_FILE, reservations)

        return self.send_json(HTTPStatus.CREATED, {
            'ok': True,
            'message': f"Table {table['number']} is available and your reservation is confirmed.",
            'reservation': reservation
        })

    def send_json(self, status_code, payload):
        body = json.dumps(payload).encode('utf-8')
        self.send_response(status_code)
        self.send_header('Content-Type', 'application/json; charset=utf-8')
        self.send_header('Content-Length', str(len(body)))
        self.end_headers()
        self.wfile.write(body)


def main():
    server = ThreadingHTTPServer(('0.0.0.0', PORT), RestaurantHandler)
    print(f'Bella Cucina backend running at http://localhost:{PORT}')
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print('\nShutting down...')
    finally:
        server.server_close()


if __name__ == '__main__':
    main()