import unittest

from synergy_reporter.csv_table import (
    CSV_ERR_BYTES,
    CSV_ERR_COLUMNS,
    CSV_ERR_EMPTY,
    CSV_ERR_HEADER,
    CSV_ERR_READ,
    CSV_ERR_ROWS,
    CSV_ERR_UTF8,
    CSV_MAX_BYTES,
    CSV_PPP_BLUE,
    CSV_PPP_RED,
    CsvTableError,
    csv_block_title,
    load_csv_table,
    parse_csv_table,
    ppp_cell_style,
)


def _style(text):
    return ppp_cell_style(text)


class CsvParseTests(unittest.TestCase):
    def test_header_and_rows_keep_original_text(self):
        parsed = parse_csv_table('Play Type,PPP\nIso,1.00\n')
        self.assertEqual(parsed['columns'], ['Play Type', 'PPP'])
        self.assertEqual(parsed['rows'], [['Iso', '1.00']])

    def test_quotes_commas_and_newlines(self):
        parsed = parse_csv_table('Name,Note\n"Lin, Wei","line1\nline2"\n')
        self.assertEqual(parsed['rows'], [['Lin, Wei', 'line1\nline2']])

    def test_header_only(self):
        parsed = parse_csv_table('PPP\n')
        self.assertEqual(parsed['columns'], ['PPP'])
        self.assertEqual(parsed['rows'], [])

    def test_short_rows_pad_and_long_rows_truncate(self):
        parsed = parse_csv_table('A,B,C\n1\n9,8,7,6\n')
        self.assertEqual(parsed['rows'], [['1', '', ''], ['9', '8', '7']])

    def test_blank_line_is_a_body_row(self):
        parsed = parse_csv_table('A,B\n\n1,2\n')
        self.assertEqual(parsed['rows'][0], ['', ''])

    def test_empty_whitespace_and_missing_header(self):
        for text in ('', '   \n', '\n'):
            with self.assertRaises(CsvTableError) as raised:
                parse_csv_table(text)
            self.assertEqual(raised.exception.message, CSV_ERR_EMPTY)
        with self.assertRaises(CsvTableError) as raised:
            parse_csv_table(',,\n')
        self.assertEqual(raised.exception.message, CSV_ERR_HEADER)

    def test_unclosed_quote(self):
        with self.assertRaises(CsvTableError) as raised:
            parse_csv_table('"open,1\n')
        self.assertEqual(raised.exception.message, CSV_ERR_READ)

    def test_column_and_row_limits(self):
        wide = ','.join('c%d' % i for i in range(24)) + '\n'
        self.assertEqual(len(parse_csv_table(wide)['columns']), 24)
        too_wide = ','.join('c%d' % i for i in range(25)) + '\n'
        with self.assertRaises(CsvTableError) as raised:
            parse_csv_table(too_wide)
        self.assertEqual(raised.exception.message, CSV_ERR_COLUMNS)
        body = ''.join('r\n' for _ in range(40))
        self.assertEqual(len(parse_csv_table('H\n' + body)['rows']), 40)
        with self.assertRaises(CsvTableError) as raised:
            parse_csv_table('H\n' + body + 'x\n')
        self.assertEqual(raised.exception.message, CSV_ERR_ROWS)


class CsvLoadTests(unittest.TestCase):
    def test_utf8_bom_and_title(self):
        block = load_csv_table('\ufeffPPP\n1.00\n'.encode('utf-8'), 'My.Table.CSV', 'plain')
        self.assertEqual(block['title'], 'My.Table')
        self.assertEqual(block['coloring'], 'plain')
        self.assertEqual(block['rows'], [['1.00']])

    def test_titles(self):
        self.assertEqual(csv_block_title('bench.csv'), 'bench')
        self.assertEqual(csv_block_title('.csv'), 'Imported table')
        self.assertEqual(csv_block_title(''), 'Imported table')
        self.assertEqual(csv_block_title('dir/play type.csv'), 'play type')

    def test_byte_limits_and_encoding(self):
        payload = b'A\n1\n'
        self.assertEqual(load_csv_table(payload, 'a.csv')['columns'], ['A'])
        with self.assertRaises(CsvTableError) as raised:
            load_csv_table(b'', 'a.csv')
        self.assertEqual(raised.exception.message, CSV_ERR_EMPTY)
        with self.assertRaises(CsvTableError) as raised:
            load_csv_table(b'A\n' + (b'x' * CSV_MAX_BYTES), 'a.csv')
        self.assertEqual(raised.exception.message, CSV_ERR_BYTES)
        exact = b'H\n' + (b'1\n' * 10)
        exact = exact + (b' ' * (CSV_MAX_BYTES - len(exact)))
        self.assertEqual(len(exact), CSV_MAX_BYTES)
        load_csv_table(exact, 'fit.csv')
        with self.assertRaises(CsvTableError) as raised:
            load_csv_table(b'\xff\xfeH\n', 'bad.csv')
        self.assertEqual(raised.exception.message, CSV_ERR_UTF8)

    def test_coloring_flag(self):
        block = load_csv_table(b'PPP\n1.25\n', 'plays.csv', 'ppp')
        self.assertEqual(block['type'], 'csv_table')
        self.assertEqual(block['coloring'], 'ppp')
        self.assertEqual(load_csv_table(b'PPP\n1\n', 'a.csv', 'other')['coloring'], 'plain')


class PppStyleTests(unittest.TestCase):
    def test_thresholds_keep_two_decimal_and_other_numbers(self):
        blue = {'color': CSV_PPP_BLUE, 'fontWeight': '700'}
        red = {'color': CSV_PPP_RED, 'fontWeight': '700'}
        for text in ('1', '1.0', '1.00', '1.000', '+1.10', ' 1.25 '):
            self.assertEqual(_style(text), blue, text)
        for text in ('0.79', '.50', '0', '-0.10', '0.799'):
            self.assertEqual(_style(text), red, text)
        for text in ('0.80', '.80', '0.99', '0.800'):
            self.assertIsNone(_style(text), text)

    def test_non_numbers_stay_plain(self):
        for text in ('', ' ', '100%', '1,25', '1e2', '１．００', '1.', 'PPP', None):
            self.assertIsNone(_style(text), text)
