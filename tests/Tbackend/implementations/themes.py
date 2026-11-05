import os
import tempfile
import unittest

from flask import Flask

from frontend.ui import ui


class TestArtRoute(unittest.TestCase):
    def setUp(self):
        app = Flask(__name__)
        app.register_blueprint(ui)
        self.c = app.test_client()

    def test_placeholder_when_missing(self):
        r = self.c.get('/art/marvel/spider-man')
        self.assertEqual(r.status_code, 200)
        self.assertIn(b'art/marvel/spider-man.jpg', r.data)

    def test_rejects_odd_names(self):
        for u in ('/art/marvel/Bad_Name', '/art/MARVEL/x', '/art/a/..%2f..'):
            self.assertEqual(self.c.get(u).status_code, 404)

    def test_own_file_wins(self):
        with tempfile.TemporaryDirectory() as d:
            os.makedirs(os.path.join(d, 'justice'))
            with open(os.path.join(d, 'justice', 'batman.png'), 'wb') as f:
                f.write(b'PNGDATA')
            os.environ['KAPOWARR_ART_DIR'] = d
            try:
                r = self.c.get('/art/justice/batman')
                self.assertEqual(r.data, b'PNGDATA')
            finally:
                del os.environ['KAPOWARR_ART_DIR']
