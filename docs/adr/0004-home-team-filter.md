# Home filters one team, and the finished Show is Results

The Home schedule can narrow to one club after League, Season, Game Type, and Show. The club is a competitor entity id labeled `nameFullLocal`. The closed control is not a text field. `All Teams` leaves every game in the current Show and stage. The menu lists named teams from the loaded season and does not shrink when Show or Game Type changes. A missing id or a `TBD` name is not a choice.

Choosing a team, switching teams, or returning to `All Teams` keeps Show. Game Type stays when the current stage still has a candidate game in that Show. Otherwise it moves to the stage a Show click would pick for those candidates. Candidates are that team's games, or every game for `All Teams`. A Show click uses the same candidate set. A Game Type click, a 35-second reload, and entry selection do not run the jump. Entry selection and a league or season change return the choice to `All Teams`. A 35-second reload also returns to `All Teams` when the stored id is no longer a named team, and leaves Game Type where it is.

Keeping the stage when it still has games avoids pulling the list off a stage the reader picked. Jumping when it does not avoids an empty list that another stage of the same Show could fill. Remembering the stage from before the team choice would fight a later Game Type click.

The Show of `FINISHED` and `CONFIRMED` games is labeled `Results` and stored as `results`. Row badges stay the raw status. The bucket is unchanged.
