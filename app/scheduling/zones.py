"""City to zone, from the scheduling schema. Dripping Springs and Manor are served but have no zone."""

ZONES = {
    "round rock": "north", "cedar park": "north", "pflugerville": "north", "georgetown": "north",
    "leander": "north", "hutto": "north", "austin": "central", "kyle": "south", "buda": "south",
}
SERVED_WITHOUT_ZONE = {"dripping springs", "manor"}


def zone_for(city: str) -> str | None:
    return ZONES.get(city.strip().lower())
