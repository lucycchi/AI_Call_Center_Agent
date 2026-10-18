from pathlib import Path

from pipeline.templates import group_templates, normalise
from pipeline.transcripts import Call, load_transcripts

DATA = Path(__file__).resolve().parents[2] / "call_data"


def make_call(call_id, customer, agent):
    return Call(call_id=call_id, timestamp="2026-07-01T10:00", staff="Tasha", seconds=60,
                customer_lines=customer, agent_lines=agent)


def test_normalise_strips_filler_numbers_and_punctuation():
    assert normalise("Um, my window was 12 to 4 and it's 4:30.") == "my window was # to # and it s #:#"


def test_loads_all_420_transcripts_and_ignores_windows_leftovers():
    calls = load_transcripts(DATA / "call_transcripts", DATA / "call_transcripts_index.csv")
    assert len(calls) == 420
    assert all(not c.call_id.endswith("Identifier") for c in calls)
    first = next(c for c in calls if c.call_id == "CALL-20260902-0001")
    assert first.staff == "Tasha"
    assert first.seconds == 82
    assert first.customer_lines[0] == "I have a tech coming tomorrow but something came up. Can I move it?"


def test_same_request_and_same_staff_outcome_share_a_template(tmp_path):
    a = make_call("A", ["I have a tech coming tomorrow but something came up. Can I move it?", "Yeah, it's MHC-23434."],
                  ["Moved. New confirmation text is on its way."])
    b = make_call("B", ["Um, I have a tech coming tomorrow but something came up. Can I move it?", "it's MHC-59930"],
                  ["Moved. New confirmation text is on its way."])
    groups = group_templates([a, b], tmp_path / "merges.csv")
    assert groups["A"] == groups["B"]


def test_same_request_but_different_staff_outcome_are_different_templates(tmp_path):
    a = make_call("A", ["I need to schedule a service call. My AC isn't cooling."],
                  ["You're booked. The diagnostic fee is $89 and that gets applied toward the repair."])
    b = make_call("B", ["I need to schedule a service call. My AC isn't cooling."],
                  ["Unfortunately that's the earliest I have for a non-emergency. I can add you to the waitlist for cancellations."])
    groups = group_templates([a, b], tmp_path / "merges.csv")
    assert groups["A"] != groups["B"]


def test_filler_openings_are_skipped_when_finding_the_request(tmp_path):
    a = make_call("A", ["Sorry, you cut out for a second.", "What's my current balance?"], ["You have an open balance of $245."])
    b = make_call("B", ["What's my current balance?"], ["You have an open balance of $312."])
    groups = group_templates([a, b], tmp_path / "merges.csv")
    assert groups["A"] == groups["B"]


def test_merge_list_joins_two_templates(tmp_path):
    a = make_call("A", ["How much is the maintenance plan?"], ["It's $189 a year for one system."])
    b = make_call("B", ["What does the Comfort Club membership actually include?"], ["It's $189 a year for one system."])
    first = group_templates([a, b], tmp_path / "none.csv")
    assert first["A"] != first["B"]
    merges = tmp_path / "merges.csv"
    merges.write_text(f"from_template,to_template\n{first['B']},{first['A']}\n")
    merged = group_templates([a, b], merges)
    assert merged["A"] == merged["B"]


def test_header_line_with_the_staff_name_is_not_read_as_something_staff_said():
    calls = load_transcripts(DATA / "call_transcripts", DATA / "call_transcripts_index.csv")
    first = next(c for c in calls if c.call_id == "CALL-20260902-0001")
    assert first.agent_lines[0].startswith("Meridian Home Comfort, Tasha speaking")
    assert all(line != "Tasha" for c in calls for line in c.agent_lines)


def test_a_callers_name_inside_the_request_does_not_split_a_template(tmp_path):
    a = make_call("A", ["Hi, this is Linda Foster, what's my current balance?"], ["You have an open balance of $245."])
    b = make_call("B", ["Hi, this is Omar Patel, what's my current balance?"], ["You have an open balance of $312."])
    groups = group_templates([a, b], tmp_path / "merges.csv")
    assert groups["A"] == groups["B"]


def test_a_waitlist_template_belongs_to_its_booking_twins_family(tmp_path):
    from pipeline.templates import families

    booked = make_call("A", ["My kitchen sink is backing up."], ["You're booked. The diagnostic fee is $89."])
    waitlist = make_call("B", ["My kitchen sink is backing up.", "Can you do anything earlier?"],
                         ["Unfortunately that's the earliest I have for a non-emergency. I can add you to the waitlist for cancellations.",
                          "You're booked. The diagnostic fee is $89."])
    other = make_call("C", ["What's my current balance?"], ["You have an open balance of $245."])
    calls = [booked, waitlist, other]
    groups = group_templates(calls, tmp_path / "merges.csv")
    family = families(calls, groups)
    assert groups["A"] != groups["B"]
    assert family[groups["B"]] == groups["A"]
    assert family[groups["A"]] == groups["A"]
    assert family[groups["C"]] == groups["C"]
