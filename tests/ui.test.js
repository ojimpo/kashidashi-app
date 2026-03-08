import test from "node:test";
import assert from "node:assert/strict";

import {
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
