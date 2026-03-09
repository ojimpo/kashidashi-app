const DEFAULT_STATE = Object.freeze({
  view: "table",
  timelineScale: "month",
  timelineDate: currentDateKey(),
  type: "",
  status: "",
  library: "",
  artist: "",
  author: "",
  sort: "borrowed_date_desc",
});

const VIEW_VALUES = new Set(["table", "tiles", "timeline"]);
const TIMELINE_SCALE_VALUES = new Set(["month", "week"]);
const TYPE_VALUES = new Set(["", "cd", "book", "dvd", "other"]);
const STATUS_VALUES = new Set(["", "not_ripped", "ripped", "not_returned", "returned"]);
const SORT_VALUES = new Set([
  "borrowed_date_desc",
  "borrowed_date_asc",
  "due_date_asc",
  "due_date_desc",
  "updated_at_desc",
]);

const state = {
  ...DEFAULT_STATE,
};

let items = [];
let editingItemId = null;
let returnTargetId = null;
let ripTargetId = null;

function currentDateKey() {
  return toDateKey(new Date());
}

function toDateKey(date) {
  return date.toISOString().slice(0, 10);
}

function normalizeChoice(value, allowedValues, fallback) {
  return allowedValues.has(value) ? value : fallback;
}

export function parseUrlState(search) {
  const params = new URLSearchParams(search.startsWith("?") ? search.slice(1) : search);
  return {
    view: normalizeChoice(params.get("view") || DEFAULT_STATE.view, VIEW_VALUES, DEFAULT_STATE.view),
    timelineScale: normalizeChoice(
      params.get("timelineScale") || DEFAULT_STATE.timelineScale,
      TIMELINE_SCALE_VALUES,
      DEFAULT_STATE.timelineScale,
    ),
    timelineDate: params.get("timelineDate") || DEFAULT_STATE.timelineDate,
    type: normalizeChoice(params.get("type") || "", TYPE_VALUES, ""),
    status: normalizeChoice(params.get("status") || "", STATUS_VALUES, ""),
    library: params.get("library") || "",
    artist: params.get("artist") || "",
    author: params.get("author") || "",
    sort: normalizeChoice(params.get("sort") || DEFAULT_STATE.sort, SORT_VALUES, DEFAULT_STATE.sort),
  };
}

export function buildUiSearch(nextState) {
  const params = new URLSearchParams();
  Object.entries(nextState).forEach(([key, value]) => {
    if (value && value !== DEFAULT_STATE[key]) {
      params.set(key, value);
    }
  });
  const query = params.toString();
  return query ? `?${query}` : "";
}

function buildApiSearch(nextState) {
  const params = new URLSearchParams();
  for (const key of ["type", "status", "library", "artist", "author", "sort"]) {
    if (nextState[key]) {
      params.set(key, nextState[key]);
    }
  }
  return params.toString();
}

function datePartsInJst(input) {
  const date = new Date(input);
  if (Number.isNaN(date.getTime())) {
    return null;
  }
  const formatter = new Intl.DateTimeFormat("sv-SE", {
    timeZone: "Asia/Tokyo",
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    hour12: false,
  });
  const parts = Object.fromEntries(formatter.formatToParts(date).map((part) => [part.type, part.value]));
  return {
    year: parts.year,
    month: parts.month,
    day: parts.day,
    hour: parts.hour,
    minute: parts.minute,
  };
}

export function formatDateTimeJst(value) {
  if (!value) {
    return "未記録";
  }
  const parts = datePartsInJst(value);
  if (!parts) {
    return "未記録";
  }
  return `${parts.year}-${parts.month}-${parts.day} ${parts.hour}:${parts.minute} JST`;
}

export function toJstDateKey(value) {
  if (!value) {
    return null;
  }
  const parts = datePartsInJst(value);
  if (!parts) {
    return null;
  }
  return `${parts.year}-${parts.month}-${parts.day}`;
}

export function toUtcIsoFromJstInput(value) {
  if (!value) {
    return null;
  }
  return new Date(`${value}:00+09:00`).toISOString().replace(".000Z", "Z");
}

export function toUtcIsoFromDateInput(value) {
  if (!value) {
    return null;
  }
  return `${value}T00:00:00Z`;
}

export function fromUtcToJstInputValue(value) {
  if (!value) {
    return "";
  }
  const parts = datePartsInJst(value);
  if (parts) {
    return `${parts.year}-${parts.month}-${parts.day}T${parts.hour}:${parts.minute}`;
  }

  // Fallback for non-ISO strings (defensive)
  const normalized = String(value).trim().replace(" ", "T");
  const m = normalized.match(/^(\d{4}-\d{2}-\d{2})T(\d{2}:\d{2})(?::\d{2})?(?:\.\d+)?(?:Z|[+-]\d{2}:?\d{2})?$/);
  if (m) {
    return `${m[1]}T${m[2]}`;
  }
  return "";
}

export function fromUtcToJstDateInputValue(value) {
  if (!value) {
    return "";
  }
  const parts = datePartsInJst(value);
  if (parts) {
    return `${parts.year}-${parts.month}-${parts.day}`;
  }
  return String(value).slice(0, 10);
}

export function placeholderForType(type) {
  const safeType = ["cd", "book", "dvd", "other"].includes(type) ? type : "other";
  return `/static/placeholders/${safeType}.svg`;
}

export function itemSupportsRip(item) {
  return item.type === "cd" && !item.returned_at;
}

function sanitizeIsbn(isbn) {
  if (!isbn) {
    return "";
  }
  return String(isbn).replaceAll(/[^0-9Xx]/g, "").toUpperCase();
}

function bookSearchQuery(item) {
  return [item.title, item.author].filter(Boolean).join(" ").trim();
}

export function bookLinksForItem(item) {
  if (item.type !== "book") {
    return null;
  }

  const isbn = sanitizeIsbn(item.isbn);
  if (isbn) {
    return {
      amazon: `https://www.amazon.co.jp/s?k=${encodeURIComponent(isbn)}`,
      bookmeter: `https://bookmeter.com/search?keyword=${encodeURIComponent(isbn)}`,
    };
  }

  const query = bookSearchQuery(item);
  if (!query) {
    return null;
  }
  return {
    amazon: `https://www.amazon.co.jp/s?k=${encodeURIComponent(query)}`,
    bookmeter: `https://bookmeter.com/search?keyword=${encodeURIComponent(query)}`,
  };
}

function bookLinksMarkup(item) {
  const links = bookLinksForItem(item);
  if (!links) {
    return "";
  }
  return `
    <div class="external-links" aria-label="外部リンク">
      <a class="external-link" href="${escapeAttribute(links.amazon)}" target="_blank" rel="noreferrer">Amazon</a>
      <a class="external-link" href="${escapeAttribute(links.bookmeter)}" target="_blank" rel="noreferrer">読書メーター</a>
    </div>
  `;
}

function formatDate(value) {
  return value || "未設定";
}

function dueDateLabel(item) {
  if (item.returned_at) {
    return "-";
  }
  return formatDate(item.due_date);
}

function creatorLabel(item) {
  if (item.type === "book") {
    return item.author || "著者未設定";
  }
  return item.artist || item.author || "作成者未設定";
}

function typeLabel(itemType) {
  return { cd: "CD", book: "本", dvd: "DVD", other: "その他" }[itemType] || "その他";
}

function returnBadge(item) {
  if (item.returned_at) {
    return '<span class="badge badge-returned">返却済</span>';
  }
  return '<span class="badge badge-active">貸出中</span>';
}

function ripBadge(item) {
  if (item.type !== "cd") {
    return '<span class="badge badge-pending">対象外</span>';
  }
  if (item.ripped_at) {
    return '<span class="badge badge-ripped">リッピング済</span>';
  }
  return '<span class="badge badge-pending">未リッピング</span>';
}

function showStatus(message, isError = false) {
  const node = document.getElementById("status-message");
  node.hidden = false;
  node.textContent = message;
  node.style.background = isError ? "rgba(191, 90, 42, 0.18)" : "rgba(69, 105, 184, 0.12)";
  node.style.color = isError ? "#7d2c0f" : "#29416d";
}

function clearStatus() {
  const node = document.getElementById("status-message");
  node.hidden = true;
  node.textContent = "";
}

function syncUrl() {
  const search = buildUiSearch(state);
  const nextUrl = `${window.location.pathname}${search}`;
  window.history.replaceState({}, "", nextUrl);
}

function applyStateToForm() {
  const form = document.getElementById("filters-form");
  for (const [key, value] of Object.entries(state)) {
    if (form.elements.namedItem(key)) {
      form.elements.namedItem(key).value = value;
    }
  }
  updateViewVisibility();
}

function updateViewVisibility() {
  document.getElementById("table-view").hidden = state.view !== "table";
  document.getElementById("tiles-view").hidden = state.view !== "tiles";
  document.getElementById("timeline-view").hidden = state.view !== "timeline";
  document.getElementById("timeline-controls-panel").hidden = state.view !== "timeline";
  document.querySelector(".timeline-only").hidden = state.view !== "timeline";
}

function updateSummary() {
  const activeCount = items.filter((item) => !item.returned_at).length;
  const returnedCount = items.filter((item) => Boolean(item.returned_at)).length;
  const rippedCount = items.filter((item) => item.type === "cd" && Boolean(item.ripped_at)).length;
  document.getElementById("count-total").textContent = String(items.length);
  document.getElementById("count-active").textContent = String(activeCount);
  document.getElementById("count-returned").textContent = String(returnedCount);
  document.getElementById("count-ripped").textContent = String(rippedCount);
}

function actionsMarkup(item) {
  const ripAction = itemSupportsRip(item)
    ? `<button class="button button-ghost" data-action="rip" data-id="${item.id}" type="button">リップ記録</button>`
    : "";
  const returnAction = !item.returned_at
    ? `<button class="button button-ghost" data-action="return" data-id="${item.id}" type="button">返却記録</button>`
    : "";
  return `
    <div class="item-actions">
      <button class="button button-ghost" data-action="edit" data-id="${item.id}" type="button">編集</button>
      ${returnAction}
      ${ripAction}
      <button class="button button-ghost" data-action="delete" data-id="${item.id}" type="button">削除</button>
    </div>
  `;
}

function renderTable() {
  const tbody = document.getElementById("table-body");
  if (!items.length) {
    tbody.innerHTML = '<tr><td colspan="9"><div class="empty-state">該当する資料がありません。</div></td></tr>';
    return;
  }
  tbody.innerHTML = items
    .map(
      (item) => `
        <tr>
          <td>
            <div class="item-title">${escapeHtml(item.title)}</div>
            ${bookLinksMarkup(item)}
            <div class="item-subline">${item.notes ? escapeHtml(item.notes) : "メモなし"}</div>
          </td>
          <td>${escapeHtml(creatorLabel(item))}</td>
          <td>${typeLabel(item.type)}</td>
          <td>${escapeHtml(item.library)}</td>
          <td>${formatDate(item.borrowed_date)}</td>
          <td>${dueDateLabel(item)}</td>
          <td>${returnBadge(item)}</td>
          <td>${ripBadge(item)}</td>
          <td>${actionsMarkup(item)}</td>
        </tr>
      `,
    )
    .join("");
}

function renderTiles() {
  const grid = document.getElementById("tiles-grid");
  if (!items.length) {
    grid.innerHTML = '<div class="empty-state">該当する資料がありません。</div>';
    return;
  }
  grid.innerHTML = items
    .map(
      (item) => `
        <article class="tile-card">
          <img class="tile-art" src="${escapeAttribute(item.image_url || placeholderForType(item.type))}" alt="${escapeAttribute(item.title)}">
          <div class="tile-meta">
            <strong>${escapeHtml(item.title)}</strong>
            ${bookLinksMarkup(item)}
            <p>${escapeHtml(creatorLabel(item))}</p>
            <p>${typeLabel(item.type)} / ${escapeHtml(item.library)}</p>
            <p>貸出 ${formatDate(item.borrowed_date)} / 返却期限 ${dueDateLabel(item)}</p>
            <p>返却: ${item.returned_at ? (toJstDateKey(item.returned_at) || formatDate(item.returned_at)) : "未返却"}</p>
            <p>リップ: ${item.ripped_at ? formatDateTimeJst(item.ripped_at) : "未記録"}</p>
          </div>
          ${actionsMarkup(item)}
        </article>
      `,
    )
    .join("");
}

function periodRange() {
  const anchor = new Date(`${state.timelineDate}T00:00:00Z`);
  if (Number.isNaN(anchor.getTime())) {
    return periodRangeFromDate(new Date(`${DEFAULT_STATE.timelineDate}T00:00:00Z`), state.timelineScale);
  }
  return periodRangeFromDate(anchor, state.timelineScale);
}

function periodRangeFromDate(anchor, scale) {
  if (scale === "week") {
    const day = (anchor.getUTCDay() + 6) % 7;
    const start = new Date(anchor);
    start.setUTCDate(anchor.getUTCDate() - day);
    const end = new Date(start);
    end.setUTCDate(start.getUTCDate() + 6);
    return { start, end, dayCount: 7 };
  }
  const start = new Date(Date.UTC(anchor.getUTCFullYear(), anchor.getUTCMonth(), 1));
  const end = new Date(Date.UTC(anchor.getUTCFullYear(), anchor.getUTCMonth() + 1, 0));
  const dayCount = end.getUTCDate();
  return { start, end, dayCount };
}

function shiftTimeline(step) {
  const anchor = new Date(`${state.timelineDate}T00:00:00Z`);
  if (state.timelineScale === "week") {
    anchor.setUTCDate(anchor.getUTCDate() + 7 * step);
  } else {
    anchor.setUTCMonth(anchor.getUTCMonth() + step);
  }
  state.timelineDate = toDateKey(anchor);
  applyStateToForm();
  syncUrl();
  renderTimeline();
}

function rangeLabel(start, end) {
  return `${toDateKey(start)} から ${toDateKey(end)}`;
}

function timelineEndDate(item) {
  return item.returned_at ? toJstDateKey(item.returned_at) : item.due_date;
}

function dateList(start, end) {
  const dates = [];
  const cursor = new Date(start);
  while (cursor <= end) {
    dates.push(toDateKey(cursor));
    cursor.setUTCDate(cursor.getUTCDate() + 1);
  }
  return dates;
}

function dayLabel(dateKey) {
  const date = new Date(`${dateKey}T00:00:00Z`);
  return {
    month: `${date.getUTCMonth() + 1}/${date.getUTCDate()}`,
    weekday: ["月", "火", "水", "木", "金", "土", "日"][(date.getUTCDay() + 6) % 7],
  };
}

function renderTimeline() {
  const node = document.getElementById("timeline-grid");
  const { start, end, dayCount } = periodRange();
  const dates = dateList(start, end);
  document.getElementById("timeline-range-label").textContent = rangeLabel(start, end);

  const visibleItems = items.filter((item) => {
    const itemStart = item.borrowed_date;
    const itemEnd = timelineEndDate(item);
    return itemEnd >= dates[0] && itemStart <= dates[dates.length - 1];
  });

  if (!visibleItems.length) {
    node.innerHTML = '<div class="empty-state">この期間に重なる資料はありません。</div>';
    return;
  }

  const headerClass = state.timelineScale === "week" ? "timeline-scale-week" : "timeline-scale-month";
  const headerMarkup = `
    <div class="timeline-header">
      <div class="timeline-header-meta">
        <strong>タイトル</strong>
      </div>
      <div class="timeline-scale ${headerClass}" style="--day-count: ${dayCount}">
        ${dates
          .map((dateKey) => {
            const label = dayLabel(dateKey);
            return `<div class="timeline-day"><strong>${label.month}</strong><span>${label.weekday}</span></div>`;
          })
          .join("")}
      </div>
    </div>
  `;

  const rows = visibleItems
    .map((item) => {
      const rawStartIndex = dates.indexOf(item.borrowed_date);
      const rawEndIndex = dates.indexOf(timelineEndDate(item));
      const startIndex = rawStartIndex === -1 ? 0 : rawStartIndex;
      const endIndex = rawEndIndex === -1 ? dates.length - 1 : rawEndIndex;
      const cellMarkup = dates.map(() => '<div class="timeline-lane-cell"></div>').join("");
      return `
        <div class="timeline-row">
          <div class="timeline-item-meta">
            <div class="item-title">${escapeHtml(item.title)}</div>
            <div class="item-subline">${escapeHtml(creatorLabel(item))}</div>
            <div class="item-subline">${typeLabel(item.type)} / 貸出 ${formatDate(item.borrowed_date)} / 期限 ${dueDateLabel(item)}</div>
            ${actionsMarkup(item)}
          </div>
          <div class="timeline-lane">
            <div class="timeline-lane-grid ${state.timelineScale}" style="--day-count: ${dayCount}">
              ${cellMarkup}
            </div>
            <div
              class="timeline-bar ${item.type}"
              style="left: calc(${(100 / dayCount) * startIndex}% + 10px); width: calc(${(100 / dayCount) * (endIndex - startIndex + 1)}% - 20px);"
            ></div>
          </div>
        </div>
      `;
    })
    .join("");

  node.innerHTML = headerMarkup + rows;
}

function toggleItemFormFields() {
  const type = document.getElementById("item-type-field").value;
  document.querySelectorAll("[data-group]").forEach((node) => {
    node.classList.add("hidden");
  });

  if (type === "book") {
    showGroups(["author", "book"]);
  } else if (type === "dvd") {
    showGroups(["artist", "dvd"]);
  } else if (type === "cd") {
    showGroups(["artist", "cd"]);
  } else {
    showGroups(["artist", "author"]);
  }
}

function showGroups(groups) {
  groups.forEach((groupName) => {
    document.querySelectorAll(`[data-group="${groupName}"]`).forEach((node) => {
      node.classList.remove("hidden");
    });
  });
}

function resetItemForm() {
  const form = document.getElementById("item-form");
  form.reset();
  form.elements.library.value = "葛飾区立中央図書館";
  form.elements.type.value = "cd";
  editingItemId = null;
  document.getElementById("item-dialog-title").textContent = "資料を登録";
  toggleItemFormFields();
}

function fillItemForm(item) {
  const form = document.getElementById("item-form");
  editingItemId = item.id;
  form.elements.type.value = item.type;
  form.elements.title.value = item.title;
  form.elements.artist.value = item.artist || "";
  form.elements.author.value = item.author || "";
  form.elements.library.value = item.library || "";
  form.elements.borrowed_date.value = item.borrowed_date || "";
  form.elements.due_date.value = item.due_date || "";
  form.elements.returned_at.value = fromUtcToJstDateInputValue(item.returned_at);
  form.elements.image_url.value = item.image_url || "";
  form.elements.isbn.value = item.isbn || "";
  form.elements.tmdb_id.value = item.tmdb_id || "";
  form.elements.ripped_at.value = fromUtcToJstInputValue(item.ripped_at);
  form.elements.musicbrainz_release_id.value = item.musicbrainz_release_id || "";
  form.elements.metadata_artist.value = item.metadata_artist || "";
  form.elements.metadata_album.value = item.metadata_album || "";
  form.elements.notes.value = item.notes || "";
  document.getElementById("item-dialog-title").textContent = "資料を編集";
  toggleItemFormFields();
}

function buildItemPayload(form) {
  const payload = {
    type: form.elements.type.value,
    title: form.elements.title.value.trim(),
    artist: form.elements.artist.value.trim() || null,
    author: form.elements.author.value.trim() || null,
    library: form.elements.library.value.trim() || null,
    borrowed_date: form.elements.borrowed_date.value,
    due_date: form.elements.due_date.value,
    returned_at: toUtcIsoFromDateInput(form.elements.returned_at.value),
    image_url: form.elements.image_url.value.trim() || null,
    isbn: form.elements.isbn.value.trim() || null,
    tmdb_id: form.elements.tmdb_id.value.trim() || null,
    ripped_at: toUtcIsoFromJstInput(form.elements.ripped_at.value),
    musicbrainz_release_id: form.elements.musicbrainz_release_id.value.trim() || null,
    metadata_artist: form.elements.metadata_artist.value.trim() || null,
    metadata_album: form.elements.metadata_album.value.trim() || null,
    notes: form.elements.notes.value.trim() || null,
  };
  if (!payload.library) {
    delete payload.library;
  }
  return payload;
}

function getItemById(itemId) {
  return items.find((item) => item.id === itemId);
}

async function loadItems() {
  clearStatus();
  syncUrl();
  const query = buildApiSearch(state);
  const response = await fetch(`/api/items${query ? `?${query}` : ""}`);
  if (!response.ok) {
    showStatus("一覧取得に失敗しました。", true);
    return;
  }
  items = await response.json();
  updateSummary();
  renderTable();
  renderTiles();
  renderTimeline();
}

async function submitJson(url, method, payload) {
  const response = await fetch(url, {
    method,
    headers: {
      "Content-Type": "application/json",
    },
    body: payload ? JSON.stringify(payload) : undefined,
  });
  if (response.status === 204) {
    return null;
  }
  const body = await response.json();
  if (!response.ok) {
    const detail = Array.isArray(body.detail) ? body.detail.join(" ") : body.detail || "処理に失敗しました。";
    throw new Error(detail);
  }
  return body;
}

async function saveItem(event) {
  event.preventDefault();
  const form = event.currentTarget;
  const payload = buildItemPayload(form);
  try {
    const url = editingItemId ? `/api/items/${editingItemId}` : "/api/items";
    const method = editingItemId ? "PATCH" : "POST";
    await submitJson(url, method, payload);
    document.getElementById("item-dialog").close();
    await loadItems();
  } catch (error) {
    showStatus(error.message, true);
  }
}

async function saveReturn(event) {
  event.preventDefault();
  try {
    await submitJson(`/api/items/${returnTargetId}`, "PATCH", {
      returned_at: toUtcIsoFromDateInput(event.currentTarget.elements.returned_at.value),
    });
    document.getElementById("returned-dialog").close();
    await loadItems();
  } catch (error) {
    showStatus(error.message, true);
  }
}

async function saveRip(event) {
  event.preventDefault();
  const elements = event.currentTarget.elements;
  try {
    await submitJson(`/api/items/${ripTargetId}`, "PATCH", {
      ripped_at: toUtcIsoFromJstInput(elements.ripped_at.value),
      musicbrainz_release_id: elements.musicbrainz_release_id.value.trim() || null,
      metadata_artist: elements.metadata_artist.value.trim() || null,
      metadata_album: elements.metadata_album.value.trim() || null,
    });
    document.getElementById("ripped-dialog").close();
    await loadItems();
  } catch (error) {
    showStatus(error.message, true);
  }
}

function openItemDialog(itemId = null) {
  resetItemForm();
  if (itemId !== null) {
    const item = getItemById(itemId);
    if (item) {
      fillItemForm(item);
    }
  }
  document.getElementById("item-dialog").showModal();
}

function openReturnDialog(itemId) {
  returnTargetId = itemId;
  const item = getItemById(itemId);
  const form = document.getElementById("returned-form");
  form.reset();
  form.elements.returned_at.value = fromUtcToJstDateInputValue(item?.returned_at) || toDateKey(new Date());
  document.getElementById("returned-dialog").showModal();
}

function openRipDialog(itemId) {
  ripTargetId = itemId;
  const item = getItemById(itemId);
  const form = document.getElementById("ripped-form");
  form.reset();
  form.elements.ripped_at.value = fromUtcToJstInputValue(item?.ripped_at) || fromUtcToJstInputValue(new Date().toISOString());
  form.elements.musicbrainz_release_id.value = item?.musicbrainz_release_id || "";
  form.elements.metadata_artist.value = item?.metadata_artist || "";
  form.elements.metadata_album.value = item?.metadata_album || "";
  document.getElementById("ripped-dialog").showModal();
}

async function deleteItemById(itemId) {
  if (!window.confirm("この資料を削除しますか？")) {
    return;
  }
  try {
    await submitJson(`/api/items/${itemId}`, "DELETE");
    await loadItems();
  } catch (error) {
    showStatus(error.message, true);
  }
}

function handleActionClick(event) {
  const button = event.target.closest("[data-action]");
  if (!button) {
    return;
  }
  const itemId = Number(button.dataset.id);
  if (button.dataset.action === "edit") {
    openItemDialog(itemId);
  } else if (button.dataset.action === "return") {
    openReturnDialog(itemId);
  } else if (button.dataset.action === "rip") {
    openRipDialog(itemId);
  } else if (button.dataset.action === "delete") {
    void deleteItemById(itemId);
  }
}

function escapeHtml(value) {
  return String(value)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#39;");
}

function escapeAttribute(value) {
  return escapeHtml(value);
}

function bindEvents() {
  document.getElementById("filters-form").addEventListener("submit", async (event) => {
    event.preventDefault();
    const form = event.currentTarget;
    for (const key of Object.keys(DEFAULT_STATE)) {
      if (form.elements.namedItem(key)) {
        state[key] = form.elements.namedItem(key).value;
      }
    }
    if (state.view !== "timeline") {
      state.timelineDate = DEFAULT_STATE.timelineDate;
    }
    updateViewVisibility();
    await loadItems();
  });

  document.getElementById("view-select").addEventListener("change", async (event) => {
    state.view = event.currentTarget.value;
    if (state.view === "timeline" && !state.timelineDate) {
      state.timelineDate = currentDateKey();
    }
    updateViewVisibility();
    await loadItems();
  });

  document.getElementById("timeline-scale-select").addEventListener("change", async (event) => {
    state.timelineScale = event.currentTarget.value;
    await loadItems();
  });

  document.getElementById("timeline-prev").addEventListener("click", () => shiftTimeline(-1));
  document.getElementById("timeline-next").addEventListener("click", () => shiftTimeline(1));

  document.getElementById("reset-filters-button").addEventListener("click", async () => {
    Object.assign(state, DEFAULT_STATE);
    applyStateToForm();
    await loadItems();
  });

  document.getElementById("new-item-button").addEventListener("click", () => openItemDialog());
  document.getElementById("item-type-field").addEventListener("change", toggleItemFormFields);
  document.getElementById("item-form").addEventListener("submit", (event) => {
    void saveItem(event);
  });
  document.getElementById("returned-form").addEventListener("submit", (event) => {
    void saveReturn(event);
  });
  document.getElementById("ripped-form").addEventListener("submit", (event) => {
    void saveRip(event);
  });

  document.querySelectorAll("[data-close-dialog]").forEach((button) => {
    button.addEventListener("click", () => {
      document.getElementById(button.dataset.closeDialog).close();
    });
  });

  document.getElementById("table-view").addEventListener("click", handleActionClick);
  document.getElementById("tiles-view").addEventListener("click", handleActionClick);
  document.getElementById("timeline-view").addEventListener("click", handleActionClick);
}

async function init() {
  Object.assign(state, parseUrlState(window.location.search));
  applyStateToForm();
  bindEvents();
  await loadItems();
}

if (typeof window !== "undefined" && typeof document !== "undefined") {
  window.addEventListener("DOMContentLoaded", () => {
    void init();
  });
}
