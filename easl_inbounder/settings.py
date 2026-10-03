# -*- coding: utf-8 -*-
"""Public EASL schedule host and the seasons Home can select."""

EASL_API_BASE = 'https://easl.joshricha.com/api/v1'
EASL_MATCHES_URL = EASL_API_BASE + '/matches'

# Newest first. Labels are the Home season control. Ids are the query seasonId.
EASL_SEASONS = (
    ('2026-27', '1409787d-a683-11f1-aea7-b596f55be5ed'),
    ('2025-26', '77441bb3-9759-11f0-b659-0561c09a0222'),
    ('2024-25', '57cefc32-5ace-11ef-81a0-3d1f6018efb7'),
    ('2023-24', 'c24ce68a-6420-11ee-9daf-6b6188281bd0'),
)
EASL_SEASON_ID = dict(EASL_SEASONS)['2026-27']
