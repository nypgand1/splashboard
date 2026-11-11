# -*- coding: utf-8 -*-
"""13-zone half-court SVG rendering and data-URI builder."""
import base64
from pathlib import Path

from domain.shot_zones import ART, CLOSER_FIRST, _rows, court_zones

_COURT_PATH = Path(__file__).resolve().parents[2] / "assets" / "bg_shootchart_court.svg"

# B.League text anchors (group translate + local translate), except the two
# baseline corners: those anchors sit on the image edge, so the two-line label
# is centered in the sliver instead.
_LABELS = {
    1: (191, 59),
    2: (191, 106),
    3: (305, 39),
    4: (305, 114),
    5: (191, 185),
    6: (78, 114),
    7: (77, 39),
    8: (362, 40),
    9: (328, 227),
    10: (191, 263),
    11: (53, 227),
    12: (14, 40),
    13: (190, 362),
}

# Baseline corners are too narrow for a horizontal percent. B.League rotates
# them: left anchors (6, 38) and (6, 88); right anchors (362, 38) and (362, 93).
_CORNER_LABELS = {
    12: ((6, 38), (6, 88)),
    8: ((362, 38), (362, 93)),
}

_court_text_cache = None


def _percent_parts(fg):
    text = str(fg)
    if text.endswith("%"):
        return text[:-1], " %"
    return text, ""


def _xml(text):
    return str(text).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _zone_label(area, zone):
    digits, unit = _percent_parts(zone["fg"])
    count = zone.get("count") or ""
    corner = _CORNER_LABELS.get(area)
    if corner:
        (px, py), (cx, cy) = corner
        if not count:
            return (
                f'<text transform="translate({px} {py}) rotate(90)" '
                f'font-size="16">{_xml(digits)}</text>'
            )
        return (
            f'<text transform="translate({px} {py}) rotate(90)">'
            f'<tspan font-size="16">{_xml(digits)}</tspan>'
            f'<tspan font-size="12">{_xml(unit)}</tspan></text>'
            f'<text transform="translate({cx} {cy}) rotate(90)" font-size="10">{_xml(count)}</text>'
        )
    x, y = _LABELS[area]
    if not count:
        return f'<text x="{x}" y="{y}" font-size="16">{_xml(digits)}</text>'
    return (
        f'<text x="{x}" y="{y}">'
        f'<tspan dy="-7" font-size="16">{_xml(digits)}</tspan>'
        f'<tspan font-size="12">{_xml(unit)}</tspan>'
        f'<tspan x="{x}" dy="15" font-size="10">{_xml(count)}</tspan>'
        f"</text>"
    )


def _court_text():
    global _court_text_cache
    if _court_text_cache is None:
        _court_text_cache = _COURT_PATH.read_text(encoding="utf-8")
    return _court_text_cache


def court_markup(zones):
    """Court SVG with heat between the wood photo and the white lines."""
    by_area = {zone["area"]: zone for zone in zones}
    fills = []
    for area in reversed(CLOSER_FIRST):
        zone = by_area.get(area)
        if not zone or not zone.get("fill"):
            continue
        art = ART[area]
        opacity = f"{float(zone['opacity']):.2f}"
        color = zone["fill"]
        if art["rect"]:
            width, height = art["rect"]
            fills.append(
                f'<rect x="{art["tx"]}" y="{art["ty"]}" width="{width}" height="{height}" '
                f'fill="{color}" fill-opacity="{opacity}" stroke="none"/>'
            )
        else:
            fills.append(
                f'<path d="{art["d"]}" transform="translate({art["tx"]} {art["ty"]})" '
                f'fill="{color}" fill-opacity="{opacity}" fill-rule="evenodd" stroke="none"/>'
            )
    labels = []
    for area in range(1, 14):
        labels.append(_zone_label(area, by_area[area]))
    rim = ART[1]
    rim_line = (
        f'<path id="shot-rim-line" d="{rim["d"]}" transform="translate({rim["tx"]} {rim["ty"]})" '
        f'fill="none" stroke="#ffffff" stroke-width="0.5"/>'
    )
    raw = _court_text()
    marker = 'fill="url(#pattern)"/>'
    at = raw.find(marker)
    if at < 0:
        raise RuntimeError("court svg is missing the wood layer")
    at += len(marker)
    body = raw[:at] + '<g id="shot-zones">' + "".join(fills) + rim_line + "</g>" + raw[at:]
    label_group = (
        '<g id="shot-labels" fill="#0f172a" '
        'font-family="-apple-system, \'PingFang TC\', \'Noto Sans TC\', \'Segoe UI\', Roboto, sans-serif" '
        'font-weight="700" text-anchor="middle">'
        + "".join(labels)
        + "</g>"
    )
    return body.replace("</svg>", label_group + "</svg>", 1)


def court_data_uri(zones):
    encoded = base64.b64encode(court_markup(zones).encode("utf-8")).decode("ascii")
    return "data:image/svg+xml;base64," + encoded


def report_shot_chart_payload(events, away_team_id, home_team_id, away_name, home_name, fixture_id=None):
    """Full-game team charts for the Report block.

    An empty frame is ``empty``. Rows with no chartable shots stay ``ready``
    so both courts still draw, with a dash in every zone.
    """
    if events is None or (hasattr(events, "empty") and bool(events.empty)):
        return {"_ui": "empty"}
    if not _rows(events):
        return {"_ui": "empty"}
    away = away_name or "Away"
    home = home_name or "Home"
    return {
        "_ui": "ready",
        "away_name": away,
        "home_name": home,
        "away_src": court_data_uri(court_zones(
            events, away_team_id, period="all", player_id="all", fixture_id=fixture_id,
        )),
        "home_src": court_data_uri(court_zones(
            events, home_team_id, period="all", player_id="all", fixture_id=fixture_id,
        )),
    }
