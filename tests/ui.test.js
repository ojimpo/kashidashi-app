import test from "node:test";
import assert from "node:assert/strict";

import {
  bookLinksForItem,
  buildUiSearch,
  formatDateTimeJst,
  itemSupportsRip,
  parseUrlState,
  placeholderForType,
  toUtcIsoFromJstInput,
} from "../app/static/app.js";

test("parseUrlState keeps view and filter query parameters", () => {
  const state = parseUrlState(
    "?view=timeline&timelineScale=week&timelineDate=2026-03-10&type=cd&status=not_ripped&artist=spitz&sort=due_date_asc",
  );

  assert.equal(state.view, "timeline");
  assert.equal(state.timelineScale, "week");
  assert.equal(state.timelineDate, "2026-03-10");
  assert.equal(state.type, "cd");
  assert.equal(state.status, "not_ripped");
  assert.equal(state.artist, "spitz");
  assert.equal(state.sort, "due_date_asc");
  assert.match(buildUiSearch(state), /view=timeline/);
});

test("JST input is converted to UTC ISO string", () => {
  assert.equal(toUtcIsoFromJstInput("2026-03-10T12:00"), "2026-03-10T03:00:00Z");
});

test("JST formatter renders a stable JST label", () => {
  assert.equal(formatDateTimeJst("2026-03-10T03:00:00Z"), "2026-03-10 12:00 JST");
});

test("placeholder path matches item type", () => {
  assert.equal(placeholderForType("cd"), "/static/placeholders/cd.svg");
  assert.equal(placeholderForType("other"), "/static/placeholders/other.svg");
});

test("rip action is limited to active CDs", () => {
  assert.equal(itemSupportsRip({ type: "cd", returned_at: null }), true);
  assert.equal(itemSupportsRip({ type: "cd", returned_at: "2026-03-10T03:00:00Z" }), false);
  assert.equal(itemSupportsRip({ type: "book", returned_at: null }), false);
});

test("book links prefer isbn when present", () => {
  const links = bookLinksForItem({
    type: "book",
    title: "Library Architecture",
    author: "村上春樹",
    isbn: "978-4-1234-5678-9",
  });

  assert.deepEqual(links, {
    amazon: "https://www.amazon.co.jp/s?k=9784123456789",
    bookmeter: "https://bookmeter.com/search?keyword=9784123456789",
  });
});

test("book links fall back to title and author search", () => {
  const links = bookLinksForItem({
    type: "book",
    title: "Library Architecture",
    author: "村上春樹",
    isbn: null,
  });

  assert.deepEqual(links, {
    amazon: "https://www.amazon.co.jp/s?k=Library%20Architecture%20%E6%9D%91%E4%B8%8A%E6%98%A5%E6%A8%B9",
    bookmeter:
      "https://bookmeter.com/search?keyword=Library%20Architecture%20%E6%9D%91%E4%B8%8A%E6%98%A5%E6%A8%B9",
  });
});

test("book links can search by title alone and are skipped for non-books", () => {
  assert.deepEqual(
    bookLinksForItem({
      type: "book",
      title: "Library Architecture",
      author: "",
      isbn: null,
    }),
    {
      amazon: "https://www.amazon.co.jp/s?k=Library%20Architecture",
      bookmeter: "https://bookmeter.com/search?keyword=Library%20Architecture",
    },
  );
  assert.equal(
    bookLinksForItem({
      type: "cd",
      title: "Future Listening",
      author: null,
      isbn: "9784123456789",
    }),
    null,
  );
});
