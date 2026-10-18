import csv
from pathlib import Path

from pipeline.convert import convert_pdf_table, convert_price_book
from pipeline.documents import internal_documents, searchable_documents

ROOT = Path(__file__).resolve().parents[2]
KB = ROOT / "call_data" / "knowledge_base"


def rel(paths):
    return {str(p.relative_to(KB)) for p in paths}


def test_searchable_documents_exclude_stale_placeholder_and_internal_files():
    searchable = rel(searchable_documents())
    for excluded in ["archive/comfort_club_overview.md", "archive/warranty_terms_2023.txt", "faq/faq_old_copy.md",
                     "services/scheduling_guide.md", "services/duct_cleaning.md", "internal/agent_discretion_notes.md",
                     "policies/escalation_and_safety.md", "services/technician_arrival_and_etas.md"]:
        assert excluded not in searchable
    assert "faq/customer_faq.md" in searchable
    assert "pricing/2026_fee_schedule.pdf" in searchable


def test_internal_documents_are_the_three_agent_facing_files():
    assert rel(internal_documents()) == {"internal/agent_discretion_notes.md", "policies/escalation_and_safety.md",
                                         "services/technician_arrival_and_etas.md"}


def test_document_list_covers_every_file_exactly_once():
    listed = [row["path"] for row in csv.DictReader((ROOT / "data" / "document_list.csv").open())]
    on_disk = sorted(str(p.relative_to(KB)) for p in KB.rglob("*") if p.is_file() and "Zone.Identifier" not in p.name)
    assert sorted(listed) == on_disk
    rows = list(csv.DictReader((ROOT / "data" / "document_list.csv").open()))
    assert {r["status"] for r in rows} <= {"current", "stale", "placeholder"}
    assert {r["audience"] for r in rows} <= {"customers", "internal"}
    assert all(r["reason"] for r in rows)


def test_pdf_fee_table_keeps_row_and_column_pairs():
    text = convert_pdf_table(KB / "pricing" / "2026_fee_schedule.pdf")
    assert "Diagnostic visit, Comfort Club: Waived" in text
    assert "Membership (annual, 1 system), Comfort Club Plus: $269" in text
    assert "Late cancellation (<24h), Non-member: $49" in text
    assert "Monthly membership requires a 12-month minimum." in text


def test_price_book_is_one_readable_line_per_item():
    text = convert_price_book(KB / "pricing" / "repair_price_book_2026.csv")
    assert "After-hours dispatch: $149 (Waived for members)" in text
    assert "Run capacitor replacement: $180 to $260" in text


def test_conflict_register_has_a_row_for_every_conflicting_fact():
    rows = list(csv.DictReader((ROOT / "data" / "conflict_register.csv").open()))
    facts = {r["fact"] for r in rows}
    for fact in ["diagnostic fee", "diagnostic credit", "after-hours fee", "late cancellation notice", "phone hours",
                 "appointment windows", "membership standard price", "membership plus price", "membership cancellation",
                 "membership transfer", "repair labour warranty", "installation labour warranty",
                 "manufacturer registration", "service area", "emergencies", "waitlist", "supervisor callbacks",
                 "payments", "duct cleaning"]:
        assert fact in facts
    assert all(r["winner"] and r["reason"] for r in rows)
    service_area = next(r for r in rows if r["fact"] == "service area")
    assert service_area["winner"] == "policies/service_area.md"


def test_conversion_removes_outputs_for_documents_no_longer_searchable(tmp_path):
    from pipeline.convert import main

    stale = tmp_path / "archive__old_notes.md"
    stale.write_text("old $79 fee")
    main(out=tmp_path)
    assert not stale.exists()
    assert (tmp_path / "faq__customer_faq.md").exists()
