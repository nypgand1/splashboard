# Narrow Game tabs wrap, and the home run number keeps a clear line

Under 767px the Game tab list is a 3-column button grid. A single scrolling row hid the scrollbar, so the later tabs were easy to miss. Folder tabs broken across two rows leave the first row with an open bottom edge, so each narrow tab is a full-border button. The label stays 13px and one line; horizontal padding is 6px and the icon gap is 4px so `Play-By-Play` fits a 375px column. At 768px the list stays the current one-row scroller. Above that it stays the folder strip.

The Rotation tab uses the same 767px line. Wide labels stay `#` plus the short name, and the red row stays `3+ STOPS`. Narrow left ticks keep the on-court dot and the bench indent but drop the name, the left tag becomes `STOPS`, and `margin.l` is 56. Hover still carries the full label. Report is desktop-only and keeps the wide figure.

Home run numbers hang down from the margin chart into the same gap as the home team name. A 41px seam let those two meet. The lower seam is now 55px, one extra 14px line, on the tab and on Report. The run numbers stay put. The home name, the home stop counts, and the home Gantt move down with the bottom panel.
