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

    def _seed_test_identities_and_habits(self) -> tuple[list[str], list[str]]:
        ident_specs = [
            {"name": "Focused Craftsperson", "domain": "work"},
            {"name": "Lifelong Learner", "domain": "growth"},
            {"name": "Consistent Planner", "domain": "work"},
        ]
        ident_ids = [app.create_identity(spec, db_path=self.db_path)["id"] for spec in ident_specs]

        habit_specs = [
            {
                "title": "Complete 60m deep-work block",
                "identity_ids": [ident_ids[0], ident_ids[2]],
                "rule1_obvious": "At 9:00 AM at clean desk",
                "rule2_attractive": "Brew coffee before starting",
                "rule3_easy": "Open file and write 2 lines",
                "rule4_satisfying": "Cast a vote immediately",
            },
            {
                "title": "Read 15 pages",
                "identity_ids": [ident_ids[1]],
                "rule1_obvious": "Book on pillow",
                "rule2_attractive": "Choose an engaging topic",
                "rule3_easy": "Read 1 page",
                "rule4_satisfying": "Log reading vote",
            },
        ]
        habit_ids = [app.create_habit(spec, db_path=self.db_path)["id"] for spec in habit_specs]
        return ident_ids, habit_ids

    def test_01_empty_bootstrap_and_no_invented_fallbacks(self) -> None:
        """Verify DB initializes cleanly with 0 identities/habits and never invents fallback strings."""
        app.init_db(db_path=self.db_path)
        state = app.get_app_state(db_path=self.db_path, scope="week")
        self.assertEqual(state["identities"], [])
        self.assertEqual(state["habits"], [])
        self.assertEqual(state["actions"], [])
        self.assertEqual(state["chart"]["total_votes"], 0)
        self.assertEqual(state["chart"]["slices"], [])

        # Creating an identity without a tagline leaves tagline as ""
        ident = app.create_identity({"name": "Writer"}, db_path=self.db_path)
        # Creating a habit without two_minute_version or rules leaves them as ""
        habit = app.create_habit(
            {"title": "Write 200 words", "identity_ids": [ident["id"]]},
            db_path=self.db_path,
        )

        st2 = app.get_app_state(db_path=self.db_path, scope="week")
        self.assertEqual(st2["identities"][0]["tagline"], "")
        created_h = st2["habits"][0]
        self.assertEqual(created_h["id"], habit["id"])
        self.assertEqual(created_h["two_minute_version"], "")
        self.assertEqual(created_h["rule1_obvious"], "")
        self.assertEqual(created_h["rule2_attractive"], "")
        self.assertEqual(created_h["rule3_easy"], "")
        self.assertEqual(created_h["rule4_satisfying"], "")

    def test_02_fractional_pie_chart_math_no_double_counting(self) -> None:
        app.init_db(db_path=self.db_path)
        ident_ids, _ = self._seed_test_identities_and_habits()
        craft_id, learn_id, plan_id = ident_ids[0], ident_ids[1], ident_ids[2]

        app.create_action(
            {
                "title": "Completed 60m deep-work block",
                "action_date": "2026-10-26",
                "identity_ids": [craft_id],
                "evidence_note": "Finished core module",
                "kind": "vote",
            },
            db_path=self.db_path,
        )

        app.create_action(
            {
                "title": "Started morning study session at 8:00 AM sharp",
                "action_date": "2026-10-26",
                "identity_ids": [learn_id, plan_id],
                "used_two_minute_rule": True,
                "kind": "vote",
            },
            db_path=self.db_path,
        )

        app.create_action(
            {
                "title": "Published technical study notes on schedule",
                "action_date": "2026-10-27",
                "identity_ids": [craft_id, learn_id, plan_id],
                "kind": "vote",
            },
            db_path=self.db_path,
        )

        app.create_action(
            {
                "title": "Checked notifications late at night",
                "action_date": "2026-10-27",
                "identity_ids": [plan_id],
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
        self.assertAlmostEqual(slice_map[craft_id]["exact_weight"], 1.0 + 1.0 / 3.0, places=5)
        self.assertEqual(slice_map[craft_id]["raw_touches"], 2)
        self.assertAlmostEqual(slice_map[learn_id]["exact_weight"], 0.5 + 1.0 / 3.0, places=5)
        self.assertEqual(slice_map[learn_id]["raw_touches"], 2)
        self.assertAlmostEqual(slice_map[plan_id]["exact_weight"], 0.5 + 1.0 / 3.0, places=5)
        self.assertEqual(slice_map[plan_id]["raw_touches"], 2)

        day_state = app.get_app_state(db_path=self.db_path, selected_date="2026-10-26", scope="day")
        self.assertEqual(day_state["chart"]["total_votes"], 2)
        self.assertEqual(len(day_state["actions"]), 2)

    def test_03_system_extendability_crud_and_four_laws_rules(self) -> None:
        """Verify adding and updating habits with the 4 simple rule strings."""
        app.init_db(db_path=self.db_path)

        new_ident = app.create_identity(
            {
                "name": "Mindful Practitioner",
                "tagline": "I practice daily mindfulness and deliberate breathing.",
                "domain": "growth",
                "current_stage": "Experimenting",
            },
            db_path=self.db_path,
        )
        new_id = new_ident["id"]

        new_habit = app.create_habit(
            {
                "title": "Complete 10 minutes of morning breathwork",
                "two_minute_version": "Sit on the cushion and take 3 slow breaths",
                "cadence": "daily",
                "category": "identity_habit",
                "identity_ids": [new_id],
                "rule1_obvious": "Place meditation cushion in the center of the room at 7:00 AM",
                "rule2_attractive": "Enjoy a calm, unhurried start before opening any screens",
                "rule3_easy": "Sit on the cushion and take 3 slow breaths",
                "rule4_satisfying": "Record a mindfulness vote immediately after finishing",
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
        self.assertEqual(len(st["identities"]), 1)
        created_h = next(h for h in st["habits"] if h["id"] == new_habit["id"])
        self.assertEqual(created_h["rule1_obvious"], "Place meditation cushion in the center of the room at 7:00 AM")
        self.assertEqual(created_h["rule2_attractive"], "Enjoy a calm, unhurried start before opening any screens")
        self.assertEqual(created_h["rule3_easy"], "Sit on the cushion and take 3 slow breaths")
        self.assertEqual(created_h["rule4_satisfying"], "Record a mindfulness vote immediately after finishing")

        app.update_habit(
            new_habit["id"],
            {
                "title": "Complete 15 minutes of morning breathwork",
                "rule1_obvious": "After pouring morning water, sit on the cushion immediately",
                "rule3_easy": "Take 5 slow breaths with eyes closed",
            },
            db_path=self.db_path,
        )
        st2 = app.get_app_state(db_path=self.db_path, selected_date="2026-10-26", scope="week")
        updated_h = next(h for h in st2["habits"] if h["id"] == new_habit["id"])
        self.assertEqual(updated_h["rule1_obvious"], "After pouring morning water, sit on the cushion immediately")
        self.assertEqual(updated_h["rule3_easy"], "Take 5 slow breaths with eyes closed")
        self.assertEqual(updated_h["two_minute_version"], "Take 5 slow breaths with eyes closed")

    def test_04_timestamps_devote_and_delete_reflected_in_db_and_logs(self) -> None:
        app.init_db(db_path=self.db_path)
        ident_ids, habit_ids = self._seed_test_identities_and_habits()
        ident_id = ident_ids[0]
        habit_id = habit_ids[0]

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

        devote_res1 = app.devote_action(
            {"habit_id": habit_id, "action_date": "2026-10-26", "identity_ids": [ident_id]},
            db_path=self.db_path,
        )
        self.assertEqual(devote_res1["effect"], "removed_vote")
        st2 = app.get_app_state(db_path=self.db_path, selected_date="2026-10-26", scope="week")
        self.assertEqual(len(st2["actions"]), 0)
        self.assertEqual(st2["chart"]["total_votes"], 0)

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

        app.create_action({"habit_id": habit_id, "action_date": "2026-10-26", "identity_ids": [ident_id], "kind": "vote"}, db_path=self.db_path)
        app.delete_habit(habit_id, db_path=self.db_path)
        st4 = app.get_app_state(db_path=self.db_path, selected_date="2026-10-26", scope="week")
        self.assertFalse(any(h["id"] == habit_id for h in st4["habits"]))
        self.assertFalse(any(a["habit_id"] == habit_id for a in st4["actions"]))

        app.delete_identity(ident_id, db_path=self.db_path)
        st5 = app.get_app_state(db_path=self.db_path, selected_date="2026-10-26", scope="week")
        self.assertFalse(any(i["id"] == ident_id for i in st5["identities"]))
        self.assertFalse(any(ident_id in a["identity_ids"] for a in st5["actions"]))

    def test_05_weekly_review_and_http_endpoints(self) -> None:
        app.init_db(db_path=self.db_path)
        self._seed_test_identities_and_habits()
        st = app.get_app_state(db_path=self.db_path, scope="week")
        rev_res = app.save_weekly_review(
            {
                "week_start": st["week_start"],
                "answers": {"What identity did my actions support this week?": "Focused Craftsperson and Lifelong Learner"},
                "one_adjustment": "Leave book on pillow every morning at 8:00 AM",
                "strongest_evidence": "Completed deep-work blocks and read 15 pages daily",
                "next_smallest_action": "Read 1 page before sleep",
                "overall_stage": "Becoming consistent",
                "system_checks": {"system_realistic": True},
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
                self.assertEqual(len(data["identities"]), 3)

            # Simulate windowless pythonw.exe (sys.stderr = None) with verbose logging enabled
            old_stderr = sys.stderr
            old_verbose = os.environ.get("IDENTITY_OS_VERBOSE")
            try:
                sys.stderr = None
                os.environ["IDENTITY_OS_VERBOSE"] = "1"
                with urllib.request.urlopen(f"{base_url}/") as resp:
                    self.assertEqual(resp.status, 200)
            finally:
                sys.stderr = old_stderr
                if old_verbose is not None:
                    os.environ["IDENTITY_OS_VERBOSE"] = old_verbose
                else:
                    os.environ.pop("IDENTITY_OS_VERBOSE", None)
        finally:
            server.shutdown()
            server.server_close()

    def test_06_json_export_and_import_identities_and_habits_only(self) -> None:
        """Verify export/import only touches identities and habits and never exposes or wipes actions/reviews."""
        app.init_db(db_path=self.db_path)
        ident_ids, habit_ids = self._seed_test_identities_and_habits()
        ident_id = ident_ids[0]
        habit_id = habit_ids[0]

        app.create_action(
            {"title": "Logged user action that must stay untouched", "action_date": "2026-11-05", "identity_ids": [ident_id], "habit_id": habit_id},
            db_path=self.db_path,
        )
        app.save_weekly_review(
            {"week_start": "2026-11-02", "one_adjustment": "Keep desk clear"},
            db_path=self.db_path,
        )

        exported = app.export_database_to_dict(self.db_path, self.guidance_dir)
        self.assertEqual(exported["schema_version"], 1)
        self.assertIn("identities", exported)
        self.assertIn("habits", exported)
        self.assertNotIn("actions", exported)
        self.assertNotIn("weekly_reviews", exported)
        self.assertNotIn("settings", exported)
        self.assertNotIn("guidance", exported)

        merge_payload = {
            "habits": [
                {
                    "id": "habit_shared_setup",
                    "title": "Practice 20 minutes of deliberate skill drills",
                    "cadence": "daily",
                    "two_minute_version": "Open practice material for 2 minutes",
                    "category": "identity_habit",
                    "sort_order": 99,
                    "active": 1,
                    "identity_ids": [ident_id],
                    "rule1_obvious": "Keep practice notebook on desk",
                    "rule2_attractive": "Track visible skill mastery",
                    "rule3_easy": "Open practice material for 2 minutes",
                    "rule4_satisfying": "Cast a vote after finishing the drill",
                }
            ]
        }
        merge_res = app.import_database_from_dict(merge_payload, db_path=self.db_path, mode="merge")
        self.assertEqual(merge_res["status"], "imported")

        st_after_merge = app.get_app_state(db_path=self.db_path, selected_date="2026-11-05", scope="day")
        self.assertTrue(any(h["id"] == "habit_shared_setup" for h in st_after_merge["habits"]))
        self.assertEqual(len(st_after_merge["actions"]), 1)
        self.assertEqual(st_after_merge["actions"][0]["title"], "Logged user action that must stay untouched")
        self.assertEqual(st_after_merge["weekly_review"]["pinned_adjustment"]["one_adjustment"], "Keep desk clear")

        replace_res = app.import_database_from_dict(exported, db_path=self.db_path, mode="replace")
        self.assertEqual(replace_res["status"], "imported")
        st_after_replace = app.get_app_state(db_path=self.db_path, selected_date="2026-11-05", scope="day")
        self.assertFalse(any(h["id"] == "habit_shared_setup" for h in st_after_replace["habits"]))
        self.assertEqual(len(st_after_replace["actions"]), 1)
        self.assertEqual(st_after_replace["weekly_review"]["pinned_adjustment"]["one_adjustment"], "Keep desk clear")

    def test_07_cli_and_rest_export_import(self) -> None:
        """Verify CLI flags --export / --import and REST /api/export /api/import."""
        app.init_db(db_path=self.db_path)
        self._seed_test_identities_and_habits()
        json_file = Path(self.temp_dir.name) / "cli_habits.json"

        handled_export = app.handle_cli_args(["--db", str(self.db_path), "--export", str(json_file)])
        self.assertTrue(handled_export)
        self.assertTrue(json_file.is_file())
        exported_data = json.loads(json_file.read_text(encoding="utf-8"))
        self.assertEqual(exported_data["schema_version"], 1)
        self.assertIn("identities", exported_data)
        self.assertIn("habits", exported_data)
        self.assertNotIn("actions", exported_data)

        handled_import = app.handle_cli_args(["--db", str(self.db_path), "--import", str(json_file)])
        self.assertTrue(handled_import)

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
                self.assertNotIn("actions", data)

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
        app.init_db(db_path=self.db_path)

        with self.assertRaises(ValueError):
            app.slugify("!!!")

        with self.assertRaises(ValueError):
            app.build_timestamp_fields("not-a-valid-date")

        with self.assertRaises(ValueError):
            app.create_action(
                {"title": "Test", "identity_ids": ["focused_craftsperson"], "kind": "invalid_kind"},
                db_path=self.db_path,
            )

        with self.assertRaises(ValueError):
            app.create_action(
                {"title": "Test", "identity_ids": ["non_existent_identity_id"], "kind": "vote"},
                db_path=self.db_path,
            )

        with self.assertRaises(ValueError):
            app.devote_action(
                {"title": "Test", "mode": "unsupported_mode"},
                db_path=self.db_path,
            )

        with self.assertRaises(ValueError):
            app.import_database_from_dict({"identities": []}, db_path=self.db_path, mode="invalid_mode")

        with self.assertRaises(ValueError):
            app.handle_cli_args(["--export"])

        with self.assertRaises(ValueError):
            app.handle_cli_args(["--import"])


if __name__ == "__main__":
    unittest.main()
