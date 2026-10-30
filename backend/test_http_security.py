"""Exercise real HTTP handlers with isolated SQLite and no engine subprocess."""
import base64
import importlib.util
import json
import os
import pathlib
import tempfile
import threading
import unittest
from unittest.mock import patch
from collections import namedtuple
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer


class HTTPSecurityTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory(dir=pathlib.Path(__file__).parent)
        keys = ('STATE_DIR', 'APP_PASSWORD', 'VIEWER_PASSWORD', 'RULES_PATH')
        cls.saved = {key: os.environ.get(key) for key in keys}
        os.environ.update(STATE_DIR=cls.temp.name, APP_PASSWORD='test-analyst', VIEWER_PASSWORD='test-viewer', RULES_PATH=str(pathlib.Path(__file__).resolve().parents[1] / 'rules/local.rules'))
        spec = importlib.util.spec_from_file_location('isolated_test_server', pathlib.Path(__file__).parent / 'server.py')
        cls.module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(cls.module)
        cls.module.db.close()
        cls.http = ThreadingHTTPServer(('127.0.0.1', 0), cls.module.API)
        cls.thread = threading.Thread(target=cls.http.serve_forever, daemon=True)
        cls.thread.start()
        cls.opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))

    @classmethod
    def tearDownClass(cls):
        cls.http.shutdown()
        cls.http.server_close()
        cls.thread.join()
        cls.module.POOL.shutdown()
        cls.temp.cleanup()
        for key, value in cls.saved.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value

    def request(self, path, data=None, actor='analyst', origin=None):
        headers = {}
        if actor:
            password = 'test-viewer' if actor == 'viewer' else 'test-analyst'
            headers['Authorization'] = 'Basic ' + base64.b64encode((actor + ':' + password).encode()).decode()
        if origin:
            headers['Origin'] = origin
        if isinstance(data, dict):
            data = json.dumps(data).encode()
            headers['Content-Type'] = 'application/json'
        req = urllib.request.Request('http://127.0.0.1:' + str(self.http.server_port) + path, data=data, headers=headers)
        try:
            with self.opener.open(req, timeout=5) as response:
                return response.status, json.load(response)
        except urllib.error.HTTPError as error:
            return error.code, json.load(error)

    def test_auth_roles_and_origin(self):
        self.assertEqual(self.request('/api/tasks', actor=None)[0], 401)
        self.assertTrue(self.request('/api/me', actor='viewer')[1]['readonly'])
        self.assertEqual(self.request('/api/tasks', b'x'*24, actor='viewer')[0], 403)
        self.assertEqual(self.request('/api/tasks', b'x'*24, origin='http://evil.invalid')[0], 403)
        self.assertEqual(self.request('/api/rules/1000001', {}, actor='viewer')[0], 403)
        self.assertEqual(self.request('/api/rules/1000001/rollback', {}, actor='viewer')[0], 403)
        self.assertEqual(self.request('/api/rules/1000001', b'[]')[0], 422)
        for endpoint in ('/api/rules/create', '/api/rules/1000001/archive', '/api/rules/1000001/restore'):
            self.assertEqual(self.request(endpoint, {}, actor='viewer')[0], 403)

    def test_rule_crud_versions_and_archive(self):
        from unittest.mock import patch
        import rule_editor
        raw = 'alert tcp any any -> any any (msg:"CRUD test"; sid:1900001; rev:1;)'
        def checked_publish(*args):
            return rule_editor.publish(*args, checker=lambda *a: None)
        def checked_lifecycle(*args):
            return rule_editor.lifecycle(*args, checker=lambda *a: None)
        with patch.object(self.module, 'publish', side_effect=checked_publish), patch.object(self.module, 'lifecycle', side_effect=checked_lifecycle):
            self.assertEqual(self.request('/api/rules/create', {'sid':1900001,'raw':raw})[0], 201)
            self.assertEqual(self.request('/api/rules/create', {'sid':1900001,'raw':raw})[0], 409)
            self.assertEqual(self.request('/api/rules/1900001', {'raw':raw,'base_revision':1})[1]['revision'], 2)
            self.assertEqual(self.request('/api/rules/1900001/archive', {'base_revision':1})[0], 409)
            self.assertEqual(self.request('/api/rules/1900001/archive', {'base_revision':2})[1]['revision'], 3)
            self.assertNotIn(1900001, [r['sid'] for r in self.request('/api/rules')[1]])
            self.assertTrue(next(r for r in self.request('/api/rules?include_archived=1')[1] if r['sid']==1900001)['archived'])
            self.assertEqual(self.request('/api/rules/create', {'sid':1900001,'raw':raw})[0], 409)
            self.assertEqual(self.request('/api/rules/1900001', {'raw':raw,'base_revision':3})[0], 404)
            self.assertEqual(self.request('/api/rules/1900001/restore', {'base_revision':3})[1]['revision'], 4)
            history = self.request('/api/rules/1900001/history')[1]
            self.assertEqual([r['action'] for r in history], ['restore','archive','edit','create','baseline'])

    def test_invalid_capture_traversal_and_rule_injection(self):
        self.assertEqual(self.request('/api/tasks', b'x'*24)[0], 400)
        self.assertEqual(self.request('/api/../../etc/passwd')[0], 404)
        self.assertEqual(self.request('/api/rules', {'sid': '1000001;touch /tmp/injected', 'enabled': True})[0], 400)
        self.assertEqual(self.request('/api/rules', {'sid': 1000001, 'enabled': 'false'})[0], 400)
        self.assertEqual(self.request('/api/alerts?src_ip=%27%20OR%201=1--')[1]['total'], 0)
        self.assertEqual(self.request('/api/tasks')[1], [])

    def test_low_disk_rejects_upload_before_creating_task(self):
        usage = namedtuple('usage', 'total used free')(1000, 999, 1)
        with patch.object(self.module.shutil, 'disk_usage', return_value=usage):
            self.assertEqual(self.request('/api/tasks', b'x'*24)[0], 507)
        self.assertEqual(self.request('/api/tasks')[1], [])

    def test_notes_are_versioned_and_readonly_cannot_write(self):
        with self.module.database() as db:
            db.execute("INSERT INTO events(id,task_id,line_no,event_type,raw_json,ingested_at) VALUES (1000,'test',1,'alert','{}','now')")
        body = {'conclusion': '仅发现可疑请求，影响待核查', 'recommendation': '核对服务器日志'}
        self.assertEqual(self.request('/api/alerts/1000/notes', body, actor='viewer')[0], 403)
        self.assertEqual(self.request('/api/alerts/1000/notes', body)[0], 200)
        self.assertEqual(self.request('/api/alerts/1000/notes', dict(body, conclusion='二次复核结论'))[0], 200)
        with self.module.database() as db:
            rows = db.execute('SELECT conclusion,actor FROM analyst_notes WHERE event_id=1000 ORDER BY id').fetchall()
        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[0]['actor'], 'analyst')
        self.assertEqual(self.request('/api/alerts/99999/notes', body)[0], 404)
