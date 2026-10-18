# Home schedule segments follow the season only when the scope changes

Home's Show and Game Type are one stored pair. Opening the page, reloading, or changing league or season recomputes that pair from the new schedule and filters the list to it. A 30-second reload refreshes rows inside the pair the user is already looking at.

The pair prefers a live game, then the earliest game that will be played, then the latest finished game, and leaves `IF_NEEDED` for last. Changing Show keeps the current stage when that stage still has rows. Changing Game Type never changes Show. Carrying Finished into a new season hid that season's games, and a reload that chased the "current" stage pulled the list out from under someone who had already chosen a view.
