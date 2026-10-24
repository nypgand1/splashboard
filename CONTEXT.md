# Splashboard

Home schedule and game views for PLG and EASL fixtures.

## Language

**Team**:
A club that plays a fixture, identified by its competitor entity id. On the schedule its label is `nameFullLocal`.
_Avoid_: TBD, display string, home side, away side

**TBD**:
The schedule label when a competitor id or its name is missing. It is not a Team.

**Results**:
The Home Show whose games are `FINISHED` or `CONFIRMED`. The stored value is `results`.
_Avoid_: Finished as the name of that Show
