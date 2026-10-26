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
        self.assertEqual(len(parsed["habits"]), 27)
        self.assertEqual(len(parsed["examples"]), 5)
        self.assertEqual(len(parsed["reflection_questions"]), 4)
        self.assertEqual(len(parsed["stages"]), 5)
        self.assertIn("not trying to eliminate fun", parsed["anti_principle"])

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

    def test_03_system_extendability_crud_identities_habits_and_guidance(self) -> None:
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
        self.assertEqual(len(st["identities"]), 7)
        oss_slice = next(s for s in st["chart"]["slices"] if s["identity_id"] == new_id)
        self.assertEqual(oss_slice["weighted_votes"], 1.0)
        self.assertEqual(oss_slice["percentage"], 100.0)

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


if __name__ == "__main__":
    unittest.main()
