import tempfile
import unittest
from pathlib import Path
from server import app, connect

class DatabaseTests(unittest.TestCase):
    def test_save_edit_persistence_validation(self):
        with tempfile.TemporaryDirectory() as folder:
            app.config['DATABASE'] = str(Path(folder) / 'test.db')
            client = app.test_client()
            base = 'http://127.0.0.1:5000'
            fields = dict(client='Cliente fictício', phone='11999990000', date='2026-10-18', device='Modelo teste', attendant='Teste', status='Recebido', problem='Tela', service='', value='150.00')
            r = client.post('/api/orders', json=fields, base_url=base)
            self.assertEqual(r.status_code, 201)
            saved = r.get_json()
            self.assertEqual(saved['cpf'], '')
            saved['cpf'] = '000.000.000-00'  # Dado fictício; validação apenas de formato.
            saved['status'] = 'Concluído'
            r = client.put('/api/orders/'+saved['id'], json=saved, base_url=base)
            self.assertEqual(r.status_code, 200)
            self.assertEqual(r.get_json()['cpf'], '00000000000')
            self.assertEqual(client.put('/api/orders/'+saved['id'], json=saved, base_url=base).status_code, 409)
            db = connect()
            self.assertEqual(db.execute('SELECT status FROM orders').fetchone()[0], 'Concluído')
            self.assertEqual(db.execute('SELECT cpf FROM orders').fetchone()[0], '00000000000')
            db.close()
            self.assertEqual(len(app.test_client().get('/api/orders', base_url=base).get_json()), 1)
            self.assertEqual(client.post('/api/orders', json={**fields, 'cpf':'123'}, base_url=base).status_code, 400)
            self.assertEqual(client.post('/api/orders', json={**fields, 'value':'-1'}, base_url=base).status_code, 400)
            self.assertEqual(client.post('/api/orders', json=fields, base_url=base, headers={'Origin':'https://example.com'}).status_code, 403)
            self.assertEqual(client.get('/dados/lpcell.db', base_url=base).status_code, 404)
            self.assertEqual(client.get('/', base_url=base).status_code, 200)

if __name__ == '__main__':
    unittest.main()
