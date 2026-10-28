# -*- coding: utf-8 -*-
"""Column-best marks for the numbers a table actually shows.

A blank cell stays out of the comparison. Fewer than two numbers, or every
participating number equal, marks nothing. Otherwise every cell that holds
the best participating number is marked.
"""


def winning_indexes(values, lower=False):
    present = []
    for index, value in enumerate(values):
        if value is None:
            continue
        present.append((index, value))
    if len(present) < 2:
        return []
    first = present[0][1]
    if all(value == first for _index, value in present):
        return []
    best = first
    for _index, value in present[1:]:
        if (value < best) if lower else (value > best):
            best = value
    return [index for index, value in present if value == best]
