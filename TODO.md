# Project TODOs

This file tracks identified improvements, code review findings, and pending maintenance tasks.

---

## Code Review Findings (from Subagent Review on branch `feat/habit-metadata-cleanup`)

### 1. Reset Pinned Focus Banner on Week Navigation
- **File:** [static/app.js:34-38](static/app.js#L34-L38)
- **Problem:** In `renderToolbarAndBanner()`, `bannerEl.textContent` only updates when `customText` is non-empty (`if (customText) { bannerEl.textContent = customText; }`). When navigating from a week with a saved review adjustment to an unreviewed week, `customText` is empty, leaving the prior week's adjustment stuck in the banner.
- **Fix:** Explicitly assign the default focus text whenever `customText` is empty:
  ```javascript
  const defaultFocus = "Review weekly, not obsessively every day. Choose 1 system adjustment in your Weekly Review.";
  bannerEl.textContent = customText || defaultFocus;
  ```

### 2. Enforce Linked Identities on Habit Import
- **File:** [app.py:1387-1389](app.py#L1387-L1389)
- **Problem:** `create_habit()` enforces at least one linked identity (`if not identity_ids: raise ValueError(...)`), but `import_database_from_dict()` allows habits with an empty or missing `identity_ids` list to be inserted. Orphan habits never render on the dashboard and are deleted automatically during identity deletion.
- **Fix:** Validate that each imported habit contains at least one linked identity:
  ```python
  linked_ids = list(h.get("identity_ids") or [])
  if not linked_ids:
      raise ValueError(f"Habit '{raw_title}' must be linked to at least one identity.")
  ```

### 3. Add Optional Chaining in Identity Modal Initialization
- **File:** [static/app.js:917-918](static/app.js#L917-L918)
- **Problem:** `openIdentityModal()` accesses `state.data.identities.length`. If a user clicks `+ New Identity` while `loadState()` is in flight or failed, `state.data` is `null`, throwing an unhandled `TypeError`.
- **Fix:** Guard with optional chaining:
  ```javascript
  const identities = state.data?.identities || [];
  const slots = state.data?.palette_slots || [{ light: "#2a78d6", dark: "#3987e5" }];
  const nextSlot = slots[identities.length % slots.length];
  ```

### 4. Handle Explicit `null` in `sort_order` During Import
- **File:** [app.py:1334, 1378](app.py#L1334)
- **Problem:** If an imported JSON object contains `"sort_order": null`, `dict.get("sort_order", idx)` returns `None`, causing `int(None)` to raise an unhandled `TypeError`.
- **Fix:** Apply an `or` fallback before `int()` casting:
  ```python
  "sort_order": int(ident.get("sort_order") or idx)
  ```
  and for habits:
  ```python
  "sort_order": int(h.get("sort_order") or idx)
  ```

### 5. Restore Configured Database Path in Test Fixture TearDown
- **File:** [tests/test_app.py:34](tests/test_app.py#L34)
- **Problem:** In `tearDown()`, `app.DEFAULT_DB_PATH` is reset to `(app.ROOT_DIR / "data" / "identity_os.db").resolve()`, which can override custom paths configured in `.env`.
- **Fix:** Capture `self.old_default_db = app.DEFAULT_DB_PATH` in `setUp()` and restore `app.DEFAULT_DB_PATH = self.old_default_db` in `tearDown()`.
