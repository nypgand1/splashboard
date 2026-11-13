# Splashboard

Home schedule and game views for PLG and EASL fixtures.

## Language

**Team**:
A club that plays a fixture, identified by its competitor entity id. On the schedule its label is `nameFullLocal`.
_Avoid_: TBD, display string, home side, away side

**Center-line zone**:
The full-width band on the half-court diagram that lies on the midcourt line. A field goal is in this zone only when it lands inside that band. A field goal from the other half of the floor is not in this zone.
_Avoid_: heave

**TBD**:
The schedule label when a competitor id or its name is missing. It is not a Team.

**Results**:
The Home Show whose games are `FINISHED` or `CONFIRMED`. The stored value is `results`.
_Avoid_: Finished as the name of that Show
