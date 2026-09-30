import base64
import unittest

import pandas as pd

from synergy_reporter.post_game_report import PostGameReport
from synergy_reporter.shot_chart import (
    COLD,
    HOT,
    MID,
    court_data_uri,
    court_markup,
    court_zones,
    report_shot_chart_payload,
    format_fg_percent,
    period_chips,
    player_options,
    shot_menu_plan,
    zone_appearance,
)


def _shot(**kwargs):
    row = {
        "entityId": "away",
        "personId": "p1",
        "Player": "Lin",
        "shirtNumber": "7",
        "eventType": "2pt",
        "periodId": 1,
        "success": True,
        "x": 6,
        "y": 50,
    }
    row.update(kwargs)
    return row


def _by_area(zones):
    return {zone["area"]: zone for zone in zones}


class PlayByPlayCoordinateTests(unittest.TestCase):
    def test_view_keeps_coordinates_and_jersey(self):
        report = PostGameReport.__new__(PostGameReport)
        report.playbyplay_df = pd.DataFrame([{
            'timestamp': 't',
            'sequence': 1,
            'periodId': 1,
            'clock': 'PT10M',
            'entityId': 'away',
            'personId': 'p1',
            'eventType': '2pt',
            'subType': 'jumpshot',
            'success': True,
            'scores': None,
            'options': None,
            'x': 6.0,
            'y': 50.0,
        }])
        report.id_table = {'away': 'Away', 'p1': 'Lin'}
        report.roster = [{'personId': 'p1', 'shirtNumber': '7'}]
        report.starter_dict = {'away': []}
        report._play_by_play_view = None
        view = report.get_play_by_play_df()
        self.assertEqual(view.iloc[0]['x'], 6.0)
        self.assertEqual(view.iloc[0]['y'], 50.0)
        self.assertEqual(str(view.iloc[0]['shirtNumber']), '7')
        self.assertEqual(view.iloc[0]['Player'], 'Lin')


class ZoneLabelTests(unittest.TestCase):
    def test_fg_percent_is_one_decimal_half_up(self):
        self.assertEqual(format_fg_percent(2, 3), "66.7%")
        self.assertEqual(format_fg_percent(3, 4), "75.0%")
        self.assertEqual(format_fg_percent(0, 7), "0.0%")
        self.assertEqual(format_fg_percent(1, 1), "100.0%")
        self.assertEqual(format_fg_percent(1, 16), "6.3%")
        self.assertEqual(format_fg_percent(0, 0), "-")

    def test_efg_bands_use_the_exact_ratio(self):
        even = zone_appearance(1, 0, 2, 2)
        self.assertEqual(even["fg"], "50.0%")
        self.assertEqual(even["fill"], HOT)
        floor = zone_appearance(2, 0, 5, 5)
        self.assertEqual(floor["fg"], "40.0%")
        self.assertEqual(floor["fill"], MID)
        cold = zone_appearance(1, 0, 3, 3)
        self.assertEqual(cold["fg"], "33.3%")
        self.assertEqual(cold["fill"], COLD)
        self.assertEqual(zone_appearance(2, 0, 3, 3)["fill"], HOT)
        threes = zone_appearance(0, 1, 2, 2)
        self.assertEqual(threes["fg"], "50.0%")
        self.assertEqual(threes["count"], "1 / 2")
        self.assertEqual(threes["fill"], HOT)

    def test_zero_attempts_are_a_dash_without_fill(self):
        empty = zone_appearance(0, 0, 0, 8)
        self.assertEqual(empty["fg"], "-")
        self.assertEqual(empty["count"], "")
        self.assertIsNone(empty["fill"])
        self.assertIsNone(empty["opacity"])

    def test_opacity_follows_this_court_share(self):
        thin = zone_appearance(1, 0, 1, 20)
        self.assertAlmostEqual(thin["opacity"], 0.20, places=2)
        middle = zone_appearance(1, 0, 1, 8)
        self.assertAlmostEqual(middle["opacity"], 0.45, places=2)
        thick = zone_appearance(5, 0, 5, 20)
        self.assertAlmostEqual(thick["opacity"], 0.45, places=2)
        capped = zone_appearance(8, 0, 8, 10)
        self.assertAlmostEqual(capped["opacity"], 0.45, places=2)


class PeriodAndPlayerTests(unittest.TestCase):
    def test_chips_follow_box_score_order_from_period_ids(self):
        chips = period_chips([3, 1, 2, 11, 1])
        self.assertEqual(
            [(chip["label"], chip["value"]) for chip in chips],
            [("All", "all"), ("1Q", "1"), ("2Q", "2"), ("1H", "h1"), ("3Q", "3"), ("OT", "11")],
        )
        self.assertEqual(
            [chip["label"] for chip in period_chips([3, 4, 12])],
            ["All", "3Q", "4Q", "2H", "2OT"],
        )
        self.assertEqual(period_chips([])[0]["value"], "all")

    def test_player_menu_is_full_game_attempts_sorted_by_jersey(self):
        events = [
            _shot(personId="late", Player="Late", shirtNumber="12", periodId=4),
            _shot(personId="early", Player="Early", shirtNumber="4", periodId=1),
            _shot(personId="other", Player="Chen", shirtNumber="9", entityId="home"),
            _shot(eventType="freeThrow", personId="ft", Player="Free", shirtNumber="1"),
            _shot(personId="nonum", Player="NoNum", shirtNumber=None),
        ]
        labels = [item["label"] for item in player_options(events, "away")]
        self.assertEqual(labels, ["All", "#4 Early", "#12 Late", "NoNum"])


class ReportShotChartPayloadTests(unittest.TestCase):
    def test_empty_frame_has_no_courts(self):
        self.assertEqual(
            report_shot_chart_payload(None, 'away', 'home', 'Dreamers', 'Braves')['_ui'],
            'empty',
        )
        self.assertEqual(
            report_shot_chart_payload(pd.DataFrame(), 'away', 'home', 'Dreamers', 'Braves')['_ui'],
            'empty',
        )

    def test_full_game_counts_every_player_on_both_teams(self):
        events = [
            _shot(personId='p1', x=6, y=50),
            _shot(personId='p2', Player='Chen', shirtNumber='8', x=6, y=50, periodId=3),
            _shot(entityId='home', personId='h1', x=94, y=50, success=False),
        ]
        payload = report_shot_chart_payload(events, 'away', 'home', 'Dreamers', 'Braves')
        self.assertEqual(payload['_ui'], 'ready')
        self.assertEqual(payload['away_name'], 'Dreamers')
        self.assertEqual(payload['home_name'], 'Braves')
        away = base64.b64decode(payload['away_src'].split(',', 1)[1]).decode('utf-8')
        home = base64.b64decode(payload['home_src'].split(',', 1)[1]).decode('utf-8')
        self.assertIn('2 / 2', away)
        self.assertIn('0 / 1', home)

    def test_rows_without_chartable_shots_still_draw_dashes(self):
        payload = report_shot_chart_payload(
            pd.DataFrame([_shot(eventType='freeThrow')]),
            'away', 'home', 'Dreamers', 'Braves',
        )
        self.assertEqual(payload['_ui'], 'ready')
        svg = base64.b64decode(payload['away_src'].split(',', 1)[1]).decode('utf-8')
        self.assertIn('font-size="16">-</text>', svg)


class CourtZoneTests(unittest.TestCase):
    def test_rim_paint_and_deep_shots_keep_their_zones(self):
        zones = _by_area(court_zones([
            _shot(x=6, y=50),
            _shot(x=17, y=50, success=False),
            _shot(x=48, y=50, success=False),
        ], "away"))
        self.assertEqual(zones[1]["fg"], "100.0%")
        self.assertEqual(zones[1]["count"], "1 / 1")
        self.assertEqual(zones[1]["fill"], HOT)
        self.assertEqual(zones[2]["fg"], "0.0%")
        self.assertEqual(zones[2]["count"], "0 / 1")
        self.assertEqual(zones[13]["count"], "0 / 1")
        self.assertEqual(zones[13]["fill"], COLD)

    def test_boundary_between_rim_and_paint_counts_for_the_rim(self):
        zones = _by_area(court_zones([_shot(x=4.52, y=50)], "away"))
        self.assertEqual(zones[1]["count"], "1 / 1")
        self.assertEqual(zones[2]["fg"], "-")

    def test_half_court_line_stays_and_the_other_half_is_dropped(self):
        events = [_shot(x=20, y=50) for _ in range(5)]
        events.append(_shot(x=50, y=50, success=False))
        events.append(_shot(x=80, y=50, success=True))
        zones = court_zones(events, "away")
        placed = sum(int(zone["count"].split(" / ")[1]) for zone in zones if zone["count"])
        self.assertEqual(placed, 6)
        self.assertEqual(_by_area(zones)[13]["count"], "0 / 1")

    def test_halftime_flip_folds_both_ends_onto_the_same_hoop(self):
        zones = _by_area(court_zones([
            _shot(x=94, y=50, periodId=1),
            _shot(x=6, y=50, periodId=3),
        ], "away"))
        self.assertEqual(zones[1]["count"], "2 / 2")
        self.assertEqual(zones[1]["fg"], "100.0%")

    def test_one_heave_does_not_flip_the_team_basket(self):
        events = [_shot(x=90, y=50, personId="other") for _ in range(8)]
        events.append(_shot(x=10, y=50, personId="heave", success=True))
        zones = court_zones(events, "away", player_id="heave")
        self.assertTrue(all(zone["fg"] == "-" for zone in zones))

    def test_right_basket_mirrors_the_sideline(self):
        left = _by_area(court_zones([_shot(x=6, y=10)], "away"))
        right = _by_area(court_zones([_shot(x=94, y=10)], "away"))
        left_area = next(area for area, zone in left.items() if zone["count"])
        right_area = next(area for area, zone in right.items() if zone["count"])
        self.assertNotEqual(left_area, right_area)

    def test_filters_ignore_free_throws_and_shots_without_coordinates(self):
        events = [
            _shot(),
            _shot(eventType="freeThrow"),
            _shot(eventType="3pt", x=None, y=None, success=False),
            _shot(periodId=3, x=6, y=50, success=False),
        ]
        first = _by_area(court_zones(events, "away", period="1"))
        self.assertEqual(first[1]["count"], "1 / 1")
        half = _by_area(court_zones(events, "away", period="h1"))
        self.assertEqual(half[1]["count"], "1 / 1")
        self.assertEqual(_by_area(court_zones(events, "home"))[1]["fg"], "-")

    def test_markup_puts_heat_under_the_lines_and_prints_the_label(self):
        zones = court_zones([
            _shot(),
            _shot(success=False),
            _shot(success=True),
        ], "away")
        uri = court_data_uri(zones)
        svg = base64.b64decode(uri.split(",", 1)[1]).decode("utf-8")
        self.assertLess(svg.find('id="shot-zones"'), svg.find('id="パス_18280"'))
        self.assertLess(svg.find('id="パス_18280"'), svg.find('id="shot-labels"'))
        self.assertIn("66.7", svg)
        self.assertIn(" %", svg)
        self.assertNotIn("66.7%", svg)
        self.assertIn("2 / 3", svg)
        self.assertIn('font-size="16"', svg)
        self.assertIn('font-size="12"', svg)
        self.assertIn('font-size="10"', svg)
        self.assertIn("translate(6 38) rotate(90)", svg)
        self.assertIn("translate(362 38) rotate(90)", svg)
        self.assertIn(HOT, svg)
        self.assertIn(">-</text>", svg)
        self.assertNotIn('stroke="#f8fafc"', svg)
        self.assertLess(svg.find('fill="#dc2626"'), svg.find('id="shot-rim-line"'))
        self.assertLess(svg.find('id="shot-rim-line"'), svg.find('id="パス_18280"'))
        self.assertIn('stroke="#ffffff"', svg)
        self.assertIn('stroke-width="0.5"', svg)
        self.assertNotIn('stroke-width="2"', svg)
        self.assertNotIn("No shots", svg)

    def test_corner_counts_use_the_second_rotated_anchor(self):
        zones = [
            {"area": area, "fg": "-", "count": "", "fill": None, "opacity": None}
            for area in range(1, 14)
        ]
        zones[11]["fg"] = "40.0%"
        zones[11]["count"] = "2 / 5"
        zones[7]["fg"] = "100.0%"
        zones[7]["count"] = "1 / 1"
        svg = court_markup(zones)
        self.assertIn("translate(6 38) rotate(90)", svg)
        self.assertIn("translate(6 88) rotate(90)", svg)
        self.assertIn("translate(362 38) rotate(90)", svg)
        self.assertIn("translate(362 93) rotate(90)", svg)
        self.assertIn("2 / 5", svg)
        self.assertIn("1 / 1", svg)

    def test_menu_opens_toward_the_side_that_fits_every_name(self):
        self.assertEqual(
            shot_menu_plan(100, 140, 800, 10, 32),
            {"side": "bottom", "height": 320, "inner": 320},
        )
        self.assertEqual(
            shot_menu_plan(700, 740, 800, 10, 32),
            {"side": "top", "height": 320, "inner": 320},
        )
        self.assertEqual(
            shot_menu_plan(500, 540, 700, 20, 32),
            {"side": "top", "height": 480, "inner": 480},
        )
        self.assertEqual(
            shot_menu_plan(10, 40, 80, 2, 32),
            {"side": "bottom", "height": 128, "inner": 128},
        )
        self.assertEqual(
            shot_menu_plan(100, 140, 800, 10, 32, 4, 4),
            {"side": "bottom", "height": 328, "inner": 320},
        )
        self.assertEqual(
            shot_menu_plan(500, 540, 700, 20, 32, 4, 4),
            {"side": "top", "height": 488, "inner": 480},
        )
        self.assertEqual(
            shot_menu_plan(10, 40, 80, 2, 32, 4, 4),
            {"side": "bottom", "height": 136, "inner": 128},
        )


if __name__ == "__main__":
    unittest.main()
