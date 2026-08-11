"""Functional contract tests for the rankings editor endpoints."""

import csv
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

import backend.server as server


def _write(path: Path, text: str) -> Path:
    path.write_text(text, encoding="utf-8")
    return path


@pytest.fixture
def rankings_files(tmp_path):
    files = {
        "swimmer_type_color_rankings": _write(
            tmp_path / "color_rankings.csv",
            "swimmer_type_id,color_id,rank\n1,1,1\n1,2,2\n2,2,1\n2,1,2\n",
        ),
        "personality_colors": _write(
            tmp_path / "colors.csv",
            "color_id,color_name,traits\n1,Blue,Calm\n2,Green,Patient\n",
        ),
        "swimmer_types": _write(
            tmp_path / "swimmer_types.csv",
            "swimmer_type_id,swimmer_type_name\n1,Nervous\n2,Fearless\n",
        ),
    }
    state = server.application_services.state
    with state.settings_lock:
        for purpose, path in files.items():
            state.settings["default_files"][purpose] = str(path)
            state.settings["last_selected_files"][purpose] = str(path)
    return files


@pytest.fixture
def client():
    return TestClient(server.app)


def _load(client):
    response = client.post(
        "/api/rankings_editor/load",
        json={"purpose": "swimmer_type_color_rankings"},
    )
    assert response.status_code == 200
    return response.json()


def _save_payload(loaded, items, order):
    return {
        "purpose": loaded["purpose"],
        "items": items,
        "swimmer_types": [
            {"id": swimmer_type["id"], "item_keys": list(order)}
            for swimmer_type in loaded["swimmer_types"]
        ],
    }


def test_load_returns_complete_frontend_contract(client, rankings_files):
    loaded = _load(client)

    assert loaded["item_singular"] == "color"
    assert loaded["item_plural"] == "colors"
    assert loaded["rankings_path"] == str(
        rankings_files["swimmer_type_color_rankings"]
    )
    assert loaded["lookup_path"] == str(rankings_files["personality_colors"])
    assert [item["name"] for item in loaded["swimmer_types"][0]["items"]] == [
        "Blue",
        "Green",
    ]


def test_new_item_round_trips_with_assigned_lookup_id(client, rankings_files):
    loaded = _load(client)
    existing = loaded["swimmer_types"][0]["items"]
    new_item = {
        "client_key": "new-purple",
        "id": None,
        "name": "Purple",
        "is_new": True,
    }
    items = [
        {
            "client_key": item["client_key"],
            "id": item["id"],
            "name": item["name"],
            "is_new": False,
        }
        for item in existing
    ] + [new_item]
    order = ["new-purple", *(item["client_key"] for item in existing)]

    response = client.post(
        "/api/rankings_editor/save",
        json=_save_payload(loaded, items, order),
    )

    assert response.status_code == 200
    assert response.json()["lookup_updated"] is True
    with rankings_files["personality_colors"].open(encoding="utf-8") as handle:
        lookup_rows = list(csv.DictReader(handle))
    assert lookup_rows[-1] == {
        "color_id": "3",
        "color_name": "Purple",
        "traits": "",
    }
    with rankings_files["swimmer_type_color_rankings"].open(
        encoding="utf-8"
    ) as handle:
        ranking_rows = list(csv.DictReader(handle))
    assert [row for row in ranking_rows if row["color_id"] == "3"] == [
        {"swimmer_type_id": "1", "color_id": "3", "rank": "1"},
        {"swimmer_type_id": "2", "color_id": "3", "rank": "1"},
    ]

    reloaded = _load(client)
    purple = reloaded["swimmer_types"][0]["items"][0]
    assert purple["id"] == "3"
    assert purple["name"] == "Purple"


def test_deleted_item_stays_deleted_after_reload(client, rankings_files):
    loaded = _load(client)
    kept = loaded["swimmer_types"][0]["items"][0]
    items = [{
        "client_key": kept["client_key"],
        "id": kept["id"],
        "name": kept["name"],
        "is_new": False,
    }]

    response = client.post(
        "/api/rankings_editor/save",
        json=_save_payload(loaded, items, [kept["client_key"]]),
    )

    assert response.status_code == 200
    assert response.json()["lookup_updated"] is True
    reloaded = _load(client)
    assert reloaded["swimmer_types"][0]["items"] == [{
        "client_key": "existing-1",
        "id": "1",
        "name": "Blue",
        "rank": 1,
    }]


def test_save_rejects_incomplete_rankings_without_changing_files(
    client, rankings_files
):
    loaded = _load(client)
    items = loaded["swimmer_types"][0]["items"]
    before_lookup = rankings_files["personality_colors"].read_bytes()
    before_rankings = rankings_files["swimmer_type_color_rankings"].read_bytes()
    payload = _save_payload(
        loaded,
        items,
        [items[0]["client_key"]],
    )

    response = client.post("/api/rankings_editor/save", json=payload)

    assert response.status_code == 400
    assert "rank every item exactly once" in response.json()["error"]
    assert rankings_files["personality_colors"].read_bytes() == before_lookup
    assert rankings_files["swimmer_type_color_rankings"].read_bytes() == before_rankings
