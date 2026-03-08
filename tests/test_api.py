from __future__ import annotations

from datetime import datetime, timezone


def make_item(**overrides: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "type": "cd",
        "title": "Future Listening",
        "artist": "The Librarians",
        "borrowed_date": "2026-03-01",
        "due_date": "2026-03-15",
        "image_url": "https://example.com/cd.jpg",
    }
    payload.update(overrides)
    return payload


def create_sample(client, **overrides: object) -> dict[str, object]:
    response = client.post("/api/items", json=make_item(**overrides))
    assert response.status_code == 201, response.text
    return response.json()


def test_create_item_defaults_library_and_fetch_detail(client) -> None:
    created = create_sample(client)

    assert created["library"] == "葛飾区立中央図書館"
    assert created["created_at"].endswith("Z")
    assert created["updated_at"].endswith("Z")

    detail = client.get(f"/api/items/{created['id']}")
    assert detail.status_code == 200
    assert detail.json()["title"] == "Future Listening"


def test_duplicate_create_returns_conflict(client) -> None:
    create_sample(client)
    duplicate = client.post("/api/items", json=make_item(title="future listening", artist="the librarians"))

    assert duplicate.status_code == 409
    assert duplicate.json()["detail"] == "同一資料がすでに登録されています。"


def test_patch_item_updates_and_clears_nullable_fields(client) -> None:
    created = create_sample(client, notes="first note")
    response = client.patch(
        f"/api/items/{created['id']}",
        json={
            "notes": None,
            "image_url": None,
            "returned_at": "2026-03-10T03:00:00Z",
        },
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["notes"] is None
    assert body["image_url"] is None
    assert body["returned_at"] == "2026-03-10T03:00:00Z"


def test_delete_item_returns_204_and_removes_record(client) -> None:
    created = create_sample(client)

    deleted = client.delete(f"/api/items/{created['id']}")
    assert deleted.status_code == 204

    missing = client.get(f"/api/items/{created['id']}")
    assert missing.status_code == 404


def test_missing_item_returns_404(client) -> None:
    response = client.get("/api/items/999")
    assert response.status_code == 404


def test_book_requires_author(client) -> None:
    response = client.post(
        "/api/items",
        json=make_item(type="book", artist=None, title="Book Title", due_date="2026-03-12"),
    )

    assert response.status_code == 422
    assert "author" in " ".join(response.json()["detail"])


def test_cd_requires_artist(client) -> None:
    response = client.post("/api/items", json=make_item(artist=None))
    assert response.status_code == 422
    assert "artist" in " ".join(response.json()["detail"])


def test_filters_and_sorting(client) -> None:
    create_sample(client, title="Gamma", borrowed_date="2026-03-03", due_date="2026-03-20")
    create_sample(
        client,
        type="dvd",
        title="Movie Night",
        artist="Director X",
        borrowed_date="2026-03-02",
        due_date="2026-03-11",
        tmdb_id="500",
        image_url=None,
    )
    create_sample(
        client,
        type="book",
        title="Library Architecture",
        artist=None,
        author="MURAKAMI",
        borrowed_date="2026-03-01",
        due_date="2026-03-18",
        isbn="9781234567890",
        image_url=None,
    )
    ripped_item = create_sample(
        client,
        title="Ripped Disc",
        borrowed_date="2026-03-04",
        due_date="2026-03-12",
        ripped_at="2026-03-05T00:00:00Z",
        metadata_artist="Meta Artist",
        metadata_album="Meta Album",
        musicbrainz_release_id="mbid-1",
    )
    returned_book = client.patch(
        f"/api/items/{ripped_item['id']}",
        json={"returned_at": "2026-03-07T00:00:00Z"},
    )
    assert returned_book.status_code == 200

    not_ripped = client.get("/api/items", params={"status": "not_ripped", "type": "cd"})
    assert not_ripped.status_code == 200
    assert {item["title"] for item in not_ripped.json()} == {"Gamma"}

    not_returned = client.get("/api/items", params={"status": "not_returned"})
    assert {item["title"] for item in not_returned.json()} == {
        "Gamma",
        "Movie Night",
        "Library Architecture",
    }

    returned = client.get("/api/items", params={"status": "returned"})
    assert {item["title"] for item in returned.json()} == {"Ripped Disc"}

    artist_match = client.get("/api/items", params={"artist": "director"})
    assert [item["title"] for item in artist_match.json()] == ["Movie Night"]

    author_match = client.get("/api/items", params={"author": "muraka"})
    assert [item["title"] for item in author_match.json()] == ["Library Architecture"]

    library_match = client.get("/api/items", params={"library": "葛飾区立中央図書館"})
    assert len(library_match.json()) == 4

    due_date_sorted = client.get("/api/items", params={"sort": "due_date_asc"})
    assert [item["title"] for item in due_date_sorted.json()] == [
        "Movie Night",
        "Ripped Disc",
        "Library Architecture",
        "Gamma",
    ]


def test_updated_at_sort_prefers_recently_changed_item(client) -> None:
    first = create_sample(client, title="First")
    second = create_sample(client, title="Second", borrowed_date="2026-03-03", due_date="2026-03-16")

    response = client.patch(
        f"/api/items/{first['id']}",
        json={"notes": "updated at " + datetime.now(timezone.utc).isoformat()},
    )
    assert response.status_code == 200

    sorted_items = client.get("/api/items", params={"sort": "updated_at_desc"})
    assert [item["title"] for item in sorted_items.json()[:2]] == ["First", "Second"]
