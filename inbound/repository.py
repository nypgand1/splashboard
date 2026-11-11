# -*- coding: utf-8 -*-
"""Unified data-fetching facade over Communicator and Parser for domain/page consumers."""
from synergy_inbounder.communicator import Communicator
from synergy_inbounder.parser import Parser


def fetch_pbp(org_id, fixture_id, status):
    return Communicator.get_game_play_by_play_synergy(
        org_id, fixture_id, live=False, fixture_status=status,
    )


def fetch_season_totals(org_id, season_id):
    return Communicator.get_season_team_totals(org_id, season_id)


def fetch_season_periods(org_id, season_id):
    return Communicator.get_season_team_periods(org_id, season_id)


def fetch_fixture_starters(org_id, fixture_id, status):
    payload = Communicator.get_game_player_stats_synergy(
        org_id, fixture_id, live=False, fixture_status=status,
    )
    return Parser.starter_dict_from_rows((payload or {}).get('data'))


def fetch_fixture_roster(org_id, fixture_id, status):
    payload = Communicator.get_fixture_roster_synergy(
        org_id, fixture_id, fixture_status=status,
    )
    return Parser._roster_from_fixture_json(payload)


def fetch_fixture_player_rows(org_id, fixture_id, status):
    payload = Communicator.get_game_player_stats_synergy(
        org_id, fixture_id, live=False, fixture_status=status,
    )
    return Parser._roster_from_json(payload or {})
