"""Local Dash process for browser smoke. Blocks live Synergy."""
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def apply_patches():
    os.environ['SPLASHBOARD_E2E'] = '1'

    from tests.e2e.fixtures import FakeReport, id_table, season_df, status_for
    from synergy_inbounder import communicator, parser, runtime_cache

    import pandas as pd

    from synergy_inbounder.settings import SYNERGY_EASL_ORGANIZATION_ID

    frame = season_df()
    names = id_table()
    names.update({
        'easl-home': 'Taoyuan Pauian Pilots',
        'easl-away': 'Utsunomiya Brex',
        'easl-eastern': 'Hong Kong Eastern',
        'easl-venue': 'Studio City Event Center',
    })
    easl_frame = pd.DataFrame([
        {
            'startTimeLocal': '2026-03-22T18:00:00',
            'fixtureId': 'easl-final',
            'fixtureType': 'FINAL',
            'status': 'CONFIRMED',
            'venueId': 'easl-venue',
            'teamIdHome': 'easl-home',
            'teamScoreHome': 81,
            'teamIdAway': 'easl-away',
            'teamScoreAway': 90,
        },
        {
            'startTimeLocal': '2026-10-03T19:10:00',
            'fixtureId': 'easl-eastern',
            'fixtureType': 'FINAL',
            'status': 'CONFIRMED',
            'venueId': 'easl-venue',
            'teamIdHome': 'easl-home',
            'teamScoreHome': 79,
            'teamIdAway': 'easl-eastern',
            'teamScoreAway': 72,
        },
        {
            'startTimeLocal': '2027-03-09T00:00:00',
            'fixtureId': 'easl-draft',
            'fixtureType': None,
            'status': 'DRAFT',
            'venueId': None,
            'teamIdHome': None,
            'teamScoreHome': None,
            'teamIdAway': None,
            'teamScoreAway': None,
        },
    ])

    def _blocked(*_args, **_kwargs):
        raise RuntimeError('e2e fixtures only')

    def _season(org_id, *_args, **_kwargs):
        if str(org_id) == SYNERGY_EASL_ORGANIZATION_ID:
            return easl_frame.copy()
        return frame.copy()

    parser.Parser.parse_season_game_list_df = staticmethod(_season)
    parser.Parser.parse_id_tables = staticmethod(lambda *_a, **_k: dict(names))
    runtime_cache.get_cached_report.factory = lambda _game_id: FakeReport()
    runtime_cache.prefetch_latest_games = lambda *_a, **_k: None
    runtime_cache.warmup_game_report = lambda *_a, **_k: None
    runtime_cache.lookup_game_status = lambda game_id, organization_id=None: status_for(game_id)

    for name in dir(communicator.Communicator):
        if name.startswith('get_') or name.startswith('_load'):
            attr = getattr(communicator.Communicator, name)
            if callable(attr):
                setattr(communicator.Communicator, name, staticmethod(_blocked))


def main(port):
    apply_patches()
    import uvicorn
    import app  # noqa: F401
    uvicorn.run(app.server, host='127.0.0.1', port=int(port), log_level='warning')


if __name__ == '__main__':
    main(sys.argv[1])
