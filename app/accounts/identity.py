"""Identify a caller by name together with an account number, service address or phone, never by name alone (R45)."""

import sqlite3
from dataclasses import dataclass

from app.accounts import normalise


@dataclass(frozen=True)
class Customer:
    customer_id: str
    name: str
    phone: str
    email: str | None
    service_address: str
    city: str
    zip: str


def identify(db: sqlite3.Connection, name: str, account: str | None = None, address: str | None = None,
             phone: str | None = None) -> Customer | None:
    if not any((account, address, phone)):
        return None
    wanted = normalise.name(name)
    rows = db.execute("select customer_id, name, phone, email, service_address, city, zip from customers").fetchall()
    for row in rows:
        customer = Customer(*row)
        if normalise.name(customer.name) != wanted:
            continue
        if account and normalise.account(account) == customer.customer_id:
            return customer
        if phone and normalise.phone(phone) == normalise.phone(customer.phone):
            return customer
        if address and normalise.street(address) == normalise.street(customer.service_address):
            return customer
    return None
