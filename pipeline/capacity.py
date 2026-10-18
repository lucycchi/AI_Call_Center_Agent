"""Appointment capacity by zone and service, and seeded appointments outside the customer's zone."""

import sqlite3

from app.scheduling.zones import zone_for

SERVICES = ("hvac_repair", "hvac_tune_up", "plumbing", "estimate")
SHORT = {"hvac_repair": "hvac repair", "hvac_tune_up": "tune-up", "plumbing": "plumbing", "estimate": "estimate"}


def capacity_by_zone(db: sqlite3.Connection) -> dict:
    result = {zone: {SHORT[s]: 0 for s in SERVICES} | {"customers": 0, "bookable": 0}
              for zone in ("north", "central", "south")}
    for zone, service, count in db.execute(
            "select zone, service_type, count(*) from appointment_slots "
            "where status in ('open','reserved_members') group by 1, 2"):
        result[zone][SHORT[service]] = count
        result[zone]["bookable"] += count
    for (city,) in db.execute("select city from customers"):
        zone = zone_for(city)
        if zone:
            result[zone]["customers"] += 1
    return result


def zone_mismatches(db: sqlite3.Connection) -> list[dict]:
    rows = db.execute(
        "select a.appointment_id, c.customer_id, c.city, s.zone from appointments a "
        "join appointment_slots s using (slot_id) join customers c using (customer_id) "
        "where a.status = 'scheduled'")
    return [{"appointment_id": a, "customer_id": c, "city": city, "customer_zone": zone_for(city), "slot_zone": zone}
            for a, c, city, zone in rows if zone_for(city) != zone]
