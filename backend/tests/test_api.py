"""Integration tests for the API (grid, rules enforcement, RBAC, notes, export)."""
from __future__ import annotations


def _admin():
    return {"X-User": "admin"}


def _viewer():
    return {"X-User": "viewer"}


def test_health(client):
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"


def test_list_plants_includes_seeded(client):
    r = client.get("/plants", headers=_viewer())
    assert r.status_code == 200
    names = {p["name"] for p in r.json()}
    assert {"Limana", "Casale", "Bradford"}.issubset(names)
    # Casale has a six-week frozen period.
    casale = next(p for p in r.json() if p["name"] == "Casale")
    assert casale["frozen_weeks"] == 6


def _limana_id(client):
    r = client.get("/plants", headers=_viewer())
    return next(p["id"] for p in r.json() if p["name"] == "Limana")


def test_grid_returns_rows_and_open_weeks(client):
    plant_id = _limana_id(client)
    # Ask far enough ahead that some weeks are outside the frozen period.
    r = client.get(
        f"/plants/{plant_id}/grid",
        params={"weeks_count": 8},
        headers=_viewer(),
    )
    assert r.status_code == 200
    body = r.json()
    assert len(body["rows"]) >= 1
    assert len(body["weeks"]) == 8


def _first_open_week(client, plant_id):
    r = client.get(f"/plants/{plant_id}/grid", params={"weeks_count": 12}, headers=_viewer())
    for row in r.json()["rows"]:
        for cell in row["cells"]:
            if not cell["computed"]["frozen"]:
                return row["line"]["id"], cell["iso_year_week"]
    raise AssertionError("no open week found")


def test_edit_open_cell_applies_rules(client):
    plant_id = _limana_id(client)
    line_id, week = _first_open_week(client, plant_id)
    # Set an approved cadence "5" (100 pieces, 5 workers) with a +10 delta.
    r = client.put(
        f"/plants/{plant_id}/cells/{line_id}/{week}",
        json={"cadence_option_id": 3, "workers_assigned": 5, "capacity_delta": 10},
        headers=_admin(),
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["computed"]["expected_pieces"] == 100
    assert body["computed"]["actual_output"] == 110


def test_edit_rejects_unmatched_workers(client):
    plant_id = _limana_id(client)
    line_id, week = _first_open_week(client, plant_id)
    # Cadence "5" requires 5 workers; sending 3 must be rejected.
    r = client.put(
        f"/plants/{plant_id}/cells/{line_id}/{week}",
        json={"cadence_option_id": 3, "workers_assigned": 3},
        headers=_admin(),
    )
    assert r.status_code == 400
    assert r.json()["error"]["code"] == "workers_mismatch"


def test_edit_frozen_week_blocked(client):
    plant_id = _limana_id(client)
    # The current week is always frozen; grab any line.
    grid = client.get(
        f"/plants/{plant_id}/grid", params={"weeks_count": 1}, headers=_viewer()
    ).json()
    line_id = grid["rows"][0]["line"]["id"]
    frozen_week = grid["weeks"][0]
    r = client.put(
        f"/plants/{plant_id}/cells/{line_id}/{frozen_week}",
        json={"capacity_delta": 5},
        headers=_admin(),
    )
    assert r.status_code == 409
    assert r.json()["error"]["code"] == "frozen_week"


def test_viewer_cannot_edit(client):
    plant_id = _limana_id(client)
    line_id, week = _first_open_week(client, plant_id)
    r = client.put(
        f"/plants/{plant_id}/cells/{line_id}/{week}",
        json={"capacity_delta": 1},
        headers=_viewer(),
    )
    assert r.status_code == 403


def test_note_creation_and_highlight(client):
    plant_id = _limana_id(client)
    line_id, week = _first_open_week(client, plant_id)
    r = client.post(
        "/notes",
        json={"product_line_id": line_id, "iso_year_week": week, "text": "Strike on Monday"},
        headers=_admin(),
    )
    assert r.status_code == 201
    # The grid should now flag the cell as having a note.
    grid = client.get(
        f"/plants/{plant_id}/grid", params={"weeks_count": 12}, headers=_viewer()
    ).json()
    flagged = any(
        cell["computed"]["has_note"]
        for row in grid["rows"]
        for cell in row["cells"]
        if row["line"]["id"] == line_id and cell["iso_year_week"] == week
    )
    assert flagged is True


def test_compass_export_returns_xlsx(client):
    plant_id = _limana_id(client)
    r = client.get(
        "/exports/compass",
        params={"plant_id": plant_id, "weeks_count": 4},
        headers=_admin(),
    )
    assert r.status_code == 200
    assert "spreadsheetml" in r.headers["content-type"]


def test_scenario_create_and_promote(client):
    plant_id = _limana_id(client)
    r = client.post(
        "/scenarios",
        json={"name": "High demand", "plant_id": plant_id},
        headers=_admin(),
    )
    assert r.status_code == 201, r.text
    scenario_id = r.json()["id"]
    r2 = client.post(f"/scenarios/{scenario_id}/promote", headers=_admin())
    assert r2.status_code == 200
    assert r2.json()["promoted"] is True


def test_production_transfer_requires_sales_agreement(client):
    plant_id = _limana_id(client)
    # Find another plant to transfer to.
    plants = client.get("/plants", headers=_viewer()).json()
    other = next(p["id"] for p in plants if p["id"] != plant_id)

    # Create a dedicated line to transfer so we don't mutate seeded lines that
    # other tests depend on.
    created = client.post(
        "/config/lines",
        json={"id": 0, "plant_id": plant_id, "name": "Transferable Line",
              "product_family": "Test", "platforms": []},
        headers=_admin(),
    )
    assert created.status_code == 201, created.text
    line_id = created.json()["id"]

    r = client.post(
        "/transfers",
        json={"product_line_id": line_id, "from_plant_id": plant_id, "to_plant_id": other,
              "market": "France"},
        headers=_admin(),
    )
    assert r.status_code == 201, r.text
    body = r.json()
    transfer_id = body["id"]
    assert body["sales_agreed"] is False
    assert body["requires_sales_agreement"] is True

    # Applying before sales agreement is blocked (R8.3).
    blocked = client.post(f"/transfers/{transfer_id}/apply", headers=_admin())
    assert blocked.status_code == 409
    assert blocked.json()["error"]["code"] == "sales_agreement_required"

    # After sales agrees, it can be applied.
    agreed = client.post(f"/transfers/{transfer_id}/agree", headers=_admin())
    assert agreed.status_code == 200
    assert agreed.json()["sales_agreed"] is True
    applied = client.post(f"/transfers/{transfer_id}/apply", headers=_admin())
    assert applied.status_code == 200
    assert applied.json()["applied"] is True


def test_hypothetical_plant_excluded_by_default(client):
    r = client.post(
        "/config/plants",
        json={"id": 0, "name": "Sandbox NC5", "country": "Test", "region": "EMEA",
              "frozen_weeks": 3, "hypothetical": True},
        headers=_admin(),
    )
    assert r.status_code == 201, r.text

    default = client.get("/plants", headers=_viewer()).json()
    assert not any(p["name"] == "Sandbox NC5" for p in default)

    with_hyp = client.get(
        "/plants", params={"include_hypothetical": True}, headers=_viewer()
    ).json()
    assert any(p["name"] == "Sandbox NC5" for p in with_hyp)


def test_special_rule_caps_grid_output(client):
    plant_id = _limana_id(client)
    line_id, week = _first_open_week(client, plant_id)
    # Set a known cadence: "5" => 100 pieces.
    client.put(
        f"/plants/{plant_id}/cells/{line_id}/{week}",
        json={"cadence_option_id": 3, "workers_assigned": 5, "capacity_delta": 0},
        headers=_admin(),
    )
    # Add a cap rule at 40.
    rule = client.post(
        "/config/rules",
        json={"name": "cap40", "rule_type": "cap", "params_json": "{\"max\": 40}",
              "active": True},
        headers=_admin(),
    )
    assert rule.status_code == 201, rule.text
    rule_id = rule.json()["id"]

    grid = client.get(
        f"/plants/{plant_id}/grid", params={"weeks_count": 12}, headers=_viewer()
    ).json()
    capped = next(
        cell["computed"]["actual_output"]
        for row in grid["rows"]
        for cell in row["cells"]
        if row["line"]["id"] == line_id and cell["iso_year_week"] == week
    )
    assert capped == 40

    # Clean up the rule so it doesn't affect later assertions.
    client.delete(f"/config/rules/{rule_id}", headers=_admin())


def test_version_snapshot_and_latest_official_diff(client):
    plant_id = _limana_id(client)
    # Save a named version, then release it official.
    v = client.post(
        "/versions",
        json={"name": "Cycle base", "plant_id": plant_id, "explanation": "baseline"},
        headers=_admin(),
    )
    assert v.status_code == 201, v.text
    version_id = v.json()["id"]
    rel = client.post(f"/versions/{version_id}/release", headers=_admin())
    assert rel.status_code == 200

    # Snapshot rows are readable back out (R7.4).
    snap = client.get(f"/versions/{version_id}/snapshot", headers=_viewer())
    assert snap.status_code == 200
    assert isinstance(snap.json()["rows"], list)

    # Diff against latest official works without passing an id (R7.2).
    diff = client.get("/versions/diff/latest-official", headers=_viewer())
    assert diff.status_code == 200
    official = client.get("/versions/official", headers=_viewer()).json()
    official_ids = {v["id"] for v in official}
    assert version_id in official_ids
    # The endpoint resolves to one of the released official versions.
    assert diff.json()["base_version_id"] in official_ids


def test_configurable_kpi_dashboard(client):
    plant_id = _limana_id(client)
    line_id, week = _first_open_week(client, plant_id)
    # Known cadence "5" => 100 pieces, no delta.
    client.put(
        f"/plants/{plant_id}/cells/{line_id}/{week}",
        json={"cadence_option_id": 3, "workers_assigned": 5, "capacity_delta": 0},
        headers=_admin(),
    )

    # Define a KPI through configuration (R13.3).
    kpi = client.post(
        "/config/kpis",
        json={"name": "Total output", "source_field": "actual_output",
              "aggregation": "sum", "unit": "pcs", "active": True},
        headers=_admin(),
    )
    assert kpi.status_code == 201, kpi.text
    kpi_id = kpi.json()["id"]

    dash = client.get(
        f"/plants/{plant_id}/kpis", params={"weeks_count": 12}, headers=_viewer()
    )
    assert dash.status_code == 200, dash.text
    body = dash.json()
    total = next(k for k in body["kpis"] if k["name"] == "Total output")
    # The edited cell (100) is included in the sum across the plant's official lines.
    assert total["value"] >= 100
    assert total["unit"] == "pcs"

    # An invalid source field is rejected (config validation).
    bad = client.post(
        "/config/kpis",
        json={"name": "Bad", "source_field": "nonsense", "aggregation": "sum"},
        headers=_admin(),
    )
    assert bad.status_code == 400
    assert bad.json()["error"]["code"] == "invalid_kpi_field"

    client.delete(f"/config/kpis/{kpi_id}", headers=_admin())


def _find_linked_lines(client, plant_id):
    """Return (primary_line_id, secondary_line_id) for the seeded linked pair, or None."""
    grid = client.get(
        f"/plants/{plant_id}/grid", params={"weeks_count": 12}, headers=_viewer()
    ).json()
    line_ids = {row["line"]["name"]: row["line"]["id"] for row in grid["rows"]}
    if "Line A1-Front" not in line_ids or "Line A1-Back" not in line_ids:
        return None
    return line_ids["Line A1-Front"], line_ids["Line A1-Back"]


def test_linked_slave_line_deducts_master_output(client):
    """A Slave line's output is its own minus the Master's, keeping its own staffing (R4.1)."""
    plant_id = _limana_id(client)
    pair = _find_linked_lines(client, plant_id)
    assert pair is not None, "seeded linked line pair (A1-Front/A1-Back) should be present"
    master_id, slave_id = pair

    _, week = _first_open_week(client, plant_id)

    # Master runs cadence "5" => 100 pieces (5 workers).
    rm = client.put(
        f"/plants/{plant_id}/cells/{master_id}/{week}",
        json={"cadence_option_id": 3, "workers_assigned": 5, "capacity_delta": 0},
        headers=_admin(),
    )
    assert rm.status_code == 200, rm.text

    # Slave runs cadence "11 + 11" => 144 pieces (22 workers), no adjustment yet.
    rs = client.put(
        f"/plants/{plant_id}/cells/{slave_id}/{week}",
        json={"cadence_option_id": 2, "workers_assigned": 22, "capacity_delta": 0},
        headers=_admin(),
    )
    assert rs.status_code == 200, rs.text
    body = rs.json()
    # Slave keeps its own cadence and workers (no forced zeroing).
    assert body["cadence_option_id"] == 2
    assert body["workers_assigned"] == 22
    # Effective output deducts the Master's theoretical: 144 - 100 = 44.
    assert body["computed"]["expected_pieces"] == 144
    assert body["computed"]["actual_output"] == 44

    # Adj. Qnty is applied on top of the deduction: 144 - 100 + 10 = 54.
    ra = client.put(
        f"/plants/{plant_id}/cells/{slave_id}/{week}",
        json={"capacity_delta": 10},
        headers=_admin(),
    )
    assert ra.status_code == 200, ra.text
    assert ra.json()["computed"]["actual_output"] == 54

    # The Slave still contributes its own workers to the plant workforce total.
    grid = client.get(
        f"/plants/{plant_id}/grid", params={"weeks_count": 12}, headers=_viewer()
    ).json()
    wf = next((w for w in grid["workforce"] if w["iso_year_week"] == week), None)
    if wf is not None:
        assert wf["assigned_workers"] >= 27  # master 5 + slave 22


def test_grid_includes_per_week_totals(client):
    plant_id = _limana_id(client)
    grid = client.get(
        f"/plants/{plant_id}/grid", params={"weeks_count": 8}, headers=_viewer()
    ).json()
    assert "totals" in grid
    assert len(grid["totals"]) == len(grid["weeks"])

    # For each week, the totals equal the sum across the visible line rows.
    for i, w in enumerate(grid["weeks"]):
        expected = sum(row["cells"][i]["computed"]["expected_pieces"] for row in grid["rows"])
        actual = sum(row["cells"][i]["computed"]["actual_output"] for row in grid["rows"])
        workers = sum(row["cells"][i]["workers_assigned"] for row in grid["rows"])
        totals = grid["totals"][i]
        assert totals["iso_year_week"] == w
        assert totals["total_expected_pieces"] == expected
        assert totals["total_actual_output"] == actual
        assert totals["total_workers"] == workers


def test_six_day_plant_prorates_output(client):
    # Create a 6-day plant via configuration and add a line to it.
    p = client.post(
        "/config/plants",
        json={"id": 0, "name": "Istanbul Test", "country": "Turkey", "region": "EMEA",
              "frozen_weeks": 1, "standard_working_days": 6, "hypothetical": False},
        headers=_admin(),
    )
    assert p.status_code == 201, p.text
    plant = p.json()
    assert plant["standard_working_days"] == 6
    plant_id = plant["id"]

    line = client.post(
        "/config/lines",
        json={"id": 0, "plant_id": plant_id, "name": "IST Line", "platforms": []},
        headers=_admin(),
    )
    assert line.status_code == 201, line.text
    line_id = line.json()["id"]

    # Find an open week for this plant (frozen_weeks=1 leaves near weeks open soon).
    grid = client.get(
        f"/plants/{plant_id}/grid", params={"weeks_count": 12}, headers=_viewer()
    ).json()
    open_week = next(
        cell["iso_year_week"]
        for row in grid["rows"]
        for cell in row["cells"]
        if row["line"]["id"] == line_id and not cell["computed"]["frozen"]
    )

    # Cadence id 1 = "1" (60 pieces, 1 worker). Set 3 of 6 working days.
    r = client.put(
        f"/plants/{plant_id}/cells/{line_id}/{open_week}",
        json={"working_days": 3, "cadence_option_id": 1, "workers_assigned": 1,
              "capacity_delta": 0},
        headers=_admin(),
    )
    assert r.status_code == 200, r.text
    body = r.json()
    # 60 * 3/6 = 30 on a 6-day plant (would wrongly be 36 with a hardcoded 5-day week).
    assert body["computed"]["expected_pieces"] == 30
    assert body["computed"]["actual_output"] == 30


def test_grid_takt_label_default_and_configurable(client):
    """The grid exposes the takt label, editable via configuration (Column E)."""
    plant_id = _limana_id(client)
    grid = client.get(
        f"/plants/{plant_id}/grid", params={"weeks_count": 1}, headers=_viewer()
    ).json()
    # Defaults to "Takt" when nothing is configured.
    assert grid["takt_label"] == "Takt"

    # Central admin can change it through the config-over-code layer (R13).
    up = client.put(
        "/config",
        json={"key": "takt_label", "value": "Takt Time"},
        headers=_admin(),
    )
    assert up.status_code == 200, up.text

    grid2 = client.get(
        f"/plants/{plant_id}/grid", params={"weeks_count": 1}, headers=_viewer()
    ).json()
    assert grid2["takt_label"] == "Takt Time"

    # Restore the default so other tests are unaffected.
    client.put("/config", json={"key": "takt_label", "value": "Takt"}, headers=_admin())


def test_line_links_crud_and_validation(client):
    """Linee_Collegate config: create/list/delete master-slave links with validation (R4)."""
    plant_id = _limana_id(client)
    grid = client.get(
        f"/plants/{plant_id}/grid", params={"weeks_count": 1}, headers=_viewer()
    ).json()
    by_name = {row["line"]["name"]: row["line"]["id"] for row in grid["rows"]}
    solo = by_name["Line A0-Solo"]
    front = by_name["Line A1-Front"]

    # The seeded Master/Slave link (A1-Front -> A1-Back) is listed.
    listing = client.get("/config/line-links", headers=_admin())
    assert listing.status_code == 200, listing.text
    assert any(link["slave_line_name"] == "Line A1-Back" for link in listing.json())

    # Create a valid link within the plant.
    created = client.post(
        "/config/line-links",
        json={"plant_id": plant_id, "master_line_id": solo, "slave_line_id": front, "ratio": 1.0},
        headers=_admin(),
    )
    assert created.status_code == 201, created.text
    link = created.json()
    assert link["master_line_name"] == "Line A0-Solo"
    assert link["slave_line_name"] == "Line A1-Front"

    # Master and Slave must differ.
    same = client.post(
        "/config/line-links",
        json={"plant_id": plant_id, "master_line_id": front, "slave_line_id": front},
        headers=_admin(),
    )
    assert same.status_code == 400
    assert same.json()["error"]["code"] == "invalid_line_link"

    # A spare in-plant line to exercise the remaining validation branches.
    other = client.post(
        "/config/lines",
        json={"id": 0, "plant_id": plant_id, "name": "Temp Slave", "platforms": []},
        headers=_admin(),
    ).json()["id"]

    # An unknown plant id is rejected (404).
    wrong_plant = client.post(
        "/config/line-links",
        json={"plant_id": 999999, "master_line_id": solo, "slave_line_id": other},
        headers=_admin(),
    )
    assert wrong_plant.status_code == 404

    # A non-admin cannot manage links.
    forbidden = client.post(
        "/config/line-links",
        json={"plant_id": plant_id, "master_line_id": solo, "slave_line_id": other},
        headers=_viewer(),
    )
    assert forbidden.status_code == 403

    # Delete the created link; a second delete is a 404.
    gone = client.delete(f"/config/line-links/{link['id']}", headers=_admin())
    assert gone.status_code == 204
    missing = client.delete(f"/config/line-links/{link['id']}", headers=_admin())
    assert missing.status_code == 404


def test_official_version_excel_export(client):
    """A released version exports as a tabular .xlsx incl. takt label and Adj. Qnty (R7.5, R10)."""
    plant_id = _limana_id(client)
    v = client.post(
        "/versions",
        json={"name": "Export cycle", "plant_id": plant_id, "explanation": "export test"},
        headers=_admin(),
    )
    assert v.status_code == 201, v.text
    version_id = v.json()["id"]
    rel = client.post(f"/versions/{version_id}/release", headers=_admin())
    assert rel.status_code == 200

    # The snapshot carries line names and the takt label for a readable table.
    snap = client.get(f"/versions/{version_id}/snapshot", headers=_viewer())
    assert snap.status_code == 200, snap.text
    body = snap.json()
    assert body["takt_label"] == "Takt"
    if body["rows"]:
        assert "line_name" in body["rows"][0]

    # The Excel export streams an xlsx document.
    xlsx = client.get(f"/versions/{version_id}/export.xlsx", headers=_viewer())
    assert xlsx.status_code == 200, xlsx.text
    assert "spreadsheetml" in xlsx.headers["content-type"]
    assert len(xlsx.content) > 0

    # A missing version yields a 404.
    absent = client.get("/versions/999999/export.xlsx", headers=_viewer())
    assert absent.status_code == 404
