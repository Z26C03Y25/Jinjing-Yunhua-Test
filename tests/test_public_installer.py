import argparse
import importlib.util
import pathlib
import tempfile
import unittest
import os
from types import SimpleNamespace
from unittest.mock import patch

spec = importlib.util.spec_from_file_location('public_installer', pathlib.Path(__file__).parents[1]/'scripts/install-public.py')
installer = importlib.util.module_from_spec(spec)
spec.loader.exec_module(installer)


class InstallerTest(unittest.TestCase):
    def test_port_increment_and_own_service(self):
        self.assertEqual(installer.find_port('0.0.0.0',80,{80,81},set(),lambda *a:True),82)
        self.assertEqual(installer.find_port('0.0.0.0',81,set(),{81},lambda *a:False),81)
        self.assertEqual(installer.find_port('0.0.0.0',80,set(),set(),lambda host,p:p==83),83)
        with self.assertRaises(RuntimeError):
            installer.find_port('0.0.0.0',65535,{65535},set())

    def test_changing_port_preserves_password_bytes(self):
        with tempfile.TemporaryDirectory() as folder:
            root=pathlib.Path(folder)
            content="APP_PASSWORD='Fake$#secret'\nWEB_PORT='80'\nVIEWER_PASSWORD=''\n"
            (root/'.env').write_text(content,encoding='utf-8')
            installer.persist_port(root,81)
            self.assertEqual((root/'.env').read_text(encoding='utf-8'),content.replace("WEB_PORT='80'","WEB_PORT='81'"))

    def test_password_file_and_existing_configuration_preserved(self):
        with tempfile.TemporaryDirectory() as folder:
            root = pathlib.Path(folder)
            args = argparse.Namespace(web_port=80, bind='0.0.0.0', project='jinjing-yunhua', backend_image='jinjing-backend:stage1')
            password = "Fake$#'\\ password9!"
            self.assertTrue(installer.save_configuration(root, password, '', args))
            original = (root/'.env').read_bytes()
            self.assertIn(b"APP_PASSWORD='", original)
            self.assertFalse(installer.save_configuration(root, 'new-secret', '', args))
            self.assertEqual((root/'.env').read_bytes(), original)
            self.assertEqual(list(root.glob('.env.install-*')), [])

    def test_newline_injection_rejected(self):
        for value in ('secret\nWEB_PORT=1', 'secret\rtest', 'secret\0test'):
            with self.assertRaises(ValueError):
                installer.dotenv_quote(value)

    def test_public_file_permissions_do_not_touch_password_file(self):
        with tempfile.TemporaryDirectory() as folder:
            root = pathlib.Path(folder)
            (root/'.git').mkdir()
            (root/'backend').mkdir()
            source = root/'backend/server.py'
            source.write_text('public code')
            source.chmod(0o600)
            secret = root/'.env'
            secret.write_text('APP_PASSWORD=private-test-only')
            secret.chmod(0o600)
            def fake(command, **kwargs):
                if command[1:4] == ['remote','get-url','origin']:
                    return installer.REPOSITORY
                if command[1:] == ['ls-files','-z']:
                    return 'backend/server.py\0'
                return ''
            with patch.object(installer, 'run', side_effect=fake), patch.object(installer.subprocess, 'run', return_value=SimpleNamespace(returncode=1)):
                installer.prepare_repository(root, update=False)
            self.assertEqual(secret.read_text(), 'APP_PASSWORD=private-test-only')
            if os.name == 'posix':
                self.assertEqual(source.stat().st_mode & 0o777, 0o644)
                self.assertEqual(secret.stat().st_mode & 0o777, 0o600)
