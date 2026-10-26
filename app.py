#!/usr/bin/env python3
"""
Identity Building OS — Extendable Standalone Backend
Based on Atomic Habits by James Clear.

Zero hardcoded identities or habits:
- Dynamically parses `base_database.md` (or any Markdown template) on initial bootstrap.
- Provides full CRUD APIs for Identities, Habits, Anti-Identity Guardrails,
  Daily Actions (Votes, Devotes & Obstacles), Weekly Reviews, and Markdown Guidance files.
- Stores full timestamps with day, month, year, hour, minute, and second in SQLite.
"""

from __future__ import annotations

import contextlib
import datetime as dt
import json
import mimetypes
import os
import re
import sqlite3
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

ROOT_DIR = Path(__file__).resolve().parent
DEFAULT_DB_PATH = ROOT_DIR / "data" / "identity_os.db"
BASE_MARKDOWN_PATH = ROOT_DIR / "base_database.md"
GUIDANCE_DIR = ROOT_DIR / "guidance"
STATIC_DIR = ROOT_DIR / "static"

# Validated categorical palette slots (from dataviz reference palette: light & dark pairs)
PALETTE_SLOTS = [
    {"light": "#2a78d6", "dark": "#3987e5"},  # Slot 1: Blue
    {"light": "#eb6834", "dark": "#d95926"},  # Slot 2: Orange
    {"light": "#1baf7a", "dark": "#199e70"},  # Slot 3: Aqua
    {"light": "#eda100", "dark": "#c98500"},  # Slot 4: Yellow
    {"light": "#e87ba4", "dark": "#d55181"},  # Slot 5: Magenta
    {"light": "#008300", "dark": "#008300"},  # Slot 6: Green
    {"light": "#6250d6", "dark": "#9085e9"},  # Slot 7: Violet
    {"light": "#e34948", "dark": "#e66767"},  # Slot 8: Red
]


def slugify(text: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "_", text.strip().lower()).strip("_")
    return slug or f"item_{int(dt.datetime.now().timestamp() * 1000)}"


def get_monday(date_str: str | None = None) -> dt.date:
    """Return the Monday date of the ISO week containing date_str (or today)."""
    if date_str:
        clean_date = date_str.strip()[:10]
        target = dt.date.fromisoformat(clean_date)
    else:
        target = dt.date.today()
    return target - dt.timedelta(days=target.weekday())


def build_timestamp_fields(
    action_date_str: str | None = None,
    now_dt: dt.datetime | None = None,
) -> dict[str, Any]:
    """
    Build complete timestamp metadata with day, month, year, hour, minute, and second.
    If action_date_str is provided (YYYY-MM-DD), combines that date with the current
    (or provided) hour, minute, and second.
    """
    now = now_dt or dt.datetime.now()
    if action_date_str:
        try:
            d_part = dt.date.fromisoformat(action_date_str.strip()[:10])
        except ValueError:
            d_part = now.date()
    else:
        d_part = now.date()

    combined = dt.datetime(
        d_part.year,
        d_part.month,
        d_part.day,
        now.hour,
        now.minute,
        now.second,
    )
    return {
        "action_date": combined.strftime("%Y-%m-%d"),
        "action_time": combined.strftime("%H:%M:%S"),
        "created_at": combined.strftime("%d/%m/%Y %H:%M:%S"),
        "day": combined.day,
        "month": combined.month,
        "year": combined.year,
        "hour": combined.hour,
        "minute": combined.minute,
        "second": combined.second,
    }


@contextlib.contextmanager
def connect_db(db_path: Path = DEFAULT_DB_PATH):
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    try:
        with conn:
            yield conn
    finally:
        conn.close()


def derive_two_minute_starter(habit_title: str) -> str:
    """Generate a sensible default 2-Minute Rule starter from a habit description."""
    cleaned = re.sub(r"^I\s+", "", habit_title.strip(), flags=re.IGNORECASE).rstrip(".")
    return f"Spend 2 minutes starting: {cleaned[:1].lower() + cleaned[1:]}"


def parse_base_markdown(md_path: Path = BASE_MARKDOWN_PATH) -> dict[str, Any]:
    """
    Dynamically parse an Identity Building Markdown file (like base_database.md)
    into structured identities, habits, anti-identities, stages, reflection prompts,
    and example actions—without hardcoding domain content in code.
    """
    if not md_path.exists():
        return {
            "identities": [],
            "habits": [],
            "anti_identities": [],
            "anti_principle": "",
            "examples": [],
            "reflection_questions": [],
            "stages": [],
            "system_checks": [],
        }

    lines = md_path.read_text(encoding="utf-8").splitlines()
    section = ""
    subsection = ""

    identities: list[dict[str, Any]] = []
    habits: list[dict[str, Any]] = []
    anti_identities: list[dict[str, Any]] = []
    anti_principle = ""
    examples: list[dict[str, str]] = []
    reflection_questions: list[str] = []
    stages: list[dict[str, str]] = []
    system_checks: list[dict[str, str]] = []

    current_identity_id: str | None = None

    for raw_line in lines:
        line = raw_line.strip()
        if not line:
            continue

        if line.startswith("## "):
            section = line[3:].strip().lower()
            subsection = ""
            current_identity_id = None
            continue

        if line.startswith("### "):
            subsection = line[4:].strip()
            if "desired identity" in section:
                ident_id = slugify(subsection)
                slot_idx = len(identities) % len(PALETTE_SLOTS)
                palette = PALETTE_SLOTS[slot_idx]
                lower_name = subsection.lower()
                domain = (
                    "leisure"
                    if any(w in lower_name for w in ("balance", "rest", "health", "play"))
                    else "growth"
                    if any(w in lower_name for w in ("read", "social", "creator", "learn"))
                    else "work"
                )
                identities.append(
                    {
                        "id": ident_id,
                        "name": subsection,
                        "tagline": f"Votes supporting {subsection}",
                        "domain": domain,
                        "color_light": palette["light"],
                        "color_dark": palette["dark"],
                        "current_stage": "Building evidence",
                        "sort_order": len(identities) + 1,
                    }
                )
                current_identity_id = ident_id
            continue

        checkbox_match = re.match(r"^-\s*\[\s*[xX ]?\s*\]\s*(.+)$", line)
        if checkbox_match:
            item_text = checkbox_match.group(1).strip()

            if "desired identity" in section and current_identity_id:
                cadence = "daily"
                if re.match(r"^(WEAKLY|WEEKLY)\b", item_text, flags=re.IGNORECASE):
                    cadence = "weekly"
                    item_text = re.sub(r"^(WEAKLY|WEEKLY)\s+", "", item_text, flags=re.IGNORECASE).strip()

                habits.append(
                    {
                        "id": f"habit_{len(habits) + 1}_{slugify(item_text)[:24]}",
                        "title": item_text,
                        "cadence": cadence,
                        "two_minute_version": derive_two_minute_starter(item_text),
                        "category": "identity_habit",
                        "identity_ids": [current_identity_id],
                        "sort_order": len(habits) + 1,
                    }
                )
            elif "anti-identity" in section:
                anti_identities.append(
                    {
                        "id": f"guard_{len(anti_identities) + 1}_{slugify(item_text)[:24]}",
                        "title": item_text,
                        "cadence": "daily",
                        "two_minute_version": f"2-minute environment reset: {item_text}",
                        "category": "anti_identity_guard",
                        "identity_ids": [],
                        "sort_order": 100 + len(anti_identities) + 1,
                    }
                )
            elif "weekly review" in section:
                system_checks.append(
                    {
                        "id": slugify(item_text)[:40],
                        "group": subsection or "Review",
                        "label": item_text,
                    }
                )
            elif "final evaluation" in section:
                stage_match = re.match(r"^\*\*(.+?):\*\*\s*(.+)$", item_text)
                if stage_match:
                    stages.append(
                        {
                            "name": stage_match.group(1).strip(),
                            "description": stage_match.group(2).strip(),
                        }
                    )
            continue

        if "anti-identity" in section and line.lower().startswith("**principle:**"):
            anti_principle = re.sub(r"^\*\*principle:\*\*\s*", "", line, flags=re.IGNORECASE).strip()
            continue

        if "evidence log" in section and line.startswith("- ") and ("→" in line or "->" in line):
            parts = re.split(r"→|->", line[2:].strip(), maxsplit=1)
            if len(parts) == 2:
                examples.append(
                    {
                        "title": parts[0].strip(),
                        "identity_hint": parts[1].strip(),
                    }
                )
            continue

        if "weekly review" in section and subsection.lower() == "reflection":
            q_match = re.match(r"^\*\*(.+\?)\*\*$", line)
            if q_match:
                reflection_questions.append(q_match.group(1).strip())

    fallback_ids = [
        i["id"]
        for i in identities
        if any(k in i["name"].lower() for k in ("balanced", "disciplined"))
    ] or ([identities[0]["id"]] if identities else [])

    for guard in anti_identities:
        guard["identity_ids"] = list(fallback_ids)

    return {
        "identities": identities,
        "habits": habits + anti_identities,
        "anti_principle": anti_principle,
        "examples": examples,
        "reflection_questions": reflection_questions,
        "stages": stages,
        "system_checks": system_checks,
    }


def _ensure_action_time_columns(conn: sqlite3.Connection) -> None:
    """Ensure existing databases have explicit day, month, year, hour, minute, second columns."""
    cols = {r["name"] for r in conn.execute("PRAGMA table_info(actions)").fetchall()}
    needed = [
        ("action_time", "TEXT NOT NULL DEFAULT '00:00:00'"),
        ("day", "INTEGER NOT NULL DEFAULT 1"),
        ("month", "INTEGER NOT NULL DEFAULT 1"),
        ("year", "INTEGER NOT NULL DEFAULT 2026"),
        ("hour", "INTEGER NOT NULL DEFAULT 0"),
        ("minute", "INTEGER NOT NULL DEFAULT 0"),
        ("second", "INTEGER NOT NULL DEFAULT 0"),
    ]
    for col_name, col_def in needed:
        if col_name not in cols:
            conn.execute(f"ALTER TABLE actions ADD COLUMN {col_name} {col_def}")


def init_db(
    db_path: Path = DEFAULT_DB_PATH,
    md_path: Path = BASE_MARKDOWN_PATH,
    seed_examples: bool = True,
) -> None:
    """Initialize SQLite schema and bootstrap dynamically from base_database.md if empty."""
    parsed = parse_base_markdown(md_path)

    with connect_db(db_path) as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS settings (
                key TEXT PRIMARY KEY,
                value_json TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS identities (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                tagline TEXT NOT NULL DEFAULT '',
                domain TEXT NOT NULL DEFAULT 'general',
                color_light TEXT NOT NULL,
                color_dark TEXT NOT NULL,
                current_stage TEXT NOT NULL DEFAULT 'Building evidence',
                sort_order INTEGER NOT NULL DEFAULT 1,
                archived INTEGER NOT NULL DEFAULT 0
            );

            CREATE TABLE IF NOT EXISTS habits (
                id TEXT PRIMARY KEY,
                title TEXT NOT NULL,
                cadence TEXT NOT NULL DEFAULT 'daily',
                two_minute_version TEXT NOT NULL DEFAULT '',
                category TEXT NOT NULL DEFAULT 'identity_habit',
                sort_order INTEGER NOT NULL DEFAULT 1,
                active INTEGER NOT NULL DEFAULT 1
            );

            CREATE TABLE IF NOT EXISTS habit_identities (
                habit_id TEXT NOT NULL REFERENCES habits(id) ON DELETE CASCADE,
                identity_id TEXT NOT NULL REFERENCES identities(id) ON DELETE CASCADE,
                PRIMARY KEY (habit_id, identity_id)
            );

            CREATE TABLE IF NOT EXISTS actions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                action_date TEXT NOT NULL,
                action_time TEXT NOT NULL DEFAULT '00:00:00',
                created_at TEXT NOT NULL,
                day INTEGER NOT NULL DEFAULT 1,
                month INTEGER NOT NULL DEFAULT 1,
                year INTEGER NOT NULL DEFAULT 2026,
                hour INTEGER NOT NULL DEFAULT 0,
                minute INTEGER NOT NULL DEFAULT 0,
                second INTEGER NOT NULL DEFAULT 0,
                title TEXT NOT NULL,
                evidence_note TEXT NOT NULL DEFAULT '',
                habit_id TEXT REFERENCES habits(id) ON DELETE SET NULL,
                kind TEXT NOT NULL DEFAULT 'vote',
                used_two_minute_rule INTEGER NOT NULL DEFAULT 0
            );

            CREATE TABLE IF NOT EXISTS action_identities (
                action_id INTEGER NOT NULL REFERENCES actions(id) ON DELETE CASCADE,
                identity_id TEXT NOT NULL REFERENCES identities(id) ON DELETE CASCADE,
                PRIMARY KEY (action_id, identity_id)
            );

            CREATE TABLE IF NOT EXISTS weekly_reviews (
                week_start TEXT PRIMARY KEY,
                review_date TEXT NOT NULL,
                answers_json TEXT NOT NULL DEFAULT '{}',
                one_adjustment TEXT NOT NULL DEFAULT '',
                strongest_evidence TEXT NOT NULL DEFAULT '',
                next_smallest_action TEXT NOT NULL DEFAULT '',
                overall_stage TEXT NOT NULL DEFAULT 'Building evidence',
                system_checks_json TEXT NOT NULL DEFAULT '{}'
            );
            """
        )
        _ensure_action_time_columns(conn)

        existing_settings = conn.execute("SELECT COUNT(*) FROM settings").fetchone()[0]
        if existing_settings == 0:
            default_stages = parsed["stages"] or [
                {"name": "Planning only", "description": "Defined the identity but have little behavioral evidence."},
                {"name": "Experimenting", "description": "Started performing the behaviors, consistency developing."},
                {"name": "Building evidence", "description": "Repeatedly performed relevant behaviors as part of routine."},
                {"name": "Becoming consistent", "description": "Behaviors are increasingly natural and resilient."},
                {"name": "Maintaining identity", "description": "Sustain behaviors while adapting to changing circumstances."},
            ]
            default_questions = parsed["reflection_questions"] or [
                "What identity did my actions support this week?",
                "Where did my behavior contradict my desired identity?",
                "What made good habits easier or harder?",
                "What is one adjustment I will make next week?",
            ]
            default_principle = (
                parsed["anti_principle"]
                or "I am not trying to eliminate fun. I am choosing how fun fits into my life."
            )
            default_checks = parsed["system_checks"] or []

            for k, val in [
                ("stages", default_stages),
                ("reflection_questions", default_questions),
                ("anti_principle", default_principle),
                ("system_checks", default_checks),
            ]:
                conn.execute(
                    "INSERT OR IGNORE INTO settings (key, value_json) VALUES (?, ?)",
                    (k, json.dumps(val)),
                )

        existing_identities = conn.execute("SELECT COUNT(*) FROM identities").fetchone()[0]
        if existing_identities == 0 and parsed["identities"]:
            for item in parsed["identities"]:
                conn.execute(
                    """
                    INSERT INTO identities (id, name, tagline, domain, color_light, color_dark, current_stage, sort_order)
                    VALUES (:id, :name, :tagline, :domain, :color_light, :color_dark, :current_stage, :sort_order)
                    """,
                    item,
                )

        existing_habits = conn.execute("SELECT COUNT(*) FROM habits").fetchone()[0]
        if existing_habits == 0 and parsed["habits"]:
            for h in parsed["habits"]:
                conn.execute(
                    """
                    INSERT INTO habits (id, title, cadence, two_minute_version, category, sort_order)
                    VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (
                        h["id"],
                        h["title"],
                        h["cadence"],
                        h["two_minute_version"],
                        h["category"],
                        h["sort_order"],
                    ),
                )
                for iid in h["identity_ids"]:
                    conn.execute(
                        "INSERT OR IGNORE INTO habit_identities (habit_id, identity_id) VALUES (?, ?)",
                        (h["id"], iid),
                    )

        existing_actions = conn.execute("SELECT COUNT(*) FROM actions").fetchone()[0]
        if existing_actions == 0 and seed_examples and parsed["examples"] and parsed["identities"]:
            today = dt.date.today()
            monday = get_monday(today.isoformat())
            ident_rows = parsed["identities"]

            for idx, ex in enumerate(parsed["examples"]):
                hint_words = [
                    w.strip().lower()
                    for w in re.split(r"[/,]", ex["identity_hint"])
                    if w.strip()
                ]
                matched_ids = []
                for ir in ident_rows:
                    ir_lower = ir["name"].lower()
                    if any(hw in ir_lower for hw in hint_words):
                        matched_ids.append(ir["id"])
                if not matched_ids:
                    matched_ids = [ident_rows[0]["id"]]

                action_date = min(monday + dt.timedelta(days=idx), today).isoformat()
                ts = build_timestamp_fields(action_date)
                cur = conn.execute(
                    """
                    INSERT INTO actions (
                        action_date, action_time, created_at,
                        day, month, year, hour, minute, second,
                        title, evidence_note, habit_id, kind, used_two_minute_rule
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, NULL, 'vote', 0)
                    """,
                    (
                        ts["action_date"],
                        ts["action_time"],
                        ts["created_at"],
                        ts["day"],
                        ts["month"],
                        ts["year"],
                        ts["hour"],
                        ts["minute"],
                        ts["second"],
                        ex["title"],
                        f"Imported from {md_path.name} example ({ex['identity_hint']})",
                    ),
                )
                aid = cur.lastrowid
                for iid in matched_ids:
                    conn.execute(
                        "INSERT OR IGNORE INTO action_identities (action_id, identity_id) VALUES (?, ?)",
                        (aid, iid),
                    )


def get_settings(conn: sqlite3.Connection) -> dict[str, Any]:
    rows = conn.execute("SELECT key, value_json FROM settings").fetchall()
    out: dict[str, Any] = {}
    for r in rows:
        try:
            out[r["key"]] = json.loads(r["value_json"])
        except json.JSONDecodeError:
            out[r["key"]] = r["value_json"]
    return out


def compute_identity_distribution(
    identities: list[dict[str, Any]],
    actions: list[dict[str, Any]],
) -> dict[str, Any]:
    """
    Compute fractional vote distribution across active identities without double-counting,
    accounting for both positive votes ('vote') and negative devotes ('devote').

    Rules:
    - Each 'vote' action has a total weight of +1.0 (split 1/k across k linked identities).
    - Each 'devote' action has a total weight of -1.0 (split -1/k across k linked identities).
    - Net weight per identity is clamped at >= 0.0 for pie chart slice geometry so slices
      remain valid and sum to 100% of positive net votes.
    """
    active_ids = {i["id"] for i in identities}
    vote_actions = [
        a
        for a in actions
        if a.get("kind", "vote") == "vote"
        and any(iid in active_ids for iid in a.get("identity_ids", []))
    ]
    devote_actions = [
        a
        for a in actions
        if a.get("kind") == "devote"
        and any(iid in active_ids for iid in a.get("identity_ids", []))
    ]
    obstacle_actions = [a for a in actions if a.get("kind") == "obstacle"]

    two_min_votes = sum(1 for a in vote_actions if a.get("used_two_minute_rule"))

    weights: dict[str, float] = {i["id"]: 0.0 for i in identities}
    touches: dict[str, int] = {i["id"]: 0 for i in identities}
    devotes_per_ident: dict[str, int] = {i["id"]: 0 for i in identities}

    for action in vote_actions:
        linked = [iid for iid in action["identity_ids"] if iid in weights]
        k = len(linked)
        if k == 0:
            continue
        share = 1.0 / k
        for iid in linked:
            weights[iid] += share
            touches[iid] += 1

    for action in devote_actions:
        linked = [iid for iid in action["identity_ids"] if iid in weights]
        k = len(linked)
        if k == 0:
            continue
        share = 1.0 / k
        for iid in linked:
            weights[iid] = max(0.0, weights[iid] - share)
            devotes_per_ident[iid] += 1

    net_total_weight = sum(weights.values())
    slices = []
    for idx, ident in enumerate(sorted(identities, key=lambda x: (x["sort_order"], x["name"])), start=1):
        iid = ident["id"]
        w = weights[iid]
        pct = (w / net_total_weight * 100.0) if net_total_weight > 0 else 0.0
        slices.append(
            {
                "identity_id": iid,
                "name": ident["name"],
                "domain": ident.get("domain", "general"),
                "slot": idx,
                "color_light": ident["color_light"],
                "color_dark": ident["color_dark"],
                "weighted_votes": round(w, 2),
                "exact_weight": w,
                "percentage": round(pct, 1),
                "raw_touches": touches[iid],
                "devote_count": devotes_per_ident[iid],
            }
        )

    active_count = sum(1 for s in slices if s["exact_weight"] > 0 or s["raw_touches"] > 0)
    return {
        "total_votes": round(net_total_weight, 2) if net_total_weight % 1 else int(round(net_total_weight)),
        "raw_vote_actions": len(vote_actions),
        "total_devotes": len(devote_actions),
        "total_obstacles": len(obstacle_actions),
        "two_minute_votes": two_min_votes,
        "active_identities_count": active_count,
        "slices": slices,
    }


def fetch_actions_in_range(
    conn: sqlite3.Connection,
    start_date: str,
    end_date: str,
) -> list[dict[str, Any]]:
    rows = conn.execute(
        """
        SELECT id, action_date, action_time, created_at,
               day, month, year, hour, minute, second,
               title, evidence_note, habit_id, kind, used_two_minute_rule
        FROM actions
        WHERE action_date >= ? AND action_date <= ?
        ORDER BY action_date DESC, action_time DESC, id DESC
        """,
        (start_date, end_date),
    ).fetchall()

    if not rows:
        return []

    action_ids = [r["id"] for r in rows]
    placeholders = ",".join("?" for _ in action_ids)
    link_rows = conn.execute(
        f"""
        SELECT ai.action_id, ai.identity_id, i.name, i.color_light, i.color_dark, i.sort_order
        FROM action_identities ai
        JOIN identities i ON i.id = ai.identity_id
        WHERE ai.action_id IN ({placeholders})
        ORDER BY i.sort_order ASC
        """,
        action_ids,
    ).fetchall()

    links_by_action: dict[int, list[dict[str, Any]]] = {aid: [] for aid in action_ids}
    for lr in link_rows:
        links_by_action[lr["action_id"]].append(
            {
                "id": lr["identity_id"],
                "name": lr["name"],
                "color_light": lr["color_light"],
                "color_dark": lr["color_dark"],
                "slot": lr["sort_order"],
            }
        )

    result = []
    for r in rows:
        linked = links_by_action.get(r["id"], [])
        k = len(linked)
        sign = 1.0 if r["kind"] == "vote" else (-1.0 if r["kind"] == "devote" else 0.0)
        formatted_ts = f"{r['day']:02d}/{r['month']:02d}/{r['year']:04d} {r['hour']:02d}:{r['minute']:02d}:{r['second']:02d}"
        result.append(
            {
                "id": r["id"],
                "action_date": r["action_date"],
                "action_time": r["action_time"],
                "created_at": r["created_at"],
                "timestamp_display": formatted_ts,
                "day": r["day"],
                "month": r["month"],
                "year": r["year"],
                "hour": r["hour"],
                "minute": r["minute"],
                "second": r["second"],
                "title": r["title"],
                "evidence_note": r["evidence_note"],
                "habit_id": r["habit_id"],
                "kind": r["kind"],
                "used_two_minute_rule": bool(r["used_two_minute_rule"]),
                "identity_ids": [item["id"] for item in linked],
                "identities": linked,
                "fractional_weight": round(sign / k, 2) if k > 0 and sign != 0.0 else 0.0,
            }
        )
    return result


def build_weekly_auto_summary(
    identities: list[dict[str, Any]],
    week_actions: list[dict[str, Any]],
    distribution: dict[str, Any],
) -> dict[str, Any]:
    """Summarize behavioral evidence dynamically for whatever identities exist."""
    slices_by_weight = sorted(
        distribution["slices"],
        key=lambda s: (s["exact_weight"], s["raw_touches"]),
        reverse=True,
    )
    supported = [s for s in slices_by_weight if s["exact_weight"] > 0]
    neglected = [s for s in distribution["slices"] if s["exact_weight"] == 0]

    counts: dict[str, dict[str, Any]] = {}
    for act in week_actions:
        if act["kind"] != "vote":
            continue
        key = act["habit_id"] or act["title"].strip().lower()
        if key not in counts:
            counts[key] = {
                "title": act["title"],
                "count": 0,
                "identities": act["identities"],
            }
        counts[key]["count"] += 1

    repeated = sorted(
        [v for v in counts.values() if v["count"] >= 2],
        key=lambda x: x["count"],
        reverse=True,
    )

    obstacles = [a for a in week_actions if a["kind"] in ("obstacle", "devote")]
    vote_actions = [a for a in week_actions if a["kind"] == "vote"]
    strongest_candidates = [
        a
        for a in vote_actions
        if a["evidence_note"].strip() or len(a["identity_ids"]) > 1
    ][:6]

    domain_weights: dict[str, float] = {}
    for s in distribution["slices"]:
        dom = s.get("domain", "general")
        domain_weights[dom] = round(domain_weights.get(dom, 0.0) + s["exact_weight"], 2)

    if supported:
        top_str = ", ".join(
            f"{s['name']} ({s['weighted_votes']} votes / {s['raw_touches']} actions)"
            for s in supported[:3]
        )
        suggested_supported = f"Most active identities: {top_str}."
    else:
        suggested_supported = "No votes logged yet for this week."

    if neglected or obstacles:
        parts = []
        if obstacles:
            parts.append(
                "Logged devotes/obstacles: "
                + "; ".join(
                    f"{o['title']} ({o['timestamp_display']})" for o in obstacles[:3]
                )
            )
        if neglected:
            parts.append("Unvoted identities this week: " + ", ".join(n["name"] for n in neglected))
        suggested_contradicted = " | ".join(parts)
    else:
        suggested_contradicted = "All active identities received votes and no obstacles were logged."

    return {
        "supported_identities": supported,
        "neglected_identities": neglected,
        "repeated_behaviors": repeated,
        "obstacles": obstacles,
        "strongest_candidates": strongest_candidates,
        "domain_weights": domain_weights,
        "suggested_supported": suggested_supported,
        "suggested_contradicted": suggested_contradicted,
    }


def get_app_state(
    db_path: Path = DEFAULT_DB_PATH,
    selected_date: str | None = None,
    week_start: str | None = None,
    scope: str = "week",
) -> dict[str, Any]:
    today_str = dt.date.today().isoformat()
    sel_date = selected_date or today_str
    monday_date = get_monday(week_start or sel_date)
    sunday_date = monday_date + dt.timedelta(days=6)
    monday_str = monday_date.isoformat()
    sunday_str = sunday_date.isoformat()

    with connect_db(db_path) as conn:
        _ensure_action_time_columns(conn)
        settings = get_settings(conn)
        ident_rows = conn.execute(
            "SELECT * FROM identities WHERE archived = 0 ORDER BY sort_order ASC, name ASC"
        ).fetchall()
        identities = [dict(r) for r in ident_rows]

        habit_rows = conn.execute(
            "SELECT * FROM habits WHERE active = 1 ORDER BY sort_order ASC, title ASC"
        ).fetchall()
        habit_links = conn.execute(
            "SELECT habit_id, identity_id FROM habit_identities"
        ).fetchall()
        h_map: dict[str, list[str]] = {}
        for hl in habit_links:
            h_map.setdefault(hl["habit_id"], []).append(hl["identity_id"])

        week_actions = fetch_actions_in_range(conn, monday_str, sunday_str)
        day_actions = [a for a in week_actions if a["action_date"] == sel_date]
        if not (monday_str <= sel_date <= sunday_str):
            day_actions = fetch_actions_in_range(conn, sel_date, sel_date)

        active_actions = day_actions if scope == "day" else week_actions
        chart_data = compute_identity_distribution(identities, active_actions)
        week_distribution = compute_identity_distribution(identities, week_actions)

        completed_on_date: dict[str, int] = {}
        for a in day_actions:
            if a["habit_id"]:
                if a["kind"] == "vote":
                    completed_on_date[a["habit_id"]] = completed_on_date.get(a["habit_id"], 0) + 1
                elif a["kind"] == "devote":
                    completed_on_date[a["habit_id"]] = max(0, completed_on_date.get(a["habit_id"], 0) - 1)

        habits = []
        for hr in habit_rows:
            hd = dict(hr)
            hd["identity_ids"] = h_map.get(hr["id"], [])
            hd["completed_on_selected_date"] = completed_on_date.get(hr["id"], 0)
            habits.append(hd)

        slice_by_id = {s["identity_id"]: s for s in chart_data["slices"]}
        week_slice_by_id = {s["identity_id"]: s for s in week_distribution["slices"]}
        for ident in identities:
            iid = ident["id"]
            s_cur = slice_by_id.get(iid, {"weighted_votes": 0.0, "percentage": 0.0, "raw_touches": 0, "devote_count": 0})
            s_wk = week_slice_by_id.get(iid, {"weighted_votes": 0.0, "raw_touches": 0, "devote_count": 0})
            ident["weighted_votes"] = s_cur["weighted_votes"]
            ident["percentage"] = s_cur["percentage"]
            ident["raw_touches"] = s_cur["raw_touches"]
            ident["devote_count"] = s_cur.get("devote_count", 0)
            ident["week_weighted_votes"] = s_wk["weighted_votes"]
            ident["week_raw_touches"] = s_wk["raw_touches"]
            ident["recent_actions"] = [
                a for a in active_actions if iid in a["identity_ids"] and a["kind"] == "vote"
            ][:3]

        heatmap_start = (sunday_date - dt.timedelta(days=27)).isoformat()
        heatmap_actions = fetch_actions_in_range(conn, heatmap_start, sunday_str)
        by_date: dict[str, list[dict[str, Any]]] = {}
        for a in heatmap_actions:
            by_date.setdefault(a["action_date"], []).append(a)

        day_names = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
        week_days = []
        for idx in range(7):
            d_obj = monday_date + dt.timedelta(days=idx)
            d_iso = d_obj.isoformat()
            prev_iso = (d_obj - dt.timedelta(days=1)).isoformat()
            d_acts = by_date.get(d_iso, [])
            prev_acts = by_date.get(prev_iso, [])
            d_votes = [a for a in d_acts if a["kind"] == "vote"]
            d_devotes = [a for a in d_acts if a["kind"] == "devote"]
            prev_votes = [a for a in prev_acts if a["kind"] == "vote"]
            d_obstacles = [a for a in d_acts if a["kind"] == "obstacle"]

            touched_ids = []
            for v in d_votes:
                for iid in v["identity_ids"]:
                    if iid not in touched_ids:
                        touched_ids.append(iid)

            net_day_votes = max(0, len(d_votes) - len(d_devotes))
            week_days.append(
                {
                    "date": d_iso,
                    "day_name": day_names[idx],
                    "day_num": d_obj.day,
                    "is_today": d_iso == today_str,
                    "is_selected": d_iso == sel_date,
                    "vote_count": net_day_votes,
                    "devote_count": len(d_devotes),
                    "obstacle_count": len(d_obstacles),
                    "identities_touched": touched_ids,
                    "never_miss_twice_recovered": len(prev_votes) == 0 and net_day_votes > 0 and d_obj <= dt.date.today(),
                }
            )

        heatmap_28d = []
        for idx in range(28):
            d_obj = sunday_date - dt.timedelta(days=27 - idx)
            d_iso = d_obj.isoformat()
            d_acts = by_date.get(d_iso, [])
            d_votes = [a for a in d_acts if a["kind"] == "vote"]
            d_devotes = [a for a in d_acts if a["kind"] == "devote"]
            net_v = max(0, len(d_votes) - len(d_devotes))
            touched_ids = []
            for v in d_votes:
                for iid in v["identity_ids"]:
                    if iid not in touched_ids:
                        touched_ids.append(iid)
            heatmap_28d.append(
                {
                    "date": d_iso,
                    "vote_count": net_v,
                    "identities_touched": touched_ids,
                    "is_today": d_iso == today_str,
                    "is_selected": d_iso == sel_date,
                }
            )

        rev_row = conn.execute(
            "SELECT * FROM weekly_reviews WHERE week_start = ?",
            (monday_str,),
        ).fetchone()
        if rev_row:
            saved_review = dict(rev_row)
            try:
                saved_review["answers"] = json.loads(saved_review.pop("answers_json") or "{}")
            except json.JSONDecodeError:
                saved_review["answers"] = {}
            try:
                saved_review["system_checks"] = json.loads(saved_review.pop("system_checks_json") or "{}")
            except json.JSONDecodeError:
                saved_review["system_checks"] = {}
        else:
            saved_review = {
                "week_start": monday_str,
                "review_date": dt.datetime.now().strftime("%d/%m/%Y %H:%M:%S"),
                "answers": {},
                "one_adjustment": "",
                "strongest_evidence": "",
                "next_smallest_action": "",
                "overall_stage": "Building evidence",
                "system_checks": {},
            }

        latest_adj_row = conn.execute(
            """
            SELECT week_start, one_adjustment, next_smallest_action
            FROM weekly_reviews
            WHERE trim(one_adjustment) != '' OR trim(next_smallest_action) != ''
            ORDER BY week_start DESC
            LIMIT 1
            """
        ).fetchone()
        pinned_adjustment = (
            dict(latest_adj_row)
            if latest_adj_row
            else {
                "week_start": monday_str,
                "one_adjustment": "",
                "next_smallest_action": "",
            }
        )

        auto_summary = build_weekly_auto_summary(identities, week_actions, week_distribution)

    return {
        "today": today_str,
        "selected_date": sel_date,
        "week_start": monday_str,
        "week_end": sunday_str,
        "scope": scope,
        "settings": settings,
        "palette_slots": PALETTE_SLOTS,
        "identities": identities,
        "habits": habits,
        "actions": active_actions,
        "chart": chart_data,
        "calendar": {
            "week_days": week_days,
            "heatmap_28d": heatmap_28d,
        },
        "weekly_review": {
            "saved": saved_review,
            "pinned_adjustment": pinned_adjustment,
            "auto_summary": auto_summary,
        },
    }


# ---------------------------------------------------------------------------
# Extendable CRUD Operations: Identities, Habits, Actions, Devote, Reviews
# ---------------------------------------------------------------------------

def create_identity(payload: dict[str, Any], db_path: Path = DEFAULT_DB_PATH) -> dict[str, Any]:
    name = str(payload.get("name") or "").strip()
    if not name:
        raise ValueError("Identity name is required.")
    tagline = str(payload.get("tagline") or f"Votes supporting {name}").strip()
    domain = str(payload.get("domain") or "general").strip()
    current_stage = str(payload.get("current_stage") or "Building evidence").strip()

    with connect_db(db_path) as conn:
        count = conn.execute("SELECT COUNT(*) FROM identities").fetchone()[0]
        slot = PALETTE_SLOTS[count % len(PALETTE_SLOTS)]
        color_light = str(payload.get("color_light") or slot["light"]).strip()
        color_dark = str(payload.get("color_dark") or slot["dark"]).strip()

        base_id = slugify(payload.get("id") or name)
        ident_id = base_id
        suffix = 2
        while conn.execute("SELECT 1 FROM identities WHERE id = ?", (ident_id,)).fetchone():
            ident_id = f"{base_id}_{suffix}"
            suffix += 1

        max_order = conn.execute("SELECT COALESCE(MAX(sort_order), 0) FROM identities").fetchone()[0]
        conn.execute(
            """
            INSERT INTO identities (id, name, tagline, domain, color_light, color_dark, current_stage, sort_order, archived)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, 0)
            """,
            (ident_id, name, tagline, domain, color_light, color_dark, current_stage, max_order + 1),
        )
    return {"id": ident_id, "status": "created"}


def update_identity(
    identity_id: str,
    payload: dict[str, Any],
    db_path: Path = DEFAULT_DB_PATH,
) -> dict[str, Any]:
    with connect_db(db_path) as conn:
        row = conn.execute("SELECT * FROM identities WHERE id = ?", (identity_id,)).fetchone()
        if not row:
            raise KeyError(f"Identity '{identity_id}' not found.")

        name = str(payload.get("name", row["name"])).strip()
        if not name:
            raise ValueError("Identity name cannot be empty.")
        tagline = str(payload.get("tagline", row["tagline"])).strip()
        domain = str(payload.get("domain", row["domain"])).strip()
        color_light = str(payload.get("color_light", row["color_light"])).strip()
        color_dark = str(payload.get("color_dark", row["color_dark"])).strip()
        current_stage = str(payload.get("current_stage", row["current_stage"])).strip()
        sort_order = int(payload.get("sort_order", row["sort_order"]))
        archived = 1 if payload.get("archived", bool(row["archived"])) else 0

        conn.execute(
            """
            UPDATE identities
            SET name = ?, tagline = ?, domain = ?, color_light = ?, color_dark = ?,
                current_stage = ?, sort_order = ?, archived = ?
            WHERE id = ?
            """,
            (name, tagline, domain, color_light, color_dark, current_stage, sort_order, archived, identity_id),
        )
    return {"id": identity_id, "status": "updated"}


def delete_identity(identity_id: str, db_path: Path = DEFAULT_DB_PATH) -> dict[str, Any]:
    """
    Delete an identity from the database and clean up any habits or actions
    that were exclusively linked to this identity so logs and charts reflect the deletion.
    """
    with connect_db(db_path) as conn:
        conn.execute("DELETE FROM identities WHERE id = ?", (identity_id,))
        # Remove habits that no longer have any linked identities
        conn.execute(
            """
            DELETE FROM habits
            WHERE id NOT IN (SELECT DISTINCT habit_id FROM habit_identities)
            """
        )
        # Remove actions in logs that no longer have any linked identities
        conn.execute(
            """
            DELETE FROM actions
            WHERE id NOT IN (SELECT DISTINCT action_id FROM action_identities)
            """
        )
    return {"id": identity_id, "status": "deleted"}


def create_habit(payload: dict[str, Any], db_path: Path = DEFAULT_DB_PATH) -> dict[str, Any]:
    title = str(payload.get("title") or "").strip()
    if not title:
        raise ValueError("Habit title is required.")
    two_min = str(payload.get("two_minute_version") or "").strip() or derive_two_minute_starter(title)
    cadence = str(payload.get("cadence") or "daily").strip()
    category = str(payload.get("category") or "identity_habit").strip()
    identity_ids = list(payload.get("identity_ids") or [])
    if not identity_ids:
        raise ValueError("At least one identity is required for a habit.")

    habit_id = f"habit_{int(dt.datetime.now().timestamp() * 1000)}_{slugify(title)[:18]}"
    with connect_db(db_path) as conn:
        max_order = conn.execute("SELECT COALESCE(MAX(sort_order), 0) FROM habits").fetchone()[0]
        conn.execute(
            """
            INSERT INTO habits (id, title, cadence, two_minute_version, category, sort_order, active)
            VALUES (?, ?, ?, ?, ?, ?, 1)
            """,
            (habit_id, title, cadence, two_min, category, max_order + 1),
        )
        for iid in identity_ids:
            conn.execute(
                "INSERT OR IGNORE INTO habit_identities (habit_id, identity_id) VALUES (?, ?)",
                (habit_id, iid),
            )
    return {"id": habit_id, "status": "created"}


def update_habit(
    habit_id: str,
    payload: dict[str, Any],
    db_path: Path = DEFAULT_DB_PATH,
) -> dict[str, Any]:
    with connect_db(db_path) as conn:
        row = conn.execute("SELECT * FROM habits WHERE id = ?", (habit_id,)).fetchone()
        if not row:
            raise KeyError(f"Habit '{habit_id}' not found.")

        title = str(payload.get("title", row["title"])).strip()
        if not title:
            raise ValueError("Habit title cannot be empty.")
        two_min = str(payload.get("two_minute_version", row["two_minute_version"])).strip()
        cadence = str(payload.get("cadence", row["cadence"])).strip()
        category = str(payload.get("category", row["category"])).strip()
        active = 1 if payload.get("active", bool(row["active"])) else 0

        conn.execute(
            """
            UPDATE habits
            SET title = ?, two_minute_version = ?, cadence = ?, category = ?, active = ?
            WHERE id = ?
            """,
            (title, two_min, cadence, category, active, habit_id),
        )

        if "identity_ids" in payload:
            identity_ids = list(payload["identity_ids"] or [])
            if not identity_ids:
                raise ValueError("At least one identity is required.")
            conn.execute("DELETE FROM habit_identities WHERE habit_id = ?", (habit_id,))
            for iid in identity_ids:
                conn.execute(
                    "INSERT OR IGNORE INTO habit_identities (habit_id, identity_id) VALUES (?, ?)",
                    (habit_id, iid),
                )
    return {"id": habit_id, "status": "updated"}


def delete_habit(habit_id: str, db_path: Path = DEFAULT_DB_PATH) -> dict[str, Any]:
    """
    Delete a habit and remove its associated action logs from the database
    so both the database and the logs reflect the habit deletion.
    """
    with connect_db(db_path) as conn:
        conn.execute("DELETE FROM actions WHERE habit_id = ?", (habit_id,))
        conn.execute("DELETE FROM habits WHERE id = ?", (habit_id,))
    return {"id": habit_id, "status": "deleted"}


def create_action(
    payload: dict[str, Any],
    db_path: Path = DEFAULT_DB_PATH,
) -> dict[str, Any]:
    title = str(payload.get("title") or "").strip()
    habit_id = payload.get("habit_id")
    action_date = str(payload.get("action_date") or dt.date.today().isoformat()).strip()
    evidence_note = str(payload.get("evidence_note") or "").strip()
    kind = str(payload.get("kind") or "vote").strip()
    if kind not in ("vote", "devote", "obstacle"):
        kind = "vote"
    used_two_min = 1 if payload.get("used_two_minute_rule") else 0
    identity_ids = list(payload.get("identity_ids") or [])

    with connect_db(db_path) as conn:
        _ensure_action_time_columns(conn)
        if habit_id:
            h_row = conn.execute("SELECT * FROM habits WHERE id = ?", (habit_id,)).fetchone()
            if h_row:
                if not title:
                    title = h_row["two_minute_version"] if (used_two_min and h_row["two_minute_version"]) else h_row["title"]
                if not identity_ids:
                    links = conn.execute(
                        "SELECT identity_id FROM habit_identities WHERE habit_id = ?",
                        (habit_id,),
                    ).fetchall()
                    identity_ids = [r["identity_id"] for r in links]

        if not title:
            raise ValueError("Action title is required.")

        valid_ids = {
            r["id"] for r in conn.execute("SELECT id FROM identities").fetchall()
        }
        clean_identity_ids = []
        for iid in identity_ids:
            if iid in valid_ids and iid not in clean_identity_ids:
                clean_identity_ids.append(iid)

        if not clean_identity_ids:
            raise ValueError("At least one valid identity must be linked to an action.")

        ts = build_timestamp_fields(action_date)
        cur = conn.execute(
            """
            INSERT INTO actions (
                action_date, action_time, created_at,
                day, month, year, hour, minute, second,
                title, evidence_note, habit_id, kind, used_two_minute_rule
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                ts["action_date"],
                ts["action_time"],
                ts["created_at"],
                ts["day"],
                ts["month"],
                ts["year"],
                ts["hour"],
                ts["minute"],
                ts["second"],
                title,
                evidence_note,
                habit_id,
                kind,
                used_two_min,
            ),
        )
        action_id = cur.lastrowid
        for iid in clean_identity_ids:
            conn.execute(
                "INSERT INTO action_identities (action_id, identity_id) VALUES (?, ?)",
                (action_id, iid),
            )

    return {
        "id": action_id,
        "status": "created",
        "kind": kind,
        "timestamp": ts["created_at"],
        "day": ts["day"],
        "month": ts["month"],
        "year": ts["year"],
        "hour": ts["hour"],
        "minute": ts["minute"],
        "second": ts["second"],
    }


def devote_action(
    payload: dict[str, Any],
    db_path: Path = DEFAULT_DB_PATH,
) -> dict[str, Any]:
    """
    Devote (remove/un-vote or record a negative devote) and reflect in database and logs:
    - If `action_id` is passed: deletes that vote action from `actions` (or if `mode == 'log'`, converts/logs a devote).
    - If `habit_id` is passed and there is an existing 'vote' for that habit on `action_date` (and `mode != 'log'`),
      deletes the most recent vote row for that habit from the database so the vote count and logs immediately decrement.
    - Otherwise, inserts a `kind = 'devote'` entry with full day/month/year/hour/min/sec timestamp into `actions`
      so the devote is recorded in the database and logs and subtracts from the identity's vote total.
    """
    action_id = payload.get("action_id")
    habit_id = payload.get("habit_id")
    action_date = str(payload.get("action_date") or dt.date.today().isoformat()).strip()
    mode = str(payload.get("mode") or "auto").strip()

    with connect_db(db_path) as conn:
        _ensure_action_time_columns(conn)

        if action_id is not None:
            conn.execute("DELETE FROM actions WHERE id = ?", (int(action_id),))
            return {"action_id": int(action_id), "effect": "removed_vote", "status": "devoted"}

        if habit_id and mode != "log":
            latest_vote = conn.execute(
                """
                SELECT id, title FROM actions
                WHERE habit_id = ? AND action_date = ? AND kind = 'vote'
                ORDER BY id DESC
                LIMIT 1
                """,
                (habit_id, action_date[:10]),
            ).fetchone()
            if latest_vote:
                conn.execute("DELETE FROM actions WHERE id = ?", (latest_vote["id"],))
                return {
                    "action_id": latest_vote["id"],
                    "habit_id": habit_id,
                    "effect": "removed_vote",
                    "status": "devoted",
                }

    # If no existing vote to undo (or explicit log mode), record a 'devote' action in DB & logs
    payload_copy = dict(payload)
    payload_copy["kind"] = "devote"
    if not payload_copy.get("title") and habit_id:
        with connect_db(db_path) as conn:
            h_row = conn.execute("SELECT title FROM habits WHERE id = ?", (habit_id,)).fetchone()
            if h_row:
                payload_copy["title"] = f"Devoted: {h_row['title']}"
    res = create_action(payload_copy, db_path=db_path)
    res["effect"] = "logged_devote"
    res["status"] = "devoted"
    return res


def update_action(
    action_id: int,
    payload: dict[str, Any],
    db_path: Path = DEFAULT_DB_PATH,
) -> dict[str, Any]:
    with connect_db(db_path) as conn:
        _ensure_action_time_columns(conn)
        existing = conn.execute("SELECT * FROM actions WHERE id = ?", (action_id,)).fetchone()
        if not existing:
            raise KeyError(f"Action {action_id} not found.")

        title = str(payload.get("title", existing["title"])).strip()
        if not title:
            raise ValueError("Action title cannot be empty.")
        action_date = str(payload.get("action_date", existing["action_date"])).strip()
        evidence_note = str(payload.get("evidence_note", existing["evidence_note"])).strip()
        kind = str(payload.get("kind", existing["kind"])).strip()
        if kind not in ("vote", "devote", "obstacle"):
            kind = "vote"
        used_two_min = (
            1
            if payload.get("used_two_minute_rule", bool(existing["used_two_minute_rule"]))
            else 0
        )

        conn.execute(
            """
            UPDATE actions
            SET title = ?, action_date = ?, evidence_note = ?, kind = ?, used_two_minute_rule = ?
            WHERE id = ?
            """,
            (title, action_date, evidence_note, kind, used_two_min, action_id),
        )

        if "identity_ids" in payload:
            valid_ids = {
                r["id"] for r in conn.execute("SELECT id FROM identities").fetchall()
            }
            clean_ids = []
            for iid in payload["identity_ids"]:
                if iid in valid_ids and iid not in clean_ids:
                    clean_ids.append(iid)
            if not clean_ids:
                raise ValueError("At least one valid identity is required.")
            conn.execute("DELETE FROM action_identities WHERE action_id = ?", (action_id,))
            for iid in clean_ids:
                conn.execute(
                    "INSERT INTO action_identities (action_id, identity_id) VALUES (?, ?)",
                    (action_id, iid),
                )

    return {"id": action_id, "status": "updated"}


def delete_action(action_id: int, db_path: Path = DEFAULT_DB_PATH) -> dict[str, Any]:
    with connect_db(db_path) as conn:
        conn.execute("DELETE FROM actions WHERE id = ?", (action_id,))
    return {"id": action_id, "status": "deleted"}


def save_weekly_review(
    payload: dict[str, Any],
    db_path: Path = DEFAULT_DB_PATH,
) -> dict[str, Any]:
    raw_week = str(payload.get("week_start") or dt.date.today().isoformat()).strip()
    monday_str = get_monday(raw_week).isoformat()
    review_date = dt.datetime.now().strftime("%d/%m/%Y %H:%M:%S")
    answers = payload.get("answers") or {}
    one_adjustment = str(payload.get("one_adjustment") or "").strip()
    strongest_evidence = str(payload.get("strongest_evidence") or "").strip()
    next_smallest_action = str(payload.get("next_smallest_action") or "").strip()
    overall_stage = str(payload.get("overall_stage") or "Building evidence").strip()
    system_checks = payload.get("system_checks") or {}

    with connect_db(db_path) as conn:
        conn.execute(
            """
            INSERT INTO weekly_reviews (
                week_start, review_date, answers_json,
                one_adjustment, strongest_evidence, next_smallest_action, overall_stage, system_checks_json
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(week_start) DO UPDATE SET
                review_date = excluded.review_date,
                answers_json = excluded.answers_json,
                one_adjustment = excluded.one_adjustment,
                strongest_evidence = excluded.strongest_evidence,
                next_smallest_action = excluded.next_smallest_action,
                overall_stage = excluded.overall_stage,
                system_checks_json = excluded.system_checks_json
            """,
            (
                monday_str,
                review_date,
                json.dumps(answers),
                one_adjustment,
                strongest_evidence,
                next_smallest_action,
                overall_stage,
                json.dumps(system_checks),
            ),
        )
    return {"week_start": monday_str, "review_date": review_date, "status": "saved"}


def update_settings(payload: dict[str, Any], db_path: Path = DEFAULT_DB_PATH) -> dict[str, Any]:
    """Allow extending/customizing reflection questions, stages, or anti-identity principle."""
    with connect_db(db_path) as conn:
        for key in ("stages", "reflection_questions", "anti_principle", "system_checks"):
            if key in payload:
                conn.execute(
                    """
                    INSERT INTO settings (key, value_json) VALUES (?, ?)
                    ON CONFLICT(key) DO UPDATE SET value_json = excluded.value_json
                    """,
                    (key, json.dumps(payload[key])),
                )
    return {"status": "updated"}


def load_guidance_documents(guidance_dir: Path = GUIDANCE_DIR) -> list[dict[str, Any]]:
    """Dynamically discover all Markdown (.md) files in guidance_dir."""
    guidance_dir.mkdir(parents=True, exist_ok=True)
    docs = []
    for fpath in sorted(guidance_dir.glob("*.md")):
        content = fpath.read_text(encoding="utf-8")
        lines = [ln.strip() for ln in content.splitlines() if ln.strip()]
        title = fpath.stem.replace("-", " ").title()
        subtitle = "Markdown guidance document"
        for idx, ln in enumerate(lines):
            if ln.startswith("# "):
                title = ln[2:].strip()
                if idx + 1 < len(lines) and not lines[idx + 1].startswith("#"):
                    subtitle = re.sub(r"^[>*_\-\s]+", "", lines[idx + 1]).strip()[:120]
                break
        docs.append(
            {
                "id": fpath.stem,
                "title": title,
                "subtitle": subtitle,
                "filename": f"guidance/{fpath.name}",
                "markdown": content,
            }
        )
    return docs


def save_guidance_document(
    payload: dict[str, Any],
    guidance_dir: Path = GUIDANCE_DIR,
) -> dict[str, Any]:
    """Create or update a Markdown guidance file in guidance_dir."""
    guidance_dir.mkdir(parents=True, exist_ok=True)
    raw_id = str(payload.get("id") or payload.get("title") or "").strip()
    if not raw_id:
        raise ValueError("Document id or title is required.")
    doc_id = re.sub(r"[^a-z0-9\-]+", "-", raw_id.lower()).strip("-")
    if not doc_id:
        raise ValueError("Invalid document identifier.")
    markdown = str(payload.get("markdown") or "")
    target = (guidance_dir / f"{doc_id}.md").resolve()
    if not str(target).startswith(str(guidance_dir.resolve())):
        raise ValueError("Invalid guidance path.")
    target.write_text(markdown, encoding="utf-8")
    return {"id": doc_id, "filename": f"guidance/{doc_id}.md", "status": "saved"}


def delete_guidance_document(doc_id: str, guidance_dir: Path = GUIDANCE_DIR) -> dict[str, Any]:
    safe_id = re.sub(r"[^a-z0-9\-]+", "-", doc_id.lower()).strip("-")
    target = (guidance_dir / f"{safe_id}.md").resolve()
    if str(target).startswith(str(guidance_dir.resolve())) and target.is_file():
        target.unlink()
    return {"id": safe_id, "status": "deleted"}


class IdentityOSRequestHandler(BaseHTTPRequestHandler):
    db_path: Path = DEFAULT_DB_PATH
    guidance_dir: Path = GUIDANCE_DIR

    def log_message(self, format: str, *args: Any) -> None:
        if os.environ.get("IDENTITY_OS_VERBOSE"):
            super().log_message(format, *args)

    def _send_json(self, data: Any, status: int = 200) -> None:
        raw = json.dumps(data).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(raw)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(raw)

    def _read_json(self) -> dict[str, Any]:
        length = int(self.headers.get("Content-Length", "0"))
        if length <= 0:
            return {}
        body = self.rfile.read(length).decode("utf-8")
        return json.loads(body) if body else {}

    def do_GET(self) -> None:
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path
        query = urllib.parse.parse_qs(parsed.query)

        try:
            if path == "/api/state":
                sel_date = query.get("date", [None])[0]
                week_start = query.get("week_start", [None])[0]
                scope = query.get("scope", ["week"])[0]
                state = get_app_state(
                    db_path=self.db_path,
                    selected_date=sel_date,
                    week_start=week_start,
                    scope=scope,
                )
                self._send_json(state)
                return

            if path == "/api/guidance":
                docs = load_guidance_documents(self.guidance_dir)
                self._send_json({"documents": docs})
                return

            rel = "index.html" if path in ("/", "") else path.lstrip("/")
            target = (STATIC_DIR / rel).resolve()
            if not str(target).startswith(str(STATIC_DIR.resolve())) or not target.is_file():
                self._send_json({"error": "Not found"}, status=404)
                return

            ctype, _ = mimetypes.guess_type(str(target))
            data = target.read_bytes()
            self.send_response(200)
            self.send_header("Content-Type", f"{ctype or 'application/octet-stream'}; charset=utf-8")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)
        except Exception as exc:
            self._send_json({"error": str(exc)}, status=500)

    def do_POST(self) -> None:
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path
        try:
            payload = self._read_json()
            if path == "/api/identities":
                res = create_identity(payload, db_path=self.db_path)
                self._send_json(res, status=201)
                return
            if path == "/api/habits":
                res = create_habit(payload, db_path=self.db_path)
                self._send_json(res, status=201)
                return
            if path == "/api/actions":
                res = create_action(payload, db_path=self.db_path)
                self._send_json(res, status=201)
                return
            if path == "/api/actions/devote":
                res = devote_action(payload, db_path=self.db_path)
                self._send_json(res, status=200)
                return
            if path == "/api/weekly-review":
                res = save_weekly_review(payload, db_path=self.db_path)
                self._send_json(res, status=200)
                return
            if path == "/api/settings":
                res = update_settings(payload, db_path=self.db_path)
                self._send_json(res, status=200)
                return
            if path == "/api/guidance":
                res = save_guidance_document(payload, guidance_dir=self.guidance_dir)
                self._send_json(res, status=201)
                return
            self._send_json({"error": "Unknown endpoint"}, status=404)
        except ValueError as exc:
            self._send_json({"error": str(exc)}, status=400)
        except Exception as exc:
            self._send_json({"error": str(exc)}, status=500)

    def do_PUT(self) -> None:
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path
        try:
            payload = self._read_json()
            if path.startswith("/api/identities/"):
                ident_id = urllib.parse.unquote(path.split("/")[-1])
                res = update_identity(ident_id, payload, db_path=self.db_path)
                self._send_json(res)
                return
            if path.startswith("/api/habits/"):
                habit_id = urllib.parse.unquote(path.split("/")[-1])
                res = update_habit(habit_id, payload, db_path=self.db_path)
                self._send_json(res)
                return
            if path.startswith("/api/actions/"):
                action_id = int(path.split("/")[-1])
                res = update_action(action_id, payload, db_path=self.db_path)
                self._send_json(res)
                return
            if path.startswith("/api/guidance/"):
                doc_id = urllib.parse.unquote(path.split("/")[-1])
                payload["id"] = doc_id
                res = save_guidance_document(payload, guidance_dir=self.guidance_dir)
                self._send_json(res)
                return
            self._send_json({"error": "Unknown endpoint"}, status=404)
        except (ValueError, KeyError) as exc:
            self._send_json({"error": str(exc)}, status=400)
        except Exception as exc:
            self._send_json({"error": str(exc)}, status=500)

    def do_DELETE(self) -> None:
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path
        try:
            if path.startswith("/api/identities/"):
                ident_id = urllib.parse.unquote(path.split("/")[-1])
                res = delete_identity(ident_id, db_path=self.db_path)
                self._send_json(res)
                return
            if path.startswith("/api/habits/"):
                habit_id = urllib.parse.unquote(path.split("/")[-1])
                res = delete_habit(habit_id, db_path=self.db_path)
                self._send_json(res)
                return
            if path.startswith("/api/actions/"):
                action_id = int(path.split("/")[-1])
                res = delete_action(action_id, db_path=self.db_path)
                self._send_json(res)
                return
            if path.startswith("/api/guidance/"):
                doc_id = urllib.parse.unquote(path.split("/")[-1])
                res = delete_guidance_document(doc_id, guidance_dir=self.guidance_dir)
                self._send_json(res)
                return
            self._send_json({"error": "Unknown endpoint"}, status=404)
        except Exception as exc:
            self._send_json({"error": str(exc)}, status=500)


def run_server(host: str = "127.0.0.1", port: int = 8765, db_path: Path = DEFAULT_DB_PATH) -> None:
    init_db(db_path=db_path, seed_examples=True)
    IdentityOSRequestHandler.db_path = db_path
    server = ThreadingHTTPServer((host, port), IdentityOSRequestHandler)
    print(f"Identity Building OS running at http://{host}:{port}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    port_num = int(os.environ.get("PORT", "8765"))
    run_server(port=port_num)
