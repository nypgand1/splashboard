# -*- coding: utf-8 -*-
"""Zone shot chart from play-by-play x,y.

Court length is API x (0 left baseline, 100 right baseline). Court width is
API y (0 top sideline, 100 bottom). The offensive basket is the majority side
of that team's shots in that period. Right-basket shots mirror y so the
shooter's left stays on the image left. Zone outlines are the B.League
13-area overlay, drawn in the court SVG's coordinate space.
"""
import base64
from decimal import Decimal, ROUND_CEILING, ROUND_HALF_UP
from pathlib import Path

from synergy_reporter.rotation import period_label

HOT = "#dc2626"
MID = "#94a3b8"
COLD = "#0077b6"
COURT_W = 380.0
HALF_Y = 354.3
_COURT_PATH = Path(__file__).resolve().parents[1] / "assets" / "bg_shootchart_court.svg"
_CURVE_STEPS = 24
_EDGE_EPS = 1.0

# (area, tx, ty, path d or None, rect (w, h) or None). Paths are local to tx,ty.
_ZONE_ART = (
    (13, 0, 307, None, (380, 93)),
    (12, 0, 0, "M23.87,76.15h0c-.11-13.66-.51-63.42-.63-76.15H0V81.92l24.03-4.92c-.05-.28-.11-.56-.16-.85", None),
    (8, 344, 0, "M12.84,76.15h-.02c-.05,.31-.12,.61-.17,.91l23.81,4.88V0H12.84V76.15Z", None),
    (11, 0, 77, "M135.93,129.09L45.01,229.87H0V4.92L24.03,0c10.74,59.39,54.63,110.03,111.9,129.09", None),
    (9, 245, 77, "M134.59,4.88V229.81h-43.35L0,128.65C56.74,109.3,100.1,58.99,110.79,0l23.8,4.88Z", None),
    (10, 45, 206, "M145.27,9.34c-18.44,.02-36.77-3.01-54.24-8.96L0,101H292L200.63,0c-17.81,6.2-36.52,9.35-55.36,9.34", None),
    (7, 23, 0, "M.63,76.1c.05,.3,.12,.6,.17,.9l104.95-21.5V0H0C.11,12.47,.52,62.71,.63,76.1Z", None),
    (3, 251, 0, "M0,55.52l105.18,21.54c.56-1.15,0-75.87,.19-77.06H0V55.52Z", None),
    (6, 24, 56, "M104.95,0L0,21.5c8.69,46.58,36.54,87.37,76.75,112.44l28.21-45.44V0Z", None),
    (4, 251, 56, "M105.28,21.54L.1,0V88.48h-.1l28.3,45.59c40.32-25.04,68.25-65.87,76.98-112.53", None),
    (5, 101, 144, "M28.21,0L0,45.44c42.69,26.9,97,32.88,144.6,16.28,11.83-4.1,23.17-9.51,33.81-16.13L150.1,0H28.21Z", None),
    (2, 129, 0, "M0,0V144H121.99V0H0ZM21.39,32H100.6c2.81,56.2-82.01,56.22-79.21,0Z", None),
    (1, 150, 32, "M.07,0C-2.73,56.22,82.09,56.2,79.28,0H.07Z", None),
)
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
# Shared edges belong to the zone closer to the rim.
_CLOSER_FIRST = (1, 2, 7, 3, 6, 4, 5, 12, 8, 11, 9, 10, 13)

_court_text_cache = None


def _menu_px(value):
    """Smallest whole pixel that can hold this length."""
    return int(Decimal(str(value)).quantize(Decimal("1"), rounding=ROUND_CEILING))


def shot_menu_plan(top, bottom, viewport_height, row_count, row_height=32, pad_top=0, pad_bottom=0):
    """Which way the player menu opens, and how tall the panel is.

    Open toward the side that can hold every highlight box plus the dropdown
    padding. The space below wins when both sides can. When neither can, scroll
    and end on a complete highlight box. A short window still keeps four rows.
    """
    above = max(0.0, float(top) - 12)
    below = max(0.0, float(viewport_height) - float(bottom) - 12)
    rows = max(0, int(row_count))
    row = float(row_height)
    pad = _menu_px(pad_top) + _menu_px(pad_bottom)
    inner_all = _menu_px(rows * row) if rows else 0
    needed = inner_all + (pad if rows else 0)

    def scroll_inner(space):
        room = float(space) - pad
        fit = int(room // row) if row > 0 else 0
        count = fit if fit >= 4 else 4
        return _menu_px(count * row)

    if needed > 0 and below >= needed:
        side, inner = "bottom", inner_all
    elif needed > 0 and above >= needed:
        side, inner = "top", inner_all
    elif below >= above:
        side, inner = "bottom", scroll_inner(below)
    else:
        side, inner = "top", scroll_inner(above)
    return {"side": side, "height": inner + pad, "inner": inner}


def format_fg_percent(makes, attempts):
    """One decimal, half-up. Zero attempts is a dash."""
    if attempts is None or int(attempts) <= 0:
        return "-"
    ratio = (Decimal(int(makes)) / Decimal(int(attempts))) * Decimal(100)
    text = ratio.quantize(Decimal("0.1"), rounding=ROUND_HALF_UP)
    return f"{text}%"


def zone_appearance(twos_made, threes_made, attempts, court_attempts):
    """FG label, make/attempt line, eFG fill, and share opacity for one zone."""
    attempts_n = int(attempts or 0)
    if attempts_n <= 0:
        return {"fg": "-", "count": "", "fill": None, "opacity": None}
    twos_n = int(twos_made or 0)
    threes_n = int(threes_made or 0)
    numer = 2 * twos_n + 3 * threes_n
    if numer >= attempts_n:
        fill = HOT
    elif 5 * numer >= 4 * attempts_n:
        fill = MID
    else:
        fill = COLD
    court_n = int(court_attempts or 0)
    share = attempts_n / court_n if court_n else 0
    opacity = min(0.45, max(0.20, share / 0.25)) if court_n else None
    return {
        "fg": format_fg_percent(twos_n + threes_n, attempts_n),
        "count": f"{twos_n + threes_n} / {attempts_n}",
        "fill": fill,
        "opacity": opacity,
    }


def period_chips(period_ids):
    """Box Score chip order from play-by-play period ids."""
    ids = set()
    for value in period_ids or []:
        try:
            ids.add(int(value))
        except (TypeError, ValueError):
            continue
    chips = [{"label": "All", "value": "all"}]

    def add(period):
        if period in ids:
            chips.append({"label": period_label(period), "value": str(period)})

    add(1)
    add(2)
    if 1 in ids and 2 in ids:
        chips.append({"label": "1H", "value": "h1"})
    add(3)
    add(4)
    if 3 in ids and 4 in ids:
        chips.append({"label": "2H", "value": "h2"})
    for period in sorted(period for period in ids if period not in (1, 2, 3, 4)):
        chips.append({"label": period_label(period), "value": str(period)})
    return chips


def player_options(events, team_id):
    """All, then players with a full-game 2pt or 3pt attempt, jersey order."""
    found = {}
    for row in _shot_rows(events):
        if not _same_id(row["team"], team_id) or row["person"] is None:
            continue
        key = str(row["person"])
        slot = found.get(key)
        if slot is None:
            found[key] = {"id": key, "shirt": row["shirt"], "name": row["name"] or key}
            continue
        if slot["shirt"] in (None, "") and row["shirt"] not in (None, ""):
            slot["shirt"] = row["shirt"]
        if row["name"] and slot["name"] == key:
            slot["name"] = row["name"]
    people = sorted(found.values(), key=lambda person: (_shirt_sort(person["shirt"]), person["name"]))
    options = [{"value": "all", "label": "All"}]
    for person in people:
        shirt = person["shirt"]
        if shirt in (None, ""):
            label = str(person["name"])
        else:
            label = f"#{shirt} {person['name']}"
        options.append({"value": person["id"], "label": label})
    return options


def court_zones(events, team_id, period="all", player_id="all"):
    """Thirteen zones for one team after period and player filters.

    Basket side is voted from that team's shots in the period, before the
    player filter. Shots on the other half of the court are dropped.
    """
    rows = [row for row in _shot_rows(events) if _same_id(row["team"], team_id) and row["x"] is not None and row["y"] is not None]
    grouped = {}
    for row in rows:
        grouped.setdefault(row["period"], []).append(row)
    sides = {period_id: _offensive_side(group) for period_id, group in grouped.items()}
    totals = {area: {"two_m": 0, "three_m": 0, "attempts": 0} for area in range(1, 14)}
    placed = 0
    for row in rows:
        if not _period_ok(row["period"], period) or not _player_ok(row["person"], player_id):
            continue
        point = _fold(row["x"], row["y"], sides.get(row["period"], "right"))
        if point is None:
            continue
        area = _zone_at(*point)
        if area is None:
            continue
        bucket = totals[area]
        bucket["attempts"] += 1
        placed += 1
        if row["made"]:
            if row["kind"] == "3pt":
                bucket["three_m"] += 1
            else:
                bucket["two_m"] += 1
    zones = []
    for area in range(1, 14):
        bucket = totals[area]
        look = zone_appearance(bucket["two_m"], bucket["three_m"], bucket["attempts"], placed)
        look["area"] = area
        zones.append(look)
    return zones


# Baseline corners are too narrow for a horizontal percent. B.League rotates
# them: left anchors (6, 38) and (6, 88); right anchors (362, 38) and (362, 93).
_CORNER_LABELS = {
    12: ((6, 38), (6, 88)),
    8: ((362, 38), (362, 93)),
}


def _percent_parts(fg):
    text = str(fg)
    if text.endswith("%"):
        return text[:-1], " %"
    return text, ""


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


def court_markup(zones):
    """Court SVG with heat between the wood photo and the white lines."""
    by_area = {zone["area"]: zone for zone in zones}
    fills = []
    for area in reversed(_CLOSER_FIRST):
        zone = by_area.get(area)
        if not zone or not zone.get("fill"):
            continue
        art = _ART[area]
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
    rim = _ART[1]
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
        'font-family="-apple-system, PingFang TC, Noto Sans TC, Segoe UI, sans-serif" '
        'font-weight="700" text-anchor="middle">'
        + "".join(labels)
        + "</g>"
    )
    return body.replace("</svg>", label_group + "</svg>", 1)


def court_data_uri(zones):
    encoded = base64.b64encode(court_markup(zones).encode("utf-8")).decode("ascii")
    return "data:image/svg+xml;base64," + encoded


def _court_text():
    global _court_text_cache
    if _court_text_cache is None:
        _court_text_cache = _COURT_PATH.read_text(encoding="utf-8")
    return _court_text_cache


def _xml(text):
    return str(text).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _shirt_sort(shirt):
    if shirt in (None, ""):
        return (1, 10 ** 9, "")
    text = str(shirt).strip()
    try:
        return (0, int(text), text)
    except ValueError:
        return (0, 10 ** 9, text)


def _same_id(left, right):
    if left is None or right is None:
        return False
    return str(left) == str(right)


def _num(value):
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, str) and not value.strip():
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if number != number:
        return None
    return number


def _is_make(value):
    if isinstance(value, str):
        return value.strip().lower() in ("true", "1")
    return value is True or value == 1


def _rows(events):
    if events is None:
        return []
    if hasattr(events, "to_dict"):
        return events.to_dict("records")
    return list(events)


def _shot_rows(events):
    rows = []
    for item in _rows(events):
        kind = str(item.get("eventType") or "").strip().lower()
        if kind not in ("2pt", "3pt"):
            continue
        period = _num(item.get("periodId"))
        if period is None:
            continue
        person = item.get("personId")
        if person is None or (isinstance(person, float) and person != person):
            person = None
        elif person is not None:
            person = str(person)
        name = item.get("Player")
        if name is None or (isinstance(name, float) and name != name):
            name = item.get("player")
        if isinstance(name, float) and name != name:
            name = None
        shirt = item.get("shirtNumber")
        if shirt is None or (isinstance(shirt, float) and shirt != shirt) or shirt == "":
            shirt = None
        else:
            shirt = str(shirt).strip()
            if shirt.endswith(".0") and shirt[:-2].isdigit():
                shirt = shirt[:-2]
        rows.append({
            "team": None if item.get("entityId") is None or (isinstance(item.get("entityId"), float) and item.get("entityId") != item.get("entityId")) else str(item.get("entityId")),
            "person": person,
            "name": None if name is None else str(name),
            "shirt": shirt,
            "period": int(period),
            "kind": kind,
            "made": _is_make(item.get("success")),
            "x": _num(item.get("x")),
            "y": _num(item.get("y")),
        })
    return rows


def _period_ok(period_id, selected):
    token = "all" if selected in (None, "", "all") else str(selected)
    if token == "all":
        return True
    if token == "h1":
        return period_id in (1, 2)
    if token == "h2":
        return period_id in (3, 4)
    try:
        return period_id == int(token)
    except ValueError:
        return False


def _player_ok(person, selected):
    if selected in (None, "", "all"):
        return True
    return str(person) == str(selected)


def _offensive_side(rows):
    rights = sum(1 for row in rows if row["x"] is not None and row["x"] >= 50)
    lefts = sum(1 for row in rows if row["x"] is not None and row["x"] < 50)
    return "right" if rights >= lefts else "left"


def _fold(x, y, side):
    if side == "right":
        if x < 50:
            return None
        distance = 100 - x
        y_norm = 100 - y
    else:
        if x > 50:
            return None
        distance = x
        y_norm = y
    if distance > 50:
        return None
    return (y_norm / 100.0) * COURT_W, (distance / 50.0) * HALF_Y


def _read_number(text, index):
    size = len(text)
    while index < size and text[index] in " ,\t\r\n":
        index += 1
    if index >= size:
        raise ValueError("svg path ended early")
    start = index
    if text[index] in "+-":
        index += 1
    if index >= size or (not text[index].isdigit() and text[index] != "."):
        raise ValueError("svg path expected a number")
    seen_dot = False
    while index < size and (text[index].isdigit() or (text[index] == "." and not seen_dot)):
        if text[index] == ".":
            seen_dot = True
        index += 1
    return float(text[start:index]), index


def _cubic(p0, p1, p2, p3):
    points = []
    for step in range(1, _CURVE_STEPS + 1):
        t = step / _CURVE_STEPS
        u = 1 - t
        points.append((
            (u ** 3) * p0[0] + 3 * (u ** 2) * t * p1[0] + 3 * u * (t ** 2) * p2[0] + (t ** 3) * p3[0],
            (u ** 3) * p0[1] + 3 * (u ** 2) * t * p1[1] + 3 * u * (t ** 2) * p2[1] + (t ** 3) * p3[1],
        ))
    return points


def _rings(d, tx, ty):
    rings = []
    ring = []
    cx = cy = 0.0
    sx = sy = 0.0
    index = 0
    size = len(d)
    cmd = None

    def end_ring():
        nonlocal ring
        if len(ring) >= 3:
            if ring[0] != ring[-1]:
                ring.append(ring[0])
            rings.append(ring)
        ring = []

    def add(x, y):
        ring.append((x + tx, y + ty))

    while index < size:
        char = d[index]
        if char.isalpha():
            cmd = char
            index += 1
            if cmd in "Zz":
                end_ring()
                cx, cy = sx, sy
            continue
        if char in " ,\t\r\n":
            index += 1
            continue
        if cmd in "Mm":
            x, index = _read_number(d, index)
            y, index = _read_number(d, index)
            nx, ny = (x, y) if cmd == "M" else (cx + x, cy + y)
            end_ring()
            add(nx, ny)
            cx, cy = nx, ny
            sx, sy = nx, ny
            cmd = "L" if cmd == "M" else "l"
            continue
        if cmd in "Ll":
            x, index = _read_number(d, index)
            y, index = _read_number(d, index)
            nx, ny = (x, y) if cmd == "L" else (cx + x, cy + y)
            add(nx, ny)
            cx, cy = nx, ny
            continue
        if cmd in "Hh":
            x, index = _read_number(d, index)
            nx = x if cmd == "H" else cx + x
            add(nx, cy)
            cx = nx
            continue
        if cmd in "Vv":
            y, index = _read_number(d, index)
            ny = y if cmd == "V" else cy + y
            add(cx, ny)
            cy = ny
            continue
        if cmd in "Cc":
            nums = []
            for _ in range(6):
                number, index = _read_number(d, index)
                nums.append(number)
            if cmd == "C":
                p1 = (nums[0], nums[1])
                p2 = (nums[2], nums[3])
                p3 = (nums[4], nums[5])
            else:
                p1 = (cx + nums[0], cy + nums[1])
                p2 = (cx + nums[2], cy + nums[3])
                p3 = (cx + nums[4], cy + nums[5])
            for point in _cubic((cx, cy), p1, p2, p3):
                add(point[0], point[1])
            cx, cy = p3
            continue
        raise ValueError(f"unsupported svg path command {cmd}")
    end_ring()
    return rings


def _seg_dist(px, py, ax, ay, bx, by):
    dx = bx - ax
    dy = by - ay
    length = dx * dx + dy * dy
    if length == 0:
        return ((px - ax) ** 2 + (py - ay) ** 2) ** 0.5
    t = max(0.0, min(1.0, ((px - ax) * dx + (py - ay) * dy) / length))
    qx = ax + t * dx
    qy = ay + t * dy
    return ((px - qx) ** 2 + (py - qy) ** 2) ** 0.5


def _ring_hit(rings, x, y):
    for ring in rings:
        for (x1, y1), (x2, y2) in zip(ring, ring[1:]):
            if _seg_dist(x, y, x1, y1, x2, y2) <= _EDGE_EPS:
                return True
    crossings = 0
    for ring in rings:
        for (x1, y1), (x2, y2) in zip(ring, ring[1:]):
            if (y1 > y) != (y2 > y):
                xint = x1 + (y - y1) * (x2 - x1) / (y2 - y1)
                if xint > x:
                    crossings += 1
    return crossings % 2 == 1


def _rect_hit(tx, ty, width, height, x, y):
    return (tx - _EDGE_EPS) <= x <= (tx + width + _EDGE_EPS) and (ty - _EDGE_EPS) <= y <= (ty + height + _EDGE_EPS)


def _build_art():
    art = {}
    hits = {}
    for area, tx, ty, d, rect in _ZONE_ART:
        art[area] = {"tx": tx, "ty": ty, "d": d, "rect": rect}
        if rect:
            width, height = rect
            hits[area] = lambda x, y, tx=tx, ty=ty, width=width, height=height: _rect_hit(tx, ty, width, height, x, y)
        else:
            rings = _rings(d, tx, ty)
            hits[area] = lambda x, y, rings=rings: _ring_hit(rings, x, y)
    return art, hits


_ART, _HITS = _build_art()


def _zone_at(x, y):
    for area in _CLOSER_FIRST:
        if _HITS[area](x, y):
            return area
    return None
