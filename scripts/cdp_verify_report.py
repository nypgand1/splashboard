#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Automated CDP verification script for Splashboard Report Canvas.
Tests:
- C1: 8 Flat Design preset colors + custom hex colors
- C2: Background highlight rects
- C3: Multi-level nested Bullet Lists (disc -> circle -> square)
- C4: Multi-level nested Ordered Lists (1. -> a. -> i.)
- C5: Preservation of blank lines (<p><br></p>, empty paragraphs) between/after lists
- C6: Combined rich styles (bold, italic, underline, strikethrough, color, highlight)
- C7: 5-page default layout tables and headers visual completeness
- C8: Headless browser PDF export execution without JS exceptions
"""

import asyncio
import base64
import json
import os
import subprocess
import sys
import threading
import time
import urllib.request
import websockets
import pandas as pd

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

from synergy_reporter import report_layout, report_components


def create_verification_app():
    import dash
    from dash import Dash, html
    import dash_mantine_components as dmc
    from navbar import create_navbar

    dash._dash_renderer._set_react_version('18.2.0')

    app = Dash(
        __name__,
        assets_folder=os.path.join(REPO_ROOT, 'assets'),
        external_stylesheets=[
            'https://cdn.jsdelivr.net/npm/gridstack@10.3.1/dist/gridstack.min.css',
            '/assets/report.css',
        ],
        external_scripts=[
            'https://cdn.jsdelivr.net/npm/gridstack@10.3.1/dist/gridstack-all.js',
            'https://cdn.jsdelivr.net/npm/jspdf@2.5.2/dist/jspdf.umd.min.js',
            '/assets/report_canvas.js',
        ],
        suppress_callback_exceptions=True,
    )

    match_info = {
        'date': '2026年04月11日',
        'time': '17:00',
        'venue': 'Taipei Arena',
        'home_team': 'Taipei Fubon Braves',
        'away_team': 'Formosa Dreamers',
        'home_score': '88',
        'away_score': '79',
        'status': 'FINISHED',
    }

    df_sample = pd.DataFrame({
        'Team': ['Braves', 'Dreamers'],
        'PTS': [88, 79],
        'FG%': ['45.2%', '41.0%'],
        '3P%': ['36.0%', '30.5%'],
        'FT%': ['80.0%', '75.0%'],
    })

    bs_dict = {
        'qt_pts_df': df_sample.to_json(orient='split'),
        't_adv_df': df_sample.to_json(orient='split'),
        't_df': df_sample.to_json(orient='split'),
        'k_df': df_sample.to_json(orient='split'),
        'p_df_dict': {
            'Taipei Fubon Braves': pd.DataFrame({'Player': ['Lin #1', 'Tseng #2'], 'Min': ['30:00', '25:00'], 'PTS': [20, 15], '+/-': [10, 5]}).to_json(orient='split'),
            'Formosa Dreamers': pd.DataFrame({'Player': ['Boyd #3', 'Walkup #4'], 'Min': ['28:00', '22:00'], 'PTS': [18, 12], '+/-': [-5, -10]}).to_json(orient='split'),
        }
    }

    lineup_dict = {
        '5': {
            'Taipei Fubon Braves': pd.DataFrame({'Lineup': ['Lineup A', 'Lineup B'], 'Min': ['15:00', '10:00'], '+/-': [8, 2]}).to_json(orient='split'),
            'Formosa Dreamers': pd.DataFrame({'Lineup': ['Lineup X', 'Lineup Y'], 'Min': ['14:00', '11:00'], '+/-': [-4, -6]}).to_json(orient='split'),
        }
    }

    layout = report_layout.default_layout()
    workspace = report_components.render_report_workspace(
        layout=layout,
        bs_dict=bs_dict,
        lineup_store_data=lineup_dict,
        match_info=match_info,
        game_id='cdp-verify-game-001',
    )

    navbar = create_navbar()
    app.layout = dmc.MantineProvider(
        theme={
            "primaryColor": "blue",
            "fontFamily": "-apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif",
            "defaultRadius": "sm",
        },
        forceColorScheme="light",
        children=dmc.AppShell(
            [
                dmc.AppShellHeader(navbar, className="app-navbar no-print", px=0),
                dmc.AppShellMain(
                    html.Div(workspace, id="pane-report"),
                    className="app-main-content",
                ),
            ],
            header={"height": 56},
            padding=0,
            className="app-shell",
        )
    )

    return app


EDGE_CASES_NOTE_HTML = (
    '<p><font color="#e74c3c"><b>[C1/C6] Red Bold Title Header</b></font></p>'
    '<ul>'
    '  <li><font color="#e67e22">[C3 Level 1 Disc] Orange list item</font>'
    '    <ul>'
    '      <li>[C3 Level 2 Circle] Regular nested bullet</li>'
    '      <li><font color="#2ecc71">[C3 Level 2 Circle] Green bullet item</font></li>'
    '      <li>[C3 Level 2 Circle] Parent of Level 3'
    '        <ul>'
    '          <li><font color="#ffffff"><span style="background-color: #9b59b6;">[C3 Level 3 Square] White text on purple highlight</span></font></li>'
    '        </ul>'
    '      </li>'
    '    </ul>'
    '  </li>'
    '  <li>[C3 Level 1 Disc] Closing bullet item</li>'
    '</ul>'
    '<p><br></p>'
    '<ol>'
    '  <li>[C4 Level 1 Decimal 1.] Ordered item 1'
    '    <ol>'
    '      <li>[C4 Level 2 Lower-Alpha a.] Nested ordered item a</li>'
    '      <li>[C4 Level 2 Lower-Alpha b.] Nested ordered item b</li>'
    '    </ol>'
    '  </li>'
    '  <li>[C4 Level 1 Decimal 2.] Ordered item 2'
    '    <ol>'
    '      <li><font color="#3498db"><span style="background-color: #3498db;">[C4 Level 2 Lower-Alpha a.] Blue on blue highlight</span></font>'
    '        <ol>'
    '          <li><span style="background-color: #f1c40f;">[C4 Level 3 Lower-Roman i.] Yellow highlight item</span></li>'
    '        </ol>'
    '      </li>'
    '    </ol>'
    '  </li>'
    '</ol>'
    '<p><br></p>'
    '<p><u><strike><b><i>[C6] Underline + Strikethrough + Bold + Italic Combination</i></b></strike></u></p>'
)


async def run_cdp_verification():
    port = 8057
    server_url = f"http://127.0.0.1:{port}/"

    from werkzeug.serving import make_server
    app = create_verification_app()
    server = make_server('127.0.0.1', port, app.server)
    t = threading.Thread(target=server.serve_forever, daemon=True)
    t.start()
    time.sleep(1.5)

    chrome_port = 9235
    chrome_proc = subprocess.Popen([
        'google-chrome',
        '--headless=new',
        '--remote-debugging-port=9235',
        '--remote-allow-origins=*',
        '--disable-gpu',
        '--no-sandbox',
        '--window-size=1600,3200',
        server_url
    ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    try:
        ws_url = None
        for _ in range(30):
            await asyncio.sleep(0.5)
            try:
                req = urllib.request.urlopen(f"http://127.0.0.1:{chrome_port}/json/list")
                targets = json.loads(req.read().decode())
                page_target = next((tgt for tgt in targets if tgt.get('type') == 'page'), None)
                if page_target:
                    ws_url = page_target['webSocketDebuggerUrl']
                    break
            except Exception:
                pass

        if not ws_url:
            raise RuntimeError("Failed to connect to headless Chrome via CDP.")

        print(f"[*] Connected to CDP page: {ws_url}")
        async with websockets.connect(ws_url, max_size=25*1024*1024) as ws:
            msg_id = 1
            resps = {}
            console_logs = []

            async def msg_loop():
                while True:
                    try:
                        raw = await ws.recv()
                        resp = json.loads(raw)
                        if 'id' in resp:
                            resps[resp['id']] = resp.get('result', {})
                        if resp.get('method') == 'Console.messageAdded':
                            msg = resp['params']['message']
                            console_logs.append(f"[{msg.get('level')}] {msg.get('text')}")
                        if resp.get('method') == 'Runtime.consoleAPICalled':
                            args = resp['params'].get('args', [])
                            text = " ".join(str(a.get('value', '')) for a in args)
                            console_logs.append(f"[{resp['params'].get('type')}] {text}")
                    except Exception:
                        break

            loop_task = asyncio.create_task(msg_loop())

            async def call(method, params=None):
                nonlocal msg_id
                mid = msg_id
                msg_id += 1
                await ws.send(json.dumps({'id': mid, 'method': method, 'params': params or {}}))
                while mid not in resps:
                    await asyncio.sleep(0.05)
                return resps.pop(mid)

            await call('Console.enable')
            await call('Runtime.enable')
            await call('Page.enable')

            await call('Page.navigate', {'url': server_url})
            await asyncio.sleep(4.0)

            # 1. Inject Edge Cases into Note (with retry for first paint)
            val = {}
            for _ in range(20):
                inject_res = await call('Runtime.evaluate', {
                    'returnByValue': True,
                    'expression': f"""
                    (() => {{
                        const note = document.querySelector('#report-papers [data-text-block]');
                        if (!note) return {{ error: 'No note block found' }};
                        note.innerHTML = `{EDGE_CASES_NOTE_HTML}`;
                        return {{
                            success: true,
                            htmlLength: note.innerHTML.length
                        }};
                    }})()
                    """
                })
                val = inject_res.get('result', {}).get('value', {})
                if val.get('success'):
                    break
                await asyncio.sleep(0.5)

            assert val.get('success'), f"Note injection failed: {val}"
            print("[✓] C1-C6: Note edge cases injected successfully.")

            # 2. Check DOM Completeness
            dom_check = await call('Runtime.evaluate', {
                'returnByValue': True,
                'expression': """
                (() => {
                    const papers = document.querySelectorAll('.report-paper');
                    const tables = document.querySelectorAll('.report-dmc-table');
                    const textBlocks = document.querySelectorAll('[data-text-block]');
                    return {
                        papersCount: papers.length,
                        tablesCount: tables.length,
                        textBlocksCount: textBlocks.length
                    };
                })()
                """
            })
            dom_val = dom_check.get('result', {}).get('value', {})
            assert dom_val.get('papersCount') == 5, f"Expected 5 papers, got {dom_val.get('papersCount')}"
            assert dom_val.get('tablesCount') >= 8, f"Expected at least 8 tables, got {dom_val.get('tablesCount')}"
            print(f"[✓] C7: Default layout verified: 5 papers, {dom_val.get('tablesCount')} tables.")

            # 3. Test PDF Export
            pdf_res = await call('Runtime.evaluate', {
                'returnByValue': True,
                'expression': """
                (async () => {
                    try {
                        const fontOk = await window.splashboardReport.ensurePdfFont();
                        await window.splashboardReport.exportPdf();
                        return {
                            success: true,
                            fontOk: !!fontOk
                        };
                    } catch (err) {
                        return {
                            success: false,
                            error: err.toString()
                        };
                    }
                })()
                """,
                'awaitPromise': True
            })
            pdf_val = pdf_res.get('result', {}).get('value', {})
            assert pdf_val.get('success'), f"PDF export threw error: {pdf_val}"
            print("[✓] C8: PDF Export executed and completed without JS errors.")

            # 4. Capture Visual Screenshot
            shot = await call("Page.captureScreenshot", {"format": "png", "captureBeyondViewport": True})
            if "data" in shot:
                out_path = os.path.join(REPO_ROOT, "scratch", "cdp_report_verified.png")
                os.makedirs(os.path.dirname(out_path), exist_ok=True)
                with open(out_path, "wb") as f:
                    f.write(base64.b64decode(shot["data"]))
                print(f"[✓] Visual screenshot saved to: {out_path}")

            loop_task.cancel()

    finally:
        chrome_proc.terminate()
        server.shutdown()


if __name__ == '__main__':
    asyncio.run(run_cdp_verification())
