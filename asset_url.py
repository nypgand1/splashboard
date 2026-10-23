"""Dash asset ?m= tokens from file bytes, not mtime.

Fly's Paketo buildpack freezes asset mtimes at 1980-01-01, so a mtime
query never changes and phones keep the previous CSS.
"""
import hashlib
import os

_FONT_URL = '/assets/NotoSansTC-Regular.ttf'
_font_fetch_url = None


def asset_token(path):
    digest = hashlib.sha256()
    with open(path, 'rb') as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b''):
            digest.update(chunk)
    return digest.hexdigest()[:16]


def stamp_asset_urls(resources):
    """Replace Dash's mtime ?m= with a content hash for files in assets/."""
    original = resources._filter_resources

    def wrapped(all_resources, dev_bundles=False):
        found = original(all_resources, dev_bundles)
        paths = {
            src['asset_path']: src['filepath']
            for src in all_resources
            if src.get('asset_path') and src.get('filepath')
        }
        for item in found:
            path = paths.get(item.get('asset_path'))
            if path and 'ts' in item:
                item['ts'] = asset_token(path)
        return found

    resources._filter_resources = wrapped


def font_fetch_url():
    """Fetch URL for the PDF font. The jsPDF VFS name stays unstamped."""
    global _font_fetch_url
    if _font_fetch_url is None:
        path = os.path.join(os.path.dirname(__file__), 'assets', 'NotoSansTC-Regular.ttf')
        _font_fetch_url = _FONT_URL + '?m=' + asset_token(path)
    return _font_fetch_url
