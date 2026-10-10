"""Dash asset ?m= tokens from file bytes, not mtime.

Fly's Paketo buildpack freezes asset mtimes at 1980-01-01, so a mtime
query never changes and phones keep the previous CSS.
"""
import hashlib


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
