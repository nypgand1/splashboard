# -*- coding: utf-8 -*-
import re
import unittest
from html.parser import HTMLParser

from auth import login_html


class _DomCollector(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.elements = []
        self._stack = []
        self._styles = []
        self._in_style = False

    def handle_starttag(self, tag, attrs):
        attr_map = dict(attrs)
        node = {'tag': tag.lower(), 'attrs': attr_map, 'text': []}
        self.elements.append(node)
        if tag.lower() not in {'input', 'img', 'meta', 'br', 'hr', 'link'}:
            self._stack.append(node)
        if tag.lower() == 'style':
            self._in_style = True

    def handle_endtag(self, tag):
        t = tag.lower()
        if t == 'style':
            self._in_style = False
        for idx in range(len(self._stack) - 1, -1, -1):
            if self._stack[idx]['tag'] == t:
                del self._stack[idx:]
                break

    def handle_data(self, data):
        if self._in_style:
            self._styles.append(data)
        if self._stack:
            self._stack[-1]['text'].append(data)

    @property
    def css(self):
        return ''.join(self._styles)

    def by_tag(self, tag):
        return [el for el in self.elements if el['tag'] == tag.lower()]


def _parse(html_text):
    parser = _DomCollector()
    parser.feed(html_text)
    parser.close()
    return parser


def _css_block(css_text, selector):
    pattern = re.compile(re.escape(selector) + r'\s*\{([^}]*)\}', re.DOTALL)
    match = pattern.search(css_text)
    return match.group(1) if match else ''


class AuthLoginButtonTests(unittest.TestCase):
    def test_form_structure_and_google_g_svg(self):
        doc = _parse(login_html.form('/team-stats?season=2026'))

        forms = doc.by_tag('form')
        self.assertEqual(len(forms), 1)
        self.assertEqual(forms[0]['attrs'].get('method', '').lower(), 'post')
        self.assertEqual(forms[0]['attrs'].get('action'), '/login')

        inputs = doc.by_tag('input')
        hidden_next = [
            el for el in inputs
            if el['attrs'].get('type') == 'hidden' and el['attrs'].get('name') == 'next'
        ]
        self.assertEqual(len(hidden_next), 1)
        self.assertEqual(hidden_next[0]['attrs'].get('value'), '/team-stats?season=2026')

        buttons = doc.by_tag('button')
        self.assertEqual(len(buttons), 1)
        btn = buttons[0]
        self.assertEqual(btn['attrs'].get('type'), 'submit')
        classes = (btn['attrs'].get('class') or '').split()
        self.assertIn('google-sign-in', classes)
        btn_text = ' '.join(''.join(btn['text']).split())
        self.assertEqual(btn_text, 'Continue with Google')

        svgs = doc.by_tag('svg')
        self.assertEqual(len(svgs), 1)
        svg = svgs[0]
        self.assertEqual(svg['attrs'].get('aria-hidden'), 'true')
        self.assertEqual(svg['attrs'].get('width'), '20')
        self.assertEqual(svg['attrs'].get('height'), '20')

        self.assertEqual(doc.by_tag('img'), [])

    def test_form_button_css_contract(self):
        doc = _parse(login_html.form('/'))
        css = doc.css

        btn_rule = _css_block(css, 'button.google-sign-in')
        self.assertIn('background: #ffffff', btn_rule)
        self.assertNotIn('#0077b6', btn_rule)
        self.assertIn('border: 1px solid #747775', btn_rule)
        self.assertIn('border-radius: 4px', btn_rule)
        self.assertIn('height: 40px', btn_rule)
        self.assertIn('color: #1f1f1f', btn_rule)

        hover_rule = _css_block(css, 'button.google-sign-in:hover')
        self.assertIn('background: #f8fafd', hover_rule)

        focus_rule = _css_block(css, 'button.google-sign-in:focus-visible')
        self.assertIn('outline: 2px solid #0077b6', focus_rule)

    def test_error_messages_have_no_button_or_svg_and_brand_back_link(self):
        errors = (
            login_html.UNAVAILABLE,
            login_html.NOT_ON_LIST,
            login_html.CANCELLED,
            login_html.INCOMPLETE,
            login_html.UNVERIFIED,
        )
        for err in errors:
            with self.subTest(error=err):
                html_text = login_html.message(err)
                doc = _parse(html_text)
                self.assertEqual(doc.by_tag('button'), [])
                self.assertEqual(doc.by_tag('svg'), [])
                self.assertEqual(doc.by_tag('img'), [])

                links = doc.by_tag('a')
                self.assertTrue(any(el['attrs'].get('href') == '/login' for el in links))

                link_rule = _css_block(doc.css, 'a')
                self.assertIn('color: #0077b6', link_rule)
