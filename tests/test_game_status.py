import unittest

from synergy_inbounder.game_status import (
    BADGE_STYLES,
    SCORE_EM_DASH,
    SCORE_VS,
    badge_label,
    format_score_display,
    is_finished_status,
    is_live_play_status,
    score_is_clickable,
    status_bucket,
)
from synergy_inbounder.runtime_cache import should_use_live_endpoints


class StatusBucketTests(unittest.TestCase):
    def test_finished_and_live_play_sets(self):
        self.assertEqual(status_bucket('FINISHED'), 'finished')
        self.assertEqual(status_bucket(' CONFIRMED '), 'finished')
        for status in ('PENDING', 'ABOUT_TO_START', 'WARM_UP', 'ON_PITCH', 'IN_PROGRESS'):
            self.assertEqual(status_bucket(status), 'live', status)
            self.assertTrue(is_live_play_status(status))
        for status in ('SCHEDULED', 'IF_NEEDED', 'DRAFT', 'POSTPONED', '', None, 'WEIRD'):
            self.assertEqual(status_bucket(status), 'unplayed', status)
        self.assertEqual(status_bucket('CANCELLED'), 'void')
        self.assertEqual(status_bucket('BYE'), 'void')
        self.assertEqual(status_bucket('ABANDONED'), 'void')
        self.assertTrue(is_finished_status('FINISHED'))
        self.assertFalse(is_finished_status('PENDING'))

    def test_live_endpoints_only_for_live_play(self):
        self.assertTrue(should_use_live_endpoints(status='PENDING'))
        self.assertTrue(should_use_live_endpoints(status='IN_PROGRESS'))
        self.assertFalse(should_use_live_endpoints(status='FINISHED'))
        self.assertFalse(should_use_live_endpoints(status='SCHEDULED'))
        self.assertFalse(should_use_live_endpoints(status='IF_NEEDED'))
        self.assertFalse(should_use_live_endpoints(status='CANCELLED'))
        self.assertFalse(should_use_live_endpoints(status='ABANDONED'))

    def test_score_display_and_clickable(self):
        self.assertEqual(format_score_display('SCHEDULED', 1, 2), SCORE_EM_DASH)
        self.assertFalse(score_is_clickable('IF_NEEDED'))
        self.assertFalse(score_is_clickable('CANCELLED'))
        self.assertEqual(format_score_display('FINISHED', 88, 79), '88 : 79')
        self.assertEqual(format_score_display('IN_PROGRESS', 0, 0), '0 : 0')
        self.assertEqual(format_score_display('PENDING', None, None), SCORE_VS)
        self.assertEqual(format_score_display('ABANDONED', 12, 10), '12 : 10')
        self.assertEqual(format_score_display('ABANDONED', None, None), SCORE_VS)
        self.assertTrue(score_is_clickable('ABANDONED'))
        self.assertTrue(score_is_clickable('PENDING'))

    def test_badge_label_is_raw_status(self):
        self.assertEqual(badge_label('IN_PROGRESS'), 'IN_PROGRESS')
        self.assertEqual(badge_label('IF_NEEDED'), 'IF_NEEDED')
        self.assertEqual(badge_label(''), 'UNKNOWN')
        self.assertEqual(BADGE_STYLES['live']['color'], '#dc2626')
        self.assertEqual(BADGE_STYLES['unplayed']['color'], '#0284c7')
        self.assertEqual(BADGE_STYLES['void']['color'], '#334155')
