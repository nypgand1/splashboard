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
        app_css = asset_token(root / 'assets' / 'app.css')
        tables_css = asset_token(root / 'assets' / 'tables.css')
        report_css = asset_token(root / 'assets' / 'report.css')
        report_js = asset_token(root / 'assets' / 'report_canvas.js')
        report_blocks_js = asset_token(root / 'assets' / 'report_blocks.js')
        report_pdf_js = asset_token(root / 'assets' / 'report_pdf.js')
        self.assertIn(f'/assets/app.css?m={app_css}', css)
        self.assertIn(f'/assets/tables.css?m={tables_css}', css)
        self.assertIn(f'/assets/report.css?m={report_css}', css)
        self.assertNotIn('report.css?m=315532801', css)
        self.assertIn(f'/assets/report_blocks.js?m={report_blocks_js}', scripts)
        self.assertIn(f'/assets/report_canvas.js?m={report_js}', scripts)
        self.assertIn(f'/assets/report_pdf.js?m={report_pdf_js}', scripts)
        self.assertNotIn('report_canvas.js?m=315532801', scripts)

    def test_import_links_assets_before_any_request(self):
        self.assertTrue(app.app._got_first_request['setup_server'])
        css_files = app.app.css._resources._resources
        script_files = app.app.scripts._resources._resources
        self.assertTrue(any(item.get('asset_path') == 'report.css' for item in css_files))
        self.assertTrue(any(item.get('asset_path') == 'page_nav.js' for item in script_files))
        # index() interpolates these two strings into every path, including a
        # first GET of /team-stats, before FastAPI would have run this hook.
        css = app.app._generate_css_dist_html()
        scripts = app.app._generate_scripts_html()
        self.assertIn('/assets/app.css?m=', css)
        self.assertIn('/assets/tables.css?m=', css)
        self.assertIn('/assets/report.css?m=', css)
        self.assertIn('/assets/page_nav.js?m=', scripts)
        self.assertIn('/assets/report_blocks.js?m=', scripts)
        self.assertIn('/assets/report_canvas.js?m=', scripts)
        self.assertIn('/assets/report_pdf.js?m=', scripts)
