"""LPCell: API local de ordens de serviço com persistência SQLite."""
import os
import sqlite3
import uuid
from pathlib import Path
from datetime import date, datetime, timezone
from decimal import Decimal, InvalidOperation
from flask import Flask, jsonify, request, send_from_directory

ROOT = Path(__file__).resolve().parent
app = Flask(__name__, static_folder=None)
app.config['MAX_CONTENT_LENGTH'] = 32 * 1024
app.config['DATABASE'] = os.environ.get('LPCELL_DATABASE', str(ROOT / 'dados' / 'lpcell.db'))
STATUSES = ['Recebido', 'Em manutenção', 'Concluído', 'Entregue']
FIELDS = ['cpf', 'client', 'phone', 'date', 'device', 'attendant', 'status', 'problem', 'service', 'value']

def connect():
    path = Path(app.config['DATABASE'])
    path.parent.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(path)
    db.row_factory = sqlite3.Row
    db.execute('''CREATE TABLE IF NOT EXISTS orders (
        number INTEGER PRIMARY KEY AUTOINCREMENT, id TEXT UNIQUE NOT NULL,
        client TEXT NOT NULL, phone TEXT NOT NULL, date TEXT NOT NULL,
        device TEXT NOT NULL, attendant TEXT NOT NULL, status TEXT NOT NULL,
        problem TEXT NOT NULL, service TEXT NOT NULL, value TEXT NOT NULL,
        updated TEXT NOT NULL)''')
    # Migração não destrutiva para bancos de versões anteriores.
    columns = {row['name'] for row in db.execute('PRAGMA table_info(orders)')}
    if 'cpf' not in columns:
        db.execute("ALTER TABLE orders ADD COLUMN cpf TEXT NOT NULL DEFAULT ''")
    db.commit()
    return db

@app.before_request
def local_access():
    if request.host not in ('127.0.0.1:5000', 'localhost:5000'):
        return jsonify(error='Acesse pelo endereço local indicado no guia.'), 403
    if request.method in ('POST', 'PUT'):
        origin = request.headers.get('Origin')
        if origin and origin != request.host_url.rstrip('/'):
            return jsonify(error='Origem não permitida.'), 403
        if not request.is_json:
            return jsonify(error='Envie JSON.'), 415

@app.after_request
def headers(response):
    response.headers['Cache-Control'] = 'no-store'
    response.headers['X-Content-Type-Options'] = 'nosniff'
    return response

@app.get('/')
def index():
    return send_from_directory(ROOT / 'site', 'index.html')

@app.get('/<name>')
def asset(name):
    if name not in ('app.js', 'style.css'):
        return jsonify(error='Arquivo não encontrado.'), 404
    return send_from_directory(ROOT / 'site', name)

@app.get('/api/orders')
def list_orders():
    db = connect()
    try:
        return jsonify([dict(row) for row in db.execute('SELECT * FROM orders ORDER BY number DESC')])
    finally:
        db.close()

def validate(payload):
    if not isinstance(payload, dict):
        raise ValueError('Dados inválidos.')
    result = {}
    for field in FIELDS:
        value = payload.get(field, '')
        if not isinstance(value, str):
            raise ValueError('Campo inválido: ' + field)
        result[field] = value.strip()
        if len(result[field]) > 2000:
            raise ValueError('Um campo excedeu 2000 caracteres.')
    if any(not result[k] for k in FIELDS if k not in ('cpf', 'service', 'value')):
        raise ValueError('Preencha todos os campos obrigatórios.')
    if len(''.join(c for c in result['phone'] if c.isdigit())) < 8:
        raise ValueError('Informe um telefone válido.')
    cpf = result['cpf']
    if cpf:
        if any(c not in '0123456789.- ' for c in cpf):
            raise ValueError('CPF inválido.')
        digits = ''.join(c for c in cpf if c in '0123456789')
        if len(digits) != 11:
            raise ValueError('O CPF deve conter 11 dígitos.')
        result['cpf'] = digits
    date.fromisoformat(result['date'])
    if result['status'] not in STATUSES:
        raise ValueError('Status inválido.')
    if result['value']:
        amount = Decimal(result['value'])
        if not amount.is_finite() or amount < 0 or amount > 999999 or amount != amount.quantize(Decimal('0.01')):
            raise ValueError('Valor inválido; use até duas casas decimais.')
    return result

@app.post('/api/orders')
@app.put('/api/orders/<order_id>')
def save_order(order_id=None):
    try:
        data = validate(request.get_json(silent=True))
    except (ValueError, InvalidOperation):
        return jsonify(error='Revise os campos, a data, o telefone e o valor. Se preenchido, o CPF deve ter 11 dígitos.'), 400
    data['updated'] = datetime.now(timezone.utc).isoformat()
    db = connect()
    try:
        with db:
            if order_id:
                old = db.execute('SELECT * FROM orders WHERE id=?', (order_id,)).fetchone()
                if not old:
                    return jsonify(error='Ordem não encontrada.'), 404
                if request.json.get('updated') != old['updated']:
                    return jsonify(error='Esta ordem mudou em outra janela. Recarregue a página antes de editar.'), 409
                db.execute('UPDATE orders SET ' + ', '.join(k + '=?' for k in data) + ' WHERE id=?', [*data.values(), order_id])
            else:
                order_id = str(uuid.uuid4())
                data['id'] = order_id
                db.execute('INSERT INTO orders (' + ','.join(data) + ') VALUES (' + ','.join('?' for _ in data) + ')', list(data.values()))
            saved = dict(db.execute('SELECT * FROM orders WHERE id=?', (order_id,)).fetchone())
        return jsonify(saved), 200 if request.method == 'PUT' else 201
    finally:
        db.close()

@app.errorhandler(sqlite3.Error)
def database_error(error):
    app.logger.error('Falha no banco: %s', error)
    return jsonify(error='Não foi possível acessar o banco. Verifique espaço e permissão da pasta dados.'), 503

if __name__ == '__main__':
    connect().close()
    print('LPCell: abra http://127.0.0.1:5000. Encerre com Ctrl+C.')
    app.run(host='127.0.0.1', port=5000, debug=False)
