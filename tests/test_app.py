import hashlib
import json
import tempfile
import threading
import unittest
import urllib.request
from http.server import ThreadingHTTPServer
from pathlib import Path

import app


class IdentityOSVerificationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.temp_dir.name) / "test_identity_os.db"
        self.guidance_dir = Path(self.temp_dir.name) / "guidance"
        self.base_md_hash_before = hashlib.sha256(app.BASE_MARKDOWN_PATH.read_bytes()).hexdigest()

    def tearDown(self) -> None:
        base_md_hash_after = hashlib.sha256(app.BASE_MARKDOWN_PATH.read_bytes()).hexdigest()
        self.assertEqual(
            self.base_md_hash_before,
            base_md_hash_after,
            "base_database.md must never be modified or overwritten!",
        )
        self.temp_dir.cleanup()

    def test_01_dynamic_markdown_parser_and_non_destructive_seed(self) -> None:
        parsed = app.parse_base_markdown(app.BASE_MARKDOWN_PATH)
        self.assertEqual(len(parsed["identities"]), 6)
        self.assertEqual(len(parsed["habits"]), 27)  # 21 identity habits + 6 anti-identity guardrails
        self.assertEqual(len(parsed["examples"]), 5)
        self.assertEqual(len(parsed["reflection_questions"]), 4)
        self.assertEqual(len(parsed["stages"]), 5)
        self.assertIn("not trying to eliminate fun", parsed["anti_principle"])

        # Verify 'WEAKLY' in base_database.md was dynamically parsed as 'weekly' cadence
        youtube_habits = [h for h in parsed["habits"] if "youtube" in h["title"].lower()]
        self.assertEqual(len(youtube_habits), 1)
        self.assertEqual(youtube_habits[0]["cadence"], "weekly")
        self.assertFalse(youtube_habits[0]["title"].upper().startswith("WEAKLY"))

    def test_02_fractional_pie_chart_math_no_double_counting(self) -> None:
        app.init_db(db_path=self.db_path, seed_examples=False)
        state0 = app.get_app_state(db_path=self.db_path, selected_date="2026-10-26", scope="week")
        self.assertEqual(state0["chart"]["total_votes"], 0)

        ident_ids = [i["id"] for i in state0["identities"]]
        ent_id, free_id, disc_id = ident_ids[0], ident_ids[1], ident_ids[4]

        # Action 1: Single identity (weight = 1.0)
        app.create_action(
            {
                "title": "Built MVP prototype",
                "action_date": "2026-10-26",
                "identity_ids": [ent_id],
                "evidence_note": "Deployed working demo",
                "kind": "vote",
            },
            db_path=self.db_path,
        )

        # Action 2: Two identities (weight = 0.5 each)
        app.create_action(
            {
                "title": "Started client deliverable at 8:00 AM sharp",
                "action_date": "2026-10-26",
                "identity_ids": [free_id, disc_id],
                "used_two_minute_rule": True,
                "kind": "vote",
            },
            db_path=self.db_path,
        )

        # Action 3: Three identities (weight = 1/3 each)
        app.create_action(
            {
                "title": "Shipped open-source module on schedule for client project",
                "action_date": "2026-10-27",
                "identity_ids": [ent_id, free_id, disc_id],
                "kind": "vote",
            },
            db_path=self.db_path,
        )

        # Action 4: Obstacle log (must NOT inflate vote pie chart)
        app.create_action(
            {
                "title": "Scrolled short-form video late at night",
                "action_date": "2026-10-27",
                "identity_ids": [disc_id],
                "evidence_note": "Phone was left on desk",
                "kind": "obstacle",
            },
            db_path=self.db_path,
        )

        week_state = app.get_app_state(db_path=self.db_path, selected_date="2026-10-26", scope="week")
        chart = week_state["chart"]
        self.assertEqual(chart["total_votes"], 3)
        self.assertEqual(chart["total_obstacles"], 1)
        self.assertEqual(chart["two_minute_votes"], 1)

        total_exact_weight = sum(s["exact_weight"] for s in chart["slices"])
        self.assertAlmostEqual(total_exact_weight, 3.0, places=6)

        slice_map = {s["identity_id"]: s for s in chart["slices"]}
        # ent_id: 1.0 + 1/3 = 1.333... (raw_touches = 2)
        self.assertAlmostEqual(slice_map[ent_id]["exact_weight"], 1.0 + 1.0 / 3.0, places=5)
        self.assertEqual(slice_map[ent_id]["raw_touches"], 2)

        # free_id: 0.5 + 1/3 = 0.833... (raw_touches = 2)
        self.assertAlmostEqual(slice_map[free_id]["exact_weight"], 0.5 + 1.0 / 3.0, places=5)
        self.assertEqual(slice_map[free_id]["raw_touches"], 2)

        # disc_id: 0.5 + 1/3 = 0.833... (raw_touches = 2)
        self.assertAlmostEqual(slice_map[disc_id]["exact_weight"], 0.5 + 1.0 / 3.0, places=5)
        self.assertEqual(slice_map[disc_id]["raw_touches"], 2)

        # Daily scope filter check (only 2026-10-26 has 2 vote actions)
        day_state = app.get_app_state(db_path=self.db_path, selected_date="2026-10-26", scope="day")
        self.assertEqual(day_state["chart"]["total_votes"], 2)
        self.assertEqual(len(day_state["actions"]), 2)

    def test_03_system_extendability_crud_identities_habits_and_guidance(self) -> None:
        app.init_db(db_path=self.db_path, seed_examples=False)

        # 1. Create a brand-new 7th Identity dynamically
        new_ident = app.create_identity(
            {
                "name": "Open Source Maintainer",
                "tagline": "I review PRs and maintain clean documentation.",
                "domain": "work",
                "current_stage": "Experimenting",
            },
            db_path=self.db_path,
        )
        new_id = new_ident["id"]

        # 2. Create a new Habit linked to the new Identity
        new_habit = app.create_habit(
            {
                "title": "Reviewed community pull request",
                "two_minute_version": "Open PR queue and read the diff of 1 PR",
                "cadence": "daily",
                "category": "identity_habit",
                "identity_ids": [new_id],
            },
            db_path=self.db_path,
        )

        # 3. Log an action via habit_id only (auto-inherits title & identity_ids)
        app.create_action(
            {
                "habit_id": new_habit["id"],
                "action_date": "2026-10-26",
                "used_two_minute_rule": True,
            },
            db_path=self.db_path,
        )

        st = app.get_app_state(db_path=self.db_path, selected_date="2026-10-26", scope="week")
        self.assertEqual(len(st["identities"]), 7)
        oss_slice = next(s for s in st["chart"]["slices"] if s["identity_id"] == new_id)
        self.assertEqual(oss_slice["weighted_votes"], 1.0)
        self.assertEqual(oss_slice["percentage"], 100.0)

        # 4. Create & read custom Markdown guidance file
        saved_doc = app.save_guidance_document(
            {
                "id": "custom-stacking",
                "markdown": "# Custom Habit Stacking\n\n> After coffee, I write code.",
            },
            guidance_dir=self.guidance_dir,
        )
        self.assertEqual(saved_doc["id"], "custom-stacking")
        docs = app.load_guidance_documents(self.guidance_dir)
        self.assertEqual(len(docs), 1)
        self.assertEqual(docs[0]["title"], "Custom Habit Stacking")

    def test_04_weekly_review_auto_summary_and_persistence(self) -> None:
        app.init_db(db_path=self.db_path, seed_examples=True)
        st = app.get_app_state(db_path=self.db_path, scope="week")
        summary = st["weekly_review"]["auto_summary"]

        self.assertGreater(len(summary["supported_identities"]), 0)
        self.assertGreater(len(summary["neglected_identities"]), 0)

        app.save_weekly_review(
            {
                "week_start": st["week_start"],
                "answers": {"What identity did my actions support this week?": "Entrepreneur and Reader"},
                "one_adjustment": "Leave book on pillow every morning at 8am",
                "strongest_evidence": "Shipped core feature and read 15 pages",
                "next_smallest_action": "Read 2 pages before sleep",
                "overall_stage": "Becoming consistent",
                "system_checks": {"my_habits_were_realistic_for_my_current": True},
            },
            db_path=self.db_path,
        )

        st_after = app.get_app_state(db_path=self.db_path, scope="week")
        self.assertEqual(
            st_after["weekly_review"]["pinned_adjustment"]["one_adjustment"],
            "Leave book on pillow every morning at 8am",
        )
        self.assertEqual(
            st_after["weekly_review"]["saved"]["overall_stage"],
            "Becoming consistent",
        )

    def test_05_http_endpoints_end_to_end(self) -> None:
        app.init_db(db_path=self.db_path, seed_examples=True)
        app.IdentityOSRequestHandler.db_path = self.db_path
        app.IdentityOSRequestHandler.guidance_dir = app.GUIDANCE_DIR

        server = ThreadingHTTPServer(("127.0.0.1", 0), app.IdentityOSRequestHandler)
        port = server.server_address[1]
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()

        try:
            base_url = f"http://127.0.0.1:{port}"
            # 1. GET index.html
            with urllib.request.urlopen(f"{base_url}/") as resp:
                self.assertEqual(resp.status, 200)
                html = resp.read().decode("utf-8")
                self.assertIn("Identity Building OS", html)

            # 2. GET /api/state
            with urllib.request.urlopen(f"{base_url}/api/state?scope=week") as resp:
                self.assertEqual(resp.status, 200)
                data = json.loads(resp.read().decode("utf-8"))
                self.assertGreaterEqual(len(data["identities"]), 6)

            # 3. GET /api/guidance
            with urllib.request.urlopen(f"{base_url}/api/guidance") as resp:
                self.assertEqual(resp.status, 200)
                gdata = json.loads(resp.read().decode("utf-8"))
                self.assertGreaterEqual(len(gdata["documents"]), 3)
        finally:
            server.shutdown()
            server.server_close()


if __name__ == "__main__":
    unittest.main()
