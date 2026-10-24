import os
import tempfile
import unittest
from pathlib import Path

import app
from asset_url import asset_token, font_fetch_url


class AssetTokenTests(unittest.TestCase):
    def test_same_bytes_keep_the_token_when_mtime_changes(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'report.css'
            path.write_bytes(b'body{}')
            os.utime(path, (315532801, 315532801))
            first = asset_token(path)
            os.utime(path, (315532801, 1700000000))
            self.assertEqual(asset_token(path), first)
            self.assertEqual(len(first), 16)
            self.assertNotIn('.', first)
            path.write_bytes(b'body{color:red}')
            self.assertNotEqual(asset_token(path), first)

    def test_font_fetch_url_uses_the_content_hash(self):
        root = Path(__file__).resolve().parents[1]
        token = asset_token(root / 'assets' / 'NotoSansTC-Regular.ttf')
        stamped = font_fetch_url()
        self.assertEqual(stamped, f'/assets/NotoSansTC-Regular.ttf?m={token}')
        self.assertEqual(font_fetch_url(), stamped)


class AssetIndexTests(unittest.TestCase):
    def test_linked_assets_use_the_content_hash(self):
        # _setup_server() moves dash.callback specs off GLOBAL_CALLBACK_LIST.
        css_files = app.app.css._resources._resources
        if not any(item.get('asset_path') == 'report.css' for item in css_files):
            app.app._walk_assets_directory()
        css = app.app._generate_css_dist_html()
        scripts = app.app._generate_scripts_html()
        root = Path(__file__).resolve().parents[1]
        report_css = asset_token(root / 'assets' / 'report.css')
        report_js = asset_token(root / 'assets' / 'report_canvas.js')
        self.assertIn(f'/assets/report.css?m={report_css}', css)
        self.assertNotIn('report.css?m=315532801', css)
        self.assertIn(f'/assets/report_canvas.js?m={report_js}', scripts)
        self.assertNotIn('report_canvas.js?m=315532801', scripts)
