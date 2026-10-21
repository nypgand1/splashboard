# -*- coding: utf-8 -*-
"""Client-side Report CSV import rules. No Dash and no disk I/O.

The browser copy lives in assets/report_canvas.js and must accept the same
text, limits, titles, and PPP colors.
"""

import csv
import io
import re

CSV_MAX_BYTES = 64 * 1024
CSV_MAX_COLUMNS = 24
CSV_MAX_BODY_ROWS = 40
CSV_BLOCK_TYPE = 'csv_table'
CSV_TITLE_FALLBACK = 'Imported table'
CSV_OFFENSE_TITLE = 'Offense | Play-type Stats'
CSV_DEFENSE_TITLE = 'Defense | Play-type Stats'
CSV_IMPORT_LABEL = 'Import from CSV File'
CSV_PLAY_TYPE_LABEL = 'Import from Play-type CSV File'
CSV_ERR_EMPTY = 'This CSV is empty.'
CSV_ERR_UTF8 = 'This CSV is not UTF-8.'
CSV_ERR_HEADER = 'This CSV needs a header row.'
CSV_ERR_READ = 'This CSV could not be read.'
CSV_ERR_BYTES = 'This CSV is larger than 64KB.'
CSV_ERR_COLUMNS = 'This CSV has more than 24 columns.'
CSV_ERR_ROWS = 'This CSV has more than 40 rows.'
CSV_PPP_HEADER = 'PPP'
CSV_PPP_BLUE = '#0077b6'
CSV_PPP_RED = '#e63946'
CSV_PPP_BLUE_MIN = 1
CSV_PPP_RED_BELOW = 0.8

_PPP_NUMBER = re.compile(r'^[+-]?(?:[0-9]+(?:\.[0-9]+)?|\.[0-9]+)$')


class CsvTableError(ValueError):
    def __init__(self, message):
        super().__init__(message)
        self.message = message


def csv_block_title(filename, coloring='plain'):
    name = str(filename or '').replace('\\', '/').split('/')[-1]
    lower = name.lower()
    if coloring == 'ppp':
        if lower.endswith('_off.csv'):
            return CSV_OFFENSE_TITLE
        if lower.endswith('_def.csv'):
            return CSV_DEFENSE_TITLE
    if lower.endswith('.csv'):
        name = name[:-4]
    if not name.strip():
        return CSV_TITLE_FALLBACK
    return name


def ppp_cell_style(text):
    token = '' if text is None else str(text).strip()
    if not _PPP_NUMBER.fullmatch(token):
        return None
    whole, _dot, frac = token.lstrip('+-').partition('.')
    scale = len(frac)
    magnitude = int((whole or '0') + frac)
    if token[0] == '-':
        magnitude = -magnitude
    if magnitude >= 10 ** scale:
        return {'color': CSV_PPP_BLUE, 'fontWeight': '700'}
    if magnitude * 10 < 8 * (10 ** scale):
        return {'color': CSV_PPP_RED, 'fontWeight': '700'}
    return None


def _records(text):
    try:
        rows = list(csv.reader(io.StringIO(text, newline=''), strict=True))
    except csv.Error as err:
        raise CsvTableError(CSV_ERR_READ) from err
    return rows


def parse_csv_table(text):
    if text is None or not str(text).strip():
        raise CsvTableError(CSV_ERR_EMPTY)
    records = _records(str(text))
    if not records:
        raise CsvTableError(CSV_ERR_EMPTY)
    columns = ['' if cell is None else str(cell) for cell in records[0]]
    if not any(cell.strip() for cell in columns):
        raise CsvTableError(CSV_ERR_HEADER)
    if len(columns) > CSV_MAX_COLUMNS:
        raise CsvTableError(CSV_ERR_COLUMNS)
    body = records[1:]
    if len(body) > CSV_MAX_BODY_ROWS:
        raise CsvTableError(CSV_ERR_ROWS)
    width = len(columns)
    rows = []
    for record in body:
        cells = ['' if cell is None else str(cell) for cell in record]
        if len(cells) < width:
            cells.extend([''] * (width - len(cells)))
        elif len(cells) > width:
            cells = cells[:width]
        rows.append(cells)
    return {'columns': columns, 'rows': rows}


def load_csv_table(data, filename, coloring='plain'):
    if isinstance(data, str):
        raise CsvTableError(CSV_ERR_READ)
    try:
        size = len(data)
    except TypeError as err:
        raise CsvTableError(CSV_ERR_READ) from err
    if size > CSV_MAX_BYTES:
        raise CsvTableError(CSV_ERR_BYTES)
    if size <= 0:
        raise CsvTableError(CSV_ERR_EMPTY)
    try:
        text = bytes(data).decode('utf-8-sig')
    except UnicodeDecodeError as err:
        raise CsvTableError(CSV_ERR_UTF8) from err
    parsed = parse_csv_table(text)
    mode = 'ppp' if coloring == 'ppp' else 'plain'
    return {
        'type': CSV_BLOCK_TYPE,
        'title': csv_block_title(filename, mode),
        'coloring': mode,
        'columns': parsed['columns'],
        'rows': parsed['rows'],
    }
