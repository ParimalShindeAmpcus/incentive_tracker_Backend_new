"""Consolidated File parser and month-agnostic Smart Match hours."""

from __future__ import annotations

from app.services.vlookup.parsers.client_hours import (
    aggregate_hours_by_candidate,
    parse_client_hours_file,
)
from app.services.vlookup.reconciliation_matcher import ReconciliationMatcher


CONSOLIDATED_CSV = """Candidate Name,Old Hours,New Hours,Organisation
Brijesh Kumar Dubey,170,160,Bravens Inc
Kavitha Rajkumar,180,160,Ampcus Inc
Joel Ortega,165,160,ITech Inc
Tara Joens White,103.5,103.5,Bravens Inc
"""


ALT_CONSOLIDATED_CSV = """Name,Actual Quantity (Qty),160 Hours,Source
Brijesh Kumar Dubey,170,160,Bravens Inc
Kavitha Rajkumar,180,160,Ampcus Inc
Joel Ortega,165,160,ITech Inc
Tara Joens White,103.5,103.5,Bravens Inc
"""

MIXED_CONSOLIDATED_CSV = """Name,Old Hours,160 Hours,Organisation
Brijesh Kumar Dubey,170,160,Bravens Inc
Kavitha Rajkumar,180,160,Ampcus Inc
"""


def test_parse_consolidated_uses_new_hours_and_organisation():
    parsed = parse_client_hours_file(CONSOLIDATED_CSV.encode("utf-8"), "hours-consolidate_file.csv")
    assert parsed["format"] == "consolidated"
    assert parsed["months_found"] == []
    by_name = {row["candidate_name"]: row for row in parsed["rows"]}
    assert by_name["Brijesh Kumar Dubey"]["hours_worked"] == 160
    assert by_name["Brijesh Kumar Dubey"]["old_hours"] == 170
    assert by_name["Brijesh Kumar Dubey"]["organisation"] == "Bravens Inc"
    assert by_name["Brijesh Kumar Dubey"]["client_name"] == ""
    assert by_name["Kavitha Rajkumar"]["organisation"] == "Ampcus Inc"
    assert by_name["Tara Joens White"]["hours_worked"] == 103.5


def test_aggregate_keeps_old_hours_for_match_cards():
    parsed = parse_client_hours_file(CONSOLIDATED_CSV.encode("utf-8"), "canonical.csv")
    groups = aggregate_hours_by_candidate(parsed["rows"], group_by_month=False)
    by_name = {g["candidate_name"]: g for g in groups}
    assert by_name["Brijesh Kumar Dubey"]["old_hours"] == 170
    assert by_name["Brijesh Kumar Dubey"]["total_hours"] == 160


def _row_fingerprint(row: dict) -> tuple:
    return (
        row["candidate_name"],
        row["old_hours"],
        row["hours_worked"],
        row["organisation"],
        row["client_name"],
    )


def test_alternate_column_names_parse_the_same_records():
    canonical = parse_client_hours_file(CONSOLIDATED_CSV.encode("utf-8"), "canonical.csv")
    alternate = parse_client_hours_file(ALT_CONSOLIDATED_CSV.encode("utf-8"), "alternate.csv")
    assert { _row_fingerprint(r) for r in canonical["rows"] } == {
        _row_fingerprint(r) for r in alternate["rows"]
    }
    by_name = {row["candidate_name"]: row for row in alternate["rows"]}
    assert by_name["Brijesh Kumar Dubey"]["hours_worked"] == 160
    assert by_name["Brijesh Kumar Dubey"]["old_hours"] == 170
    assert by_name["Brijesh Kumar Dubey"]["organisation"] == "Bravens Inc"


def test_mixed_column_name_variants_parse():
    parsed = parse_client_hours_file(MIXED_CONSOLIDATED_CSV.encode("utf-8"), "mixed.csv")
    by_name = {row["candidate_name"]: row for row in parsed["rows"]}
    assert by_name["Brijesh Kumar Dubey"]["hours_worked"] == 160
    assert by_name["Brijesh Kumar Dubey"]["old_hours"] == 170
    assert by_name["Kavitha Rajkumar"]["organisation"] == "Ampcus Inc"


def test_alternate_headers_produce_the_same_match_result():
    templates = [
        {
            "id": 1,
            "candidate_id": "SUB2201077",
            "candidate_name": "Brijesh Kumar Dubey",
            "client_name": "Infosys",
            "month": "2025-06",
        },
        {
            "id": 2,
            "candidate_id": "AMSUB24-3321",
            "candidate_name": "Kavitha Rajkumar",
            "client_name": "Amazon",
            "month": "2025-06",
        },
    ]
    matcher = ReconciliationMatcher()
    canonical_groups = aggregate_hours_by_candidate(
        parse_client_hours_file(CONSOLIDATED_CSV.encode("utf-8"), "canonical.csv")["rows"],
        group_by_month=False,
    )
    alternate_groups = aggregate_hours_by_candidate(
        parse_client_hours_file(ALT_CONSOLIDATED_CSV.encode("utf-8"), "alternate.csv")["rows"],
        group_by_month=False,
    )
    canonical = matcher.match(templates, canonical_groups, target_month="2025-06")
    alternate = matcher.match(templates, alternate_groups, target_month="2025-06")

    def _summary(results: dict) -> set:
        return {
            (
                row["template_candidate_id"],
                row["match_status"],
                row["total_hours"],
                row["messy_name_original"],
                row["messy_client_name"],
            )
            for rows in results.values()
            for row in rows
            if row.get("template_candidate_id") in (1, 2)
        }

    assert _summary(canonical) == _summary(alternate)
    assert canonical["matched"][0]["total_hours"] == 160


def test_both_header_variants_in_one_file_do_not_duplicate_rows():
    csv = (
        "Candidate Name,Name,Old Hours,Actual Quantity (Qty),New Hours,160 Hours,Organisation,Source\n"
        "Brijesh Kumar Dubey,Brijesh Kumar Dubey,170,999,160,1,Bravens Inc,Other Org\n"
    )
    parsed = parse_client_hours_file(csv.encode("utf-8"), "both-headers.csv")
    assert parsed["row_count"] == 1
    row = parsed["rows"][0]
    assert row["candidate_name"] == "Brijesh Kumar Dubey"
    assert row["old_hours"] == 170
    assert row["hours_worked"] == 160
    assert row["organisation"] == "Bravens Inc"


def test_parse_consolidated_rejects_hours_template_shape():
    template = (
        "Candidate ID,Candidate Name,Client Name,Hours Worked,Month\n"
        "SUB2201077,Brijesh Kumar Dubey,Infosys,0,2025-06\n"
    ).encode("utf-8")
    try:
        parse_client_hours_file(template, "hours-template.csv")
    except ValueError as exc:
        assert "Consolidated File" in str(exc)
    else:
        raise AssertionError("Hours Template must not be accepted as a Consolidated File")


def test_match_fills_template_month_from_consolidated_new_hours():
    parsed = parse_client_hours_file(CONSOLIDATED_CSV.encode("utf-8"), "consolidated.csv")
    groups = aggregate_hours_by_candidate(parsed["rows"], group_by_month=False)
    templates = [
        {
            "id": 1,
            "candidate_id": "SUB2201077",
            "candidate_name": "Brijesh Kumar Dubey",
            "client_name": "Infosys",
            "month": "2025-06",
        },
        {
            "id": 2,
            "candidate_id": "SUB2201077",
            "candidate_name": "Brijesh Kumar Dubey",
            "client_name": "Infosys",
            "month": "2025-07",
        },
        {
            "id": 3,
            "candidate_id": "AMSUB24-3321",
            "candidate_name": "Kavitha Rajkumar",
            "client_name": "Amazon",
            "month": "2025-06",
        },
        {
            "id": 4,
            "candidate_id": "MISSING-1",
            "candidate_name": "Nobody Here",
            "client_name": "Infosys",
            "month": "2025-06",
        },
    ]
    results = ReconciliationMatcher().match(templates, groups, target_month="2025-06")
    by_id = {
        row["template_candidate_id"]: row
        for rows in results.values()
        for row in rows
    }
    june = by_id[1]
    july = by_id[2]
    kavitha = by_id[3]
    missing = by_id[4]
    assert june["match_status"] == "matched"
    assert june["total_hours"] == 160
    assert june["monthly_hours"]["2025-06"] == 160
    assert june["messy_client_name"] == "Bravens Inc"
    assert kavitha["match_status"] == "matched"
    assert kavitha["total_hours"] == 160
    assert kavitha["messy_client_name"] == "Ampcus Inc"
    assert july["match_status"] == "matched"
    assert july["total_hours"] == 160
    assert july["messy_month"] == "2025-07"
    assert missing["match_status"] == "unmatched"


ALL_ORG_CSV = """Candidate Name,Old Hours,New Hours,Organisation
Brijesh Kumar Dubey,170,160,Bravens Inc
Kavitha Rajkumar,180,160,Ampcus Inc
Joel Ortega,165,160,ITech Inc
Org Apokrin Person,140,140,Apokrin LLC
Org BravensTech Person,155,150,BravensTech
"""


def test_all_organisations_parse_and_match_by_name_only():
    parsed = parse_client_hours_file(ALL_ORG_CSV.encode("utf-8"), "consolidated.csv")
    orgs = {row["organisation"] for row in parsed["rows"]}
    assert orgs == {
        "Ampcus Inc",
        "Bravens Inc",
        "ITech Inc",
        "Apokrin LLC",
        "BravensTech",
    }
    assert all(row["client_name"] == "" for row in parsed["rows"])
    groups = aggregate_hours_by_candidate(parsed["rows"], group_by_month=False)
    templates = [
        {"id": 1, "candidate_id": "A1", "candidate_name": "Brijesh Kumar Dubey", "client_name": "Infosys", "month": "2025-06"},
        {"id": 2, "candidate_id": "A2", "candidate_name": "Kavitha Rajkumar", "client_name": "Amazon", "month": "2025-06"},
        {"id": 3, "candidate_id": "A3", "candidate_name": "Joel Ortega", "client_name": "ESPN / Disney", "month": "2025-06"},
        {"id": 4, "candidate_id": "A4", "candidate_name": "Org Apokrin Person", "client_name": "Hitachi Globallogic", "month": "2025-06"},
        {"id": 5, "candidate_id": "A5", "candidate_name": "Org BravensTech Person", "client_name": "Cognizant Technology", "month": "2025-06"},
    ]
    results = ReconciliationMatcher().match(templates, groups, target_month="2025-06")
    matched = {row["template_candidate_id_str"]: row for row in results["matched"]}
    assert matched["A1"]["total_hours"] == 160
    assert matched["A2"]["total_hours"] == 160
    assert matched["A3"]["total_hours"] == 160
    assert matched["A4"]["total_hours"] == 140
    assert matched["A5"]["total_hours"] == 150
    # Organisation is retained on the source side, never as Hours Template client.
    assert matched["A1"]["messy_client_name"] == "Bravens Inc"
    assert matched["A4"]["messy_client_name"] == "Apokrin LLC"
    assert matched["A5"]["messy_client_name"] == "BravensTech"


def test_month_filter_uses_template_month_and_template_client_on_export():
    from datetime import datetime

    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
    from sqlalchemy.pool import StaticPool

    from app.core.db import Base
    from app.repositories.entities.vlookup import (
        VLookupMatchedRecord,
        VLookupTemplateCandidate,
        VLookupUploadBatch,
    )
    from app.services.vlookup.vlookup_service import _hours_export_rows, _match_belongs_to_month

    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    db = sessionmaker(bind=engine)()
    try:
        db.add(
            VLookupUploadBatch(
                batch_id="e2e-1",
                file_type="template_and_consolidated",
                filename="template.csv + consolidated.csv",
                status="completed",
                matched_count=2,
                unmatched_count=0,
                target_month="2025-06",
                uploaded_by="test",
                completed_at=datetime.utcnow(),
            )
        )
        june = VLookupTemplateCandidate(
            candidate_id="SUB1",
            candidate_name="Brijesh Kumar Dubey",
            client_name="Infosys",
            template_hours=0,
            month="2025-06",
            upload_batch_id="e2e-1",
        )
        july = VLookupTemplateCandidate(
            candidate_id="SUB1",
            candidate_name="Brijesh Kumar Dubey",
            client_name="Infosys",
            template_hours=0,
            month="2025-07",
            upload_batch_id="e2e-1",
        )
        db.add_all([june, july])
        db.flush()
        for template, month, hours in ((june, "2025-06", 160), (july, "2025-07", 160)):
            db.add(
                VLookupMatchedRecord(
                    template_candidate_id=template.id,
                    template_candidate_name=template.candidate_name,
                    template_candidate_id_str=template.candidate_id,
                    messy_name_original="Brijesh Kumar Dubey",
                    messy_client_name="Bravens Inc",
                    messy_month=month,
                    weekly_breakdown={},
                    total_hours=hours,
                    confidence_score=99.0,
                    match_status="matched",
                    match_method="name",
                    match_explanation={"monthly_hours": {month: hours}},
                    upload_batch_id="e2e-1",
                )
            )
        db.commit()

        assert _match_belongs_to_month(db.query(VLookupMatchedRecord).first(), june, "2025-06") is True

        _latest, june_rows, month = _hours_export_rows(
            db,
            batch_id="e2e-1",
            statuses=["matched", "accepted"],
            month_key="2025-06",
            require_template=True,
        )
        assert month == "2025-06"
        assert len(june_rows) == 1
        row = june_rows[0]
        assert list(row.keys())[:5]  # sanity
        assert row["Candidate ID"] == "SUB1"
        assert row["Candidate Name"] == "Brijesh Kumar Dubey"
        assert row["Client Name"] == "Infosys"
        assert row["Hours Worked"] == 160
        assert row["Month"] == "2025-06"
        assert row["Organisation"] == "Bravens Inc"
        assert row["Client Name"] != "Bravens Inc"

        _latest, july_rows, _m = _hours_export_rows(
            db,
            batch_id="e2e-1",
            statuses=["matched", "accepted"],
            month_key="2025-07",
            require_template=True,
        )
        assert len(july_rows) == 1
        assert july_rows[0]["Month"] == "2025-07"
        assert july_rows[0]["Client Name"] == "Infosys"
    finally:
        db.close()
        Base.metadata.drop_all(bind=engine)


def test_consolidated_file_list_includes_old_and_new_hours():
    from datetime import datetime

    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
    from sqlalchemy.pool import StaticPool

    from app.core.db import Base
    from app.repositories.entities.vlookup import VLookupUploadBatch, VLookupWeeklyHours
    from app.services.vlookup.vlookup_service import list_messy_file

    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    db = sessionmaker(bind=engine)()
    try:
        db.add(
            VLookupUploadBatch(
                batch_id="cf-1",
                file_type="template_and_consolidated",
                filename="template.csv + consolidated.csv",
                status="completed",
                uploaded_by="test",
                completed_at=datetime.utcnow(),
            )
        )
        db.add(
            VLookupWeeklyHours(
                candidate_name_messy="Brijesh Kumar Dubey",
                hours_worked=160,
                old_hours=170,
                new_hours=160,
                week="New Hours",
                month="",
                client_name="Bravens Inc",
                normalized_name="brijesh kumar dubey",
                upload_batch_id="cf-1",
            )
        )
        db.add(
            VLookupWeeklyHours(
                candidate_name_messy="Tara Joens White",
                hours_worked=104,
                old_hours=103.5,
                new_hours=103.5,
                week="New Hours",
                month="",
                client_name="Bravens Inc",
                normalized_name="tara joens white",
                upload_batch_id="cf-1",
            )
        )
        db.commit()

        payload = list_messy_file(db, batch_id="cf-1")
        by_name = {row["candidate_name"]: row for row in payload["identities"]}
        brijesh = by_name["Brijesh Kumar Dubey"]
        tara = by_name["Tara Joens White"]
        assert brijesh["old_hours"] == 170
        assert brijesh["total_hours"] == 160
        assert brijesh["organisation"] == "Bravens Inc"
        assert tara["old_hours"] == 103.5
        assert tara["total_hours"] == 103.5
        assert set(brijesh) >= {
            "candidate_name",
            "old_hours",
            "total_hours",
            "organisation",
        }
    finally:
        db.close()
        Base.metadata.drop_all(bind=engine)
