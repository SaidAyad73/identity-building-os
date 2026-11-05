import json
import os
import sys
import tempfile
import threading
import unittest
import urllib.request
from http.server import ThreadingHTTPServer
from pathlib import Path

# Ensure root directory is on python path
ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

import app


class IdentityOSVerificationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.temp_dir.name) / "test_identity_os.db"
        self.guidance_dir = Path(self.temp_dir.name) / "guidance"
        self.old_env_db = os.environ.get("IDENTITY_OS_DB_PATH")
        os.environ["IDENTITY_OS_DB_PATH"] = str(self.db_path)
        app.DEFAULT_DB_PATH = self.db_path
        app.GUIDANCE_DIR = self.guidance_dir

    def tearDown(self) -> None:
        if self.old_env_db is not None:
            os.environ["IDENTITY_OS_DB_PATH"] = self.old_env_db
        else:
            os.environ.pop("IDENTITY_OS_DB_PATH", None)
        app.DEFAULT_DB_PATH = (app.ROOT_DIR / "data" / "identity_os.db").resolve()
        app.GUIDANCE_DIR = (app.ROOT_DIR / "guidance").resolve()
        self.temp_dir.cleanup()

    def test_01_resilient_bootstrap_and_schema(self) -> None:
        """Verify DB initializes with built-in default settings, identities, and habits."""
        app.init_db(db_path=self.db_path, seed_examples=False)
        state = app.get_app_state(db_path=self.db_path, scope="week")
        self.assertGreaterEqual(len(state["identities"]), 6)
        self.assertGreaterEqual(len(state["habits"]), 4)
        self.assertIn("stages", state["settings"])
        self.assertIn("reflection_questions", state["settings"])
        self.assertIn("anti_principle", state["settings"])

    def test_02_fractional_pie_chart_math_no_double_counting(self) -> None:
        app.init_db(db_path=self.db_path, seed_examples=False)
        state0 = app.get_app_state(db_path=self.db_path, selected_date="2026-10-26", scope="week")

        ident_ids = [i["id"] for i in state0["identities"]]
        ent_id, free_id, disc_id = ident_ids[0], ident_ids[1], ident_ids[4]

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

        app.create_action(
            {
                "title": "Shipped open-source module on schedule for client project",
                "action_date": "2026-10-27",
                "identity_ids": [ent_id, free_id, disc_id],
                "kind": "vote",
            },
            db_path=self.db_path,
        )

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
        self.assertAlmostEqual(slice_map[ent_id]["exact_weight"], 1.0 + 1.0 / 3.0, places=5)
        self.assertEqual(slice_map[ent_id]["raw_touches"], 2)
        self.assertAlmostEqual(slice_map[free_id]["exact_weight"], 0.5 + 1.0 / 3.0, places=5)
        self.assertEqual(slice_map[free_id]["raw_touches"], 2)
        self.assertAlmostEqual(slice_map[disc_id]["exact_weight"], 0.5 + 1.0 / 3.0, places=5)
        self.assertEqual(slice_map[disc_id]["raw_touches"], 2)

        day_state = app.get_app_state(db_path=self.db_path, selected_date="2026-10-26", scope="day")
        self.assertEqual(day_state["chart"]["total_votes"], 2)
        self.assertEqual(len(day_state["actions"]), 2)

    def test_03_system_extendability_crud_triggers_and_rules(self) -> None:
        """Verify adding habits with Rule 1 triggers and 4-rule metadata."""
        app.init_db(db_path=self.db_path, seed_examples=False)

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

        new_habit = app.create_habit(
            {
                "title": "Reviewed community pull request",
                "two_minute_version": "Open PR queue and read the diff of 1 PR",
                "cadence": "daily",
                "category": "identity_habit",
                "identity_ids": [new_id],
                "trigger_type": "time_location",
                "trigger_time": "10:00 AM",
                "trigger_location": "Home desk",
                "rule1_obvious": "Pin GitHub notifications tab to browser",
                "rule2_attractive": "Help open-source developers ship features",
                "rule3_easy": "Review smallest PR first (< 10 lines)",
                "rule4_satisfying": "Approve and merge",
            },
            db_path=self.db_path,
        )

        app.create_action(
            {
                "habit_id": new_habit["id"],
                "action_date": "2026-10-26",
                "used_two_minute_rule": True,
            },
            db_path=self.db_path,
        )

        st = app.get_app_state(db_path=self.db_path, selected_date="2026-10-26", scope="week")
        self.assertGreaterEqual(len(st["identities"]), 7)
        created_h = next(h for h in st["habits"] if h["id"] == new_habit["id"])
        self.assertEqual(created_h["trigger_type"], "time_location")
        self.assertEqual(created_h["trigger_time"], "10:00 AM")
        self.assertEqual(created_h["rule1_obvious"], "Pin GitHub notifications tab to browser")

        # Test updating habit rules & anti-identity inversion
        app.update_habit(
            new_habit["id"],
            {
                "title": "Reviewed PRs with diligence",
                "trigger_type": "habit_stack",
                "trigger_anchor": "After morning coffee",
                "rule1_obvious": "Updated stack trigger",
            },
            db_path=self.db_path,
        )
        st2 = app.get_app_state(db_path=self.db_path, selected_date="2026-10-26", scope="week")
        updated_h = next(h for h in st2["habits"] if h["id"] == new_habit["id"])
        self.assertEqual(updated_h["trigger_type"], "habit_stack")
        self.assertEqual(updated_h["trigger_anchor"], "After morning coffee")

    def test_04_timestamps_devote_and_delete_reflected_in_db_and_logs(self) -> None:
        app.init_db(db_path=self.db_path, seed_examples=False)
        st0 = app.get_app_state(db_path=self.db_path, selected_date="2026-10-26", scope="week")
        ident_id = st0["identities"][0]["id"]
        habit_id = st0["habits"][0]["id"]

        # 1. Verify action stores day, month, year, hour, minute, second in DB and logs
        created = app.create_action(
            {
                "habit_id": habit_id,
                "action_date": "2026-10-26",
                "identity_ids": [ident_id],
                "kind": "vote",
            },
            db_path=self.db_path,
        )
        self.assertEqual(created["day"], 26)
        self.assertEqual(created["month"], 10)
        self.assertEqual(created["year"], 2026)
        self.assertIsInstance(created["hour"], int)
        self.assertIsInstance(created["minute"], int)
        self.assertIsInstance(created["second"], int)
        self.assertRegex(created["timestamp"], r"^\d{2}/\d{2}/\d{4} \d{2}:\d{2}:\d{2}$")

        with app.connect_db(self.db_path) as conn:
            db_row = conn.execute("SELECT * FROM actions WHERE id = ?", (created["id"],)).fetchone()
            self.assertEqual(db_row["day"], 26)
            self.assertEqual(db_row["month"], 10)
            self.assertEqual(db_row["year"], 2026)
            self.assertTrue(0 <= db_row["hour"] <= 23)
            self.assertTrue(0 <= db_row["minute"] <= 59)
            self.assertTrue(0 <= db_row["second"] <= 59)

        st1 = app.get_app_state(db_path=self.db_path, selected_date="2026-10-26", scope="week")
        self.assertEqual(len(st1["actions"]), 1)
        self.assertRegex(st1["actions"][0]["timestamp_display"], r"^26/10/2026 \d{2}:\d{2}:\d{2}$")
        self.assertEqual(st1["chart"]["total_votes"], 1)

        # 2. Devote the voted habit -> removes the vote from DB & logs
        devote_res1 = app.devote_action(
            {"habit_id": habit_id, "action_date": "2026-10-26", "identity_ids": [ident_id]},
            db_path=self.db_path,
        )
        self.assertEqual(devote_res1["effect"], "removed_vote")
        st2 = app.get_app_state(db_path=self.db_path, selected_date="2026-10-26", scope="week")
        self.assertEqual(len(st2["actions"]), 0)
        self.assertEqual(st2["chart"]["total_votes"], 0)

        # 3. Cast 2 votes and then log a negative devote -> net votes = 1, both reflected in logs
        app.create_action({"title": "Vote A", "action_date": "2026-10-26", "identity_ids": [ident_id], "kind": "vote"}, db_path=self.db_path)
        app.create_action({"title": "Vote B", "action_date": "2026-10-26", "identity_ids": [ident_id], "kind": "vote"}, db_path=self.db_path)
        devote_res2 = app.devote_action(
            {"title": "Devote penalty", "action_date": "2026-10-26", "identity_ids": [ident_id], "mode": "log"},
            db_path=self.db_path,
        )
        self.assertEqual(devote_res2["effect"], "logged_devote")
        st3 = app.get_app_state(db_path=self.db_path, selected_date="2026-10-26", scope="week")
        self.assertEqual(st3["chart"]["total_votes"], 1)
        self.assertEqual(st3["chart"]["total_devotes"], 1)
        self.assertEqual(len(st3["actions"]), 3)

        # 4. Delete habit -> deletes habit and its associated actions from DB and logs
        app.create_action({"habit_id": habit_id, "action_date": "2026-10-26", "identity_ids": [ident_id], "kind": "vote"}, db_path=self.db_path)
        app.delete_habit(habit_id, db_path=self.db_path)
        st4 = app.get_app_state(db_path=self.db_path, selected_date="2026-10-26", scope="week")
        self.assertFalse(any(h["id"] == habit_id for h in st4["habits"]))
        self.assertFalse(any(a["habit_id"] == habit_id for a in st4["actions"]))

        # 5. Delete identity -> deletes identity and cleans up its exclusively linked habits & logs
        app.delete_identity(ident_id, db_path=self.db_path)
        st5 = app.get_app_state(db_path=self.db_path, selected_date="2026-10-26", scope="week")
        self.assertFalse(any(i["id"] == ident_id for i in st5["identities"]))
        self.assertFalse(any(ident_id in a["identity_ids"] for a in st5["actions"]))

    def test_05_weekly_review_and_http_endpoints(self) -> None:
        app.init_db(db_path=self.db_path, seed_examples=True)
        st = app.get_app_state(db_path=self.db_path, scope="week")
        rev_res = app.save_weekly_review(
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
        self.assertRegex(rev_res["review_date"], r"^\d{2}/\d{2}/\d{4} \d{2}:\d{2}:\d{2}$")

        app.IdentityOSRequestHandler.db_path = self.db_path
        app.IdentityOSRequestHandler.guidance_dir = app.GUIDANCE_DIR

        server = ThreadingHTTPServer(("127.0.0.1", 0), app.IdentityOSRequestHandler)
        port = server.server_address[1]
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()

        try:
            base_url = f"http://127.0.0.1:{port}"
            with urllib.request.urlopen(f"{base_url}/") as resp:
                self.assertEqual(resp.status, 200)
            with urllib.request.urlopen(f"{base_url}/api/state?scope=week") as resp:
                self.assertEqual(resp.status, 200)
                data = json.loads(resp.read().decode("utf-8"))
                self.assertGreaterEqual(len(data["identities"]), 6)
        finally:
            server.shutdown()
            server.server_close()

    def test_06_json_export_and_import_for_ai_agents(self) -> None:
        """Verify full database serialization and restoration via JSON for AI agents."""
        app.init_db(db_path=self.db_path, seed_examples=False)

        # 1. Export database to dict
        exported = app.export_database_to_dict(self.db_path, self.guidance_dir)
        self.assertEqual(exported["schema_version"], 1)
        self.assertIn("identities", exported)
        self.assertIn("habits", exported)
        self.assertIn("settings", exported)
        self.assertGreaterEqual(len(exported["identities"]), 6)

        # 2. Add an action and a custom habit with triggers
        habit_id = exported["habits"][0]["id"]
        ident_id = exported["identities"][0]["id"]
        app.create_action(
            {"title": "Agent action test", "action_date": "2026-11-05", "identity_ids": [ident_id], "habit_id": habit_id},
            db_path=self.db_path,
        )

        exported_with_action = app.export_database_to_dict(self.db_path, self.guidance_dir)
        self.assertEqual(len(exported_with_action["actions"]), 1)

        # 3. Create a fresh second database and import the exported state
        db_path_2 = Path(self.temp_dir.name) / "test_import_os.db"
        app.init_db(db_path=db_path_2, seed_examples=False)

        import_res = app.import_database_from_dict(exported_with_action, db_path=db_path_2, guidance_dir=self.guidance_dir, mode="replace")
        self.assertEqual(import_res["status"], "imported")
        self.assertEqual(import_res["actions_count"], 1)

        st2 = app.get_app_state(db_path=db_path_2, selected_date="2026-11-05", scope="day")
        self.assertEqual(len(st2["actions"]), 1)
        self.assertEqual(st2["actions"][0]["title"], "Agent action test")

        # 4. Test merge mode: add new habit via JSON merge
        merge_payload = {
            "habits": [
                {
                    "id": "habit_agent_created",
                    "title": "Created autonomously by AI Agent",
                    "cadence": "daily",
                    "two_minute_version": "Spend 2 min on AI prompt",
                    "category": "identity_habit",
                    "sort_order": 99,
                    "active": 1,
                    "identity_ids": [ident_id],
                    "trigger_type": "time_location",
                    "trigger_time": "11:00 AM",
                    "trigger_location": "Terminal",
                    "rule1_obvious": "Schedule automated agent run",
                    "rule2_attractive": "Rapid progress",
                    "rule3_easy": "One command",
                    "rule4_satisfying": "Green test pass",
                }
            ]
        }
        merge_res = app.import_database_from_dict(merge_payload, db_path=db_path_2, guidance_dir=self.guidance_dir, mode="merge")
        self.assertEqual(merge_res["status"], "imported")
        st3 = app.get_app_state(db_path=db_path_2, scope="week")
        self.assertTrue(any(h["id"] == "habit_agent_created" for h in st3["habits"]))

    def test_07_cli_and_rest_export_import(self) -> None:
        """Verify CLI flags --export / --import and REST /api/export /api/import."""
        app.init_db(db_path=self.db_path, seed_examples=False)
        json_file = Path(self.temp_dir.name) / "cli_backup.json"

        # Test CLI export explicitly targeted to test db
        handled_export = app.handle_cli_args(["--db", str(self.db_path), "--export", str(json_file)])
        self.assertTrue(handled_export)
        self.assertTrue(json_file.is_file())
        exported_data = json.loads(json_file.read_text(encoding="utf-8"))
        self.assertEqual(exported_data["schema_version"], 1)

        # Test CLI import explicitly targeted to test db
        handled_import = app.handle_cli_args(["--db", str(self.db_path), "--import", str(json_file), "--merge"])
        self.assertTrue(handled_import)

        # Test HTTP REST export and import
        app.IdentityOSRequestHandler.db_path = self.db_path
        app.IdentityOSRequestHandler.guidance_dir = app.GUIDANCE_DIR

        server = ThreadingHTTPServer(("127.0.0.1", 0), app.IdentityOSRequestHandler)
        port = server.server_address[1]
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()

        try:
            base_url = f"http://127.0.0.1:{port}"

            with urllib.request.urlopen(f"{base_url}/api/export") as resp:
                self.assertEqual(resp.status, 200)
                data = json.loads(resp.read().decode("utf-8"))
                self.assertIn("identities", data)
                self.assertIn("habits", data)

            import_req = urllib.request.Request(
                f"{base_url}/api/import",
                data=json.dumps({"mode": "merge", "data": exported_data}).encode("utf-8"),
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            with urllib.request.urlopen(import_req) as resp:
                self.assertEqual(resp.status, 200)
                res_json = json.loads(resp.read().decode("utf-8"))
                self.assertEqual(res_json["status"], "imported")
        finally:
            server.shutdown()
            server.server_close()

    def test_08_fail_loudly_no_silent_swallows(self) -> None:
        """Verify errors are propagated loudly rather than silently swallowed."""
        app.init_db(db_path=self.db_path, seed_examples=False)

        # 1. Invalid date format must raise ValueError
        with self.assertRaises(ValueError):
            app.build_timestamp_fields("not-a-valid-date")

        # 2. Invalid action kind must raise ValueError
        with self.assertRaises(ValueError):
            app.create_action(
                {"title": "Test", "identity_ids": ["entrepreneur"], "kind": "invalid_kind"},
                db_path=self.db_path,
            )

        # 3. Invalid identity ID must raise ValueError
        with self.assertRaises(ValueError):
            app.create_action(
                {"title": "Test", "identity_ids": ["non_existent_identity_id"], "kind": "vote"},
                db_path=self.db_path,
            )

        # 4. Invalid devote mode must raise ValueError
        with self.assertRaises(ValueError):
            app.devote_action(
                {"title": "Test", "mode": "unsupported_mode"},
                db_path=self.db_path,
            )

        # 5. Corrupted JSON in settings must raise ValueError
        with app.connect_db(self.db_path) as conn:
            conn.execute("INSERT OR REPLACE INTO settings (key, value_json) VALUES ('corrupted_key', '{not_json}')")
            with self.assertRaises(ValueError):
                app.get_settings(conn)


if __name__ == "__main__":
    unittest.main()
