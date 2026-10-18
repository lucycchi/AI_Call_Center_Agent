"""Fixed safety replies written in code, never by the model (R35 to R37). The wording paraphrases the internal
safety protocol rather than quoting it (R43)."""

from app.safety import patterns as p

TICKET = "I'm opening a priority ticket now so our team gets back to you right away."

REPLIES = {
    "danger": ["This could be dangerous, so please leave your home right now, with everyone inside.",
               "Once you're out, call 911 or your gas utility from outside the house.",
               "Don't flip switches, don't open windows near the furnace, and don't restart equipment on the way out.",
               TICKET],
    "burning": ["Please turn the system off at the thermostat now.",
                "Please don't reset breakers.",
                "Leave the home if there is smoke, and call 911 once you're outside.",
                "This needs a technician to look at it first, so I won't book it as a regular visit. " + TICKET],
}
URGENT = {
    "leak": ["Let's limit the damage: please turn off the water supply to the leak, or the main shutoff if you can't find it.",
             "Stay clear of any water near outlets or electrical equipment.", TICKET],
    "heat": ["I'm sorry you're without heat in this cold.",
             "Layers, blankets and closing off unused rooms will help hold the heat in; please don't use an oven or grill to warm the home.",
             TICKET],
    "cool": ["I'm sorry you're without cooling in this heat.",
             "Drink water, keep blinds closed, and if anyone at home is vulnerable to heat, go somewhere cooler for now.",
             TICKET],
}


def fixed_reply(kind: str, situation: str = "") -> list[str]:
    if kind != "urgent":
        return list(REPLIES[kind])
    said = p.normalise(situation)
    if p.found(p.LEAK, said):
        return list(URGENT["leak"])
    if p.found(p.NO_HEAT, said):
        return list(URGENT["heat"])
    if p.found(p.NO_COOLING, said):
        return list(URGENT["cool"])
    return list(URGENT["leak"])
