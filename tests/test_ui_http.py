from __future__ import annotations


def test_index_page_contains_view_switches(client) -> None:
    response = client.get("/")

    assert response.status_code == 200
    assert 'value="table"' in response.text
    assert 'value="tiles"' in response.text
    assert 'value="timeline"' in response.text
    assert '/static/app.js' in response.text


def test_static_assets_are_served(client) -> None:
    for path in (
        "/static/styles.css",
        "/static/app.js",
        "/static/placeholders/cd.svg",
        "/static/placeholders/book.svg",
        "/static/placeholders/dvd.svg",
        "/static/placeholders/other.svg",
    ):
        response = client.get(path)
        assert response.status_code == 200, path

