"""CLI behavior checks; all writes stay in isolated temporary directories."""

import importlib.machinery
import importlib.util
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import unittest
from unittest import mock


SCRIPT = Path(__file__).resolve().parents[1] / "eat"
loader = importlib.machinery.SourceFileLoader("eat_cli", str(SCRIPT))
spec = importlib.util.spec_from_loader(loader.name, loader)
eat = importlib.util.module_from_spec(spec)
loader.exec_module(eat)


class TerminalText(io.StringIO):
    def isatty(self):
        return True


class EatCLI(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.env = dict(os.environ, EAT_HOME=self.tmp.name)
        self.path = Path(self.tmp.name) / "state.json"

    def run_cli(self, *args, status=0):
        result = subprocess.run([sys.executable, str(SCRIPT), *args], env=self.env,
                                capture_output=True, text=True, timeout=5)
        self.assertEqual(result.returncode, status, result.stderr)
        self.assertNotIn("Traceback", result.stderr)
        return result

    def state(self):
        return json.loads(self.path.read_text())

    def run_terminal(self, args=None, chance=0.99):
        output = TerminalText()
        pauses = []
        with mock.patch.dict(os.environ, self.env), \
                mock.patch.object(sys, "stdin", io.StringIO()), \
                mock.patch.object(sys, "stdout", output), \
                mock.patch("builtins.input", side_effect=AssertionError("Must never prompt")), \
                mock.patch.object(eat.random, "random", return_value=chance), \
                mock.patch.object(eat.time, "sleep", side_effect=lambda seconds: pauses.append((seconds, output.getvalue()))):
            self.assertEqual(eat.main(args or []), 0)
        return output.getvalue(), pauses

    def test_terminal_suggests_once_and_exits_without_input_or_delay(self):
        output, pauses = self.run_terminal()
        self.assertIn("No idea? I've got you.", output)
        self.assertNotIn("[Enter]", output)
        self.assertNotIn("[n]", output)
        self.assertEqual(pauses, [])
        self.assertEqual(len(self.state()["history"]), 1)

    def test_ctrl_c_stops_animation_without_a_traceback(self):
        with mock.patch.dict(os.environ, self.env), \
                mock.patch.object(sys, "stdin", io.StringIO()), \
                mock.patch.object(sys, "stdout", TerminalText()) as output, \
                mock.patch.object(eat.time, "sleep", side_effect=KeyboardInterrupt):
            self.assertEqual(eat.main(["--chaos"]), 130)
        self.assertIn("Dinner can wait", output.getvalue())
        self.assertNotIn("Traceback", output.getvalue())

    def test_redirected_output_has_no_prompts_animation_or_delays(self):
        output = io.StringIO()
        with mock.patch.dict(os.environ, self.env), \
                mock.patch.object(sys, "stdout", output), \
                mock.patch("builtins.input", side_effect=AssertionError("Must never prompt")), \
                mock.patch.object(eat.time, "sleep", side_effect=AssertionError("Must not delay a pipe")):
            self.assertEqual(eat.main(["--chaos"]), 0)
        output = output.getvalue()
        self.assertNotIn("[Enter]", output)
        self.assertNotIn("No idea?", output)
        self.assertNotIn("Thinking...", output)
        self.assertNotIn("\r", output)

    def test_overthinking_is_occasional_and_respects_filters(self):
        normal, _ = self.run_terminal(chance=0.99)
        theatrical, _ = self.run_terminal(args=["--quick", "--cheap", "--vegetarian"], chance=0.0)
        self.assertNotIn("Thinking...", normal)
        self.assertIn("Thinking...", theatrical)
        self.assertGreater(len(theatrical) - len(normal), 500)
        chosen = next(item for item in eat.MEALS if item["id"] == self.state()["history"][-1]["id"])
        self.assertLessEqual(chosen["minutes"], 15)
        self.assertTrue(chosen["cheap"] and chosen["vegetarian"])
        self.assertLess(theatrical.index("Let's go with:"), theatrical.rindex(chosen["name"]))

    def test_overthinking_reveals_steps_progressively_then_finishes(self):
        output, pauses = self.run_terminal(args=["--chaos"])
        self.assertIn("Thinking...", pauses[0][1])
        self.assertIn("Okay. Something to", pauses[0][1])
        self.assertNotIn("This should be a small decision.", pauses[0][1])
        self.assertIn("Enough. This one.", pauses[-1][1])
        self.assertNotIn("Let's go with:", pauses[-1][1])
        self.assertIn("Let's go with:", output)
        self.assertTrue(all(seconds > 0 for seconds, _ in pauses))
        self.assertGreater(sum(seconds for seconds, _ in pauses), 20)
        self.assertLess(sum(seconds for seconds, _ in pauses), 40)
        self.assertEqual(output.count("Thinking..."), 1)
        self.assertEqual(len(self.state()["history"]), 1)
        chosen = next(item for item in eat.MEALS if item["id"] == self.state()["history"][-1]["id"])
        self.assertIn(chosen["name"], output)
        self.assertNotIn("[Enter]", output)
        self.assertNotIn("committee", output.lower())

    def test_longer_thoughts_get_more_reading_time_after_text_is_visible(self):
        durations = []
        for thought in ("Maybe noodles.", "Wait, I should probably consider how much effort this dinner actually needs."):
            output = io.StringIO()
            pauses = []
            with mock.patch.object(sys, "stdout", output), \
                    mock.patch.object(sys, "stdin", io.StringIO()), \
                    mock.patch.object(eat.time, "sleep", side_effect=lambda seconds: pauses.append((seconds, output.getvalue()))):
                eat.stream_thought(thought)
            self.assertIn(thought, " ".join(pauses[-1][1].split()))
            self.assertGreaterEqual(pauses[-1][0], 0.5)
            durations.append(sum(seconds for seconds, _ in pauses))
        self.assertGreater(durations[1], durations[0])

    def test_enter_during_a_reading_pause_reveals_meal_and_skips_later_thinking(self):
        def press_enter_during_reading(seconds):
            if seconds > 0.5:
                raise eat.SkipThinking

        with mock.patch.object(eat, "thinking_pause", side_effect=press_enter_during_reading):
            output, _ = self.run_terminal(args=["--chaos", "--vegetarian"])
        self.assertIn("This should be a small decision.", output)
        self.assertIn("Overthinking skipped. Let's go with:", output)
        self.assertNotIn("Enough. This one.", output)
        self.assertTrue(self.state()["history"][-1]["thought"])
        chosen = next(item for item in eat.MEALS if item["id"] == self.state()["history"][-1]["id"])
        self.assertTrue(chosen["vegetarian"])
        self.assertIn(chosen["name"], output)
        again, pauses = self.run_terminal(args=["--chaos"])
        self.assertIn("Overthinking interrupted", again)
        self.assertIn("This should be a small decision.", again)
        self.assertGreater(sum(seconds for seconds, _ in pauses), 0)
        self.assertLess(sum(seconds for seconds, _ in pauses), 2)

    def test_completed_thinking_is_remembered_across_requests(self):
        first, pauses = self.run_terminal(args=["--chaos"])
        self.assertTrue(pauses)
        self.assertIn("Enough. This one.", first)
        for _ in range(3):
            following, pauses = self.run_terminal(args=["--chaos"])
            self.assertIn("Okay. Something to eat.", following)
            self.assertIn("Start with", following)
            self.assertIn("— wait. No. Dinner first.", following)
            self.assertIn("Overthinking interrupted", following)
            self.assertNotIn("Wait. Is the first idea good", following)
            self.assertNotIn("Straight to the food", following)
            self.assertNotIn("Start with", pauses[0][1])
            self.assertIn("Start with", pauses[-1][1])
            self.assertGreater(sum(seconds for seconds, _ in pauses), 0)
            self.assertLess(sum(seconds for seconds, _ in pauses), 2)
        self.assertEqual(sum(item["thought"] for item in self.state()["history"]), 1)

    def test_enter_also_skips_the_abbreviated_thinking(self):
        self.run_terminal(args=["--chaos"])
        with mock.patch.object(eat, "thinking_pause", side_effect=eat.SkipThinking):
            output, _ = self.run_terminal(args=["--chaos"])
        self.assertIn("Overthinking skipped. Let's go with:", output)
        self.assertNotIn("Overthinking interrupted", output)
        self.assertEqual(sum(item["thought"] for item in self.state()["history"]), 1)

    def test_reset_and_streak_expiry_allow_full_thinking_again(self):
        self.run_terminal(args=["--chaos"])
        self.run_cli("reset")
        _, pauses = self.run_terminal(args=["--chaos"])
        self.assertTrue(pauses)
        state = self.state()
        state["history"][-1]["at"] = time.time() - 125
        self.path.write_text(json.dumps(state))
        _, pauses = self.run_terminal(args=["--chaos"])
        self.assertTrue(pauses)

    @unittest.skipUnless(os.name == "posix", "Uses a real POSIX terminal")
    def test_enter_skips_in_a_real_terminal(self):
        import pty
        import select

        master, slave = pty.openpty()
        process = None
        output = bytearray()
        try:
            process = subprocess.Popen([sys.executable, str(SCRIPT), "--chaos"],
                                       stdin=slave, stdout=slave, stderr=slave, env=self.env)
            # Keep the parent slave descriptor open while draining output; on macOS,
            # closing the last slave can discard unread terminal output.
            deadline = time.monotonic() + 5
            while b"Okay. Something to" not in output and time.monotonic() < deadline:
                if select.select([master], [], [], 0.1)[0]:
                    output.extend(os.read(master, 4096))
            self.assertIn(b"Press Enter to skip", output)
            self.assertIn(b"Okay. Something to", output)
            os.write(master, b"\n")
            process.wait(timeout=2)
            while select.select([master], [], [], 0.1)[0]:
                try:
                    chunk = os.read(master, 4096)
                except OSError:
                    break
                if not chunk:
                    break
                output.extend(chunk)
            self.assertEqual(process.returncode, 0, output.decode(errors="replace"))
            self.assertIn(b"Overthinking skipped. Let's go with:", output)
            self.assertNotIn(b"Enough. This one.", output)
            self.assertEqual(len(self.state()["history"]), 1)
            self.assertTrue(self.state()["history"][0]["thought"])
        finally:
            if process is not None and process.poll() is None:
                process.kill()
                process.wait()
            os.close(master)
            if slave is not None:
                os.close(slave)

    def test_monologue_uses_available_alternatives_and_handles_a_single_meal(self):
        options = [item for item in eat.MEALS if item["vegetarian"] and item["cheap"]][:2]
        steps = " ".join(eat.thinking_steps(options[0], options))
        self.assertIn(options[1]["name"], steps)
        self.assertIn(options[0]["name"], steps)
        custom = eat.meal("custom-one", "Family dinner", None, False, False, "A familiar meal.")
        steps = " ".join(eat.thinking_steps(custom, [custom]))
        self.assertIn("Family dinner", steps)
        self.assertNotIn("None", steps)

    def test_help_and_list_are_read_only(self):
        self.assertIn("Dinner has been decided", self.run_cli("--help").stdout)
        self.assertIn("60 meals", self.run_cli("list").stdout)
        self.assertFalse(self.path.exists())

    def test_expanded_catalog_is_valid_and_has_unique_entries(self):
        self.assertEqual(len(eat.MEALS), 60)
        self.assertTrue(all(eat.valid_meal(item) for item in eat.MEALS))
        self.assertEqual(len({item["id"] for item in eat.MEALS}), 60)
        self.assertEqual(len({item["name"].casefold() for item in eat.MEALS}), 60)
        quick = self.run_cli("list", "--quick", "--cheap", "--vegetarian").stdout
        self.assertIn("Tomato and egg stir-fry", quick)
        self.assertIn("Lentil rice bowl", quick)
        self.assertNotIn("Chicken fajitas", quick)

    def test_every_builtin_has_preparation_and_diet_tags(self):
        for item in eat.MEALS:
            with self.subTest(meal=item["name"]):
                tags = eat.describe(item).split(" · ")
                self.assertGreaterEqual(len(tags), 3)
                self.assertIn(item["method"], tags)
                self.assertIn("vegetarian" if item["vegetarian"] else item["diet"], tags)
        catalog = {item["id"]: item for item in eat.MEALS}
        self.assertEqual(eat.describe(catalog["salmon"]), "25 min · fish · oven")
        self.assertIn("poultry", eat.describe(catalog["chicken-fajitas"]))
        self.assertIn("no cook", eat.describe(catalog["hummus-plate"]))
        self.assertNotIn("cheap", eat.describe(catalog["salmon"]))

    def test_personal_meals_without_extra_metadata_still_have_a_tag(self):
        self.run_cli("add", "Family dinner", "--minutes", "25")
        saved = self.state()["meals"][0]
        self.assertEqual(eat.describe(saved), "25 min · personal meal")
        self.assertIn("Family dinner — 25 min · personal meal", self.run_cli("list").stdout)
        self.assertNotIn("Family dinner", self.run_cli("list", "--vegetarian").stdout)

    def test_fifteen_picks_then_refusal_with_distinct_late_remarks(self):
        outputs = [self.run_cli().stdout for _ in range(15)]
        self.assertEqual(len(self.state()["history"]), 15)
        late_remarks = [output.strip().splitlines()[-1] for output in outputs[7:]]
        self.assertEqual(len(set(late_remarks)), 8)
        self.assertIn("Last suggestion", outputs[-1])
        before = self.path.read_bytes()
        refused = self.run_cli(status=1)
        self.assertEqual(refused.stdout, "")
        self.assertIn("No more suggestions", refused.stderr)
        self.assertIn("./eat reset", refused.stderr)
        self.assertEqual(self.path.read_bytes(), before)
        self.run_cli("list")
        self.run_cli("add", "Comfort dinner")
        self.run_cli("--quick", "--chaos", status=1)
        self.assertEqual(len(self.state()["history"]), 15)

    def test_refusal_skips_thinking_in_a_terminal(self):
        self.run_cli()
        state = self.state()
        state["history"] = [{"id": eat.MEALS[0]["id"], "at": time.time()} for _ in range(15)]
        self.path.write_text(json.dumps(state))
        with mock.patch.dict(os.environ, self.env), \
                mock.patch.object(sys, "stdout", TerminalText()) as output, \
                mock.patch.object(sys, "stderr", io.StringIO()), \
                mock.patch.object(eat.time, "sleep", side_effect=AssertionError("Refusal must be immediate")):
            self.assertEqual(eat.main(["--chaos"]), 1)
        self.assertEqual(output.getvalue(), "")

    def test_reset_preserves_personal_meals_and_preferences(self):
        self.run_cli("add", "Family supper", "--minutes", "10", "--vegetarian")
        state = self.state()
        state["preferences"] = {"vegetarian": True}
        state["history"] = [{"id": eat.MEALS[0]["id"], "at": time.time()} for _ in range(15)]
        self.path.write_text(json.dumps(state))
        self.run_cli(status=1)
        self.assertIn("Fresh start", self.run_cli("reset").stdout)
        reset = self.state()
        self.assertEqual(reset["history"], [])
        self.assertEqual(reset["meals"], state["meals"])
        self.assertEqual(reset["preferences"], state["preferences"])
        self.run_cli()
        self.assertEqual(len(self.state()["history"]), 1)
        self.run_cli("reset")
        self.run_cli("reset")
        self.assertEqual(self.state()["history"], [])

    def test_expired_streak_allows_another_pick(self):
        self.run_cli()
        state = self.state()
        state["history"] = [{"id": eat.MEALS[0]["id"], "at": time.time() - 125} for _ in range(15)]
        self.path.write_text(json.dumps(state))
        output = self.run_cli().stdout
        self.assertNotIn("Last suggestion", output)
        self.assertEqual(len(self.state()["history"]), 16)

    def test_new_catalog_names_do_not_break_existing_personal_meals(self):
        self.run_cli()
        state = self.state()
        custom = eat.meal("custom-existing", "Scallion noodles", 8, True, True, "My own family recipe.")
        state["meals"] = [custom]
        self.path.write_text(json.dumps(state))
        listing = self.run_cli("list").stdout
        self.assertEqual(listing.count("Scallion noodles"), 1)
        loaded = eat.load_state(self.path)
        matching = [item for item in eat.menu(loaded) if item["name"] == custom["name"]]
        self.assertEqual(matching, [custom])

    def test_combined_filters_and_chaos_retain_constraints(self):
        catalog = {item["id"]: item for item in eat.MEALS}
        for _ in range(8):
            output = self.run_cli("--quick", "--cheap", "--vegetarian", "--chaos").stdout
            chosen = catalog[self.state()["history"][-1]["id"]]
            self.assertLessEqual(chosen["minutes"], 15)
            self.assertTrue(chosen["cheap"] and chosen["vegetarian"])
            self.assertTrue(any(joke in output for joke in eat.CHAOS))

    def test_recent_picks_and_reroll_commentary(self):
        outputs = [self.run_cli().stdout for _ in range(6)]
        history = self.state()["history"]
        self.assertEqual(len({item["id"] for item in history}), 6)
        self.assertIn("Third suggestion", outputs[2])
        self.assertIn("Five options", outputs[4])

    def test_custom_meal_persists_and_is_filterable(self):
        self.run_cli("add", "Mom's curry")
        self.run_cli("add", "Emergency beans", "--minutes", "10", "--cheap",
                     "--vegetarian", "--note", "Beans. Toast. Dinner.")
        self.assertIn("Mom's curry", self.run_cli("list").stdout)
        filtered = self.run_cli("list", "--quick", "--cheap", "--vegetarian").stdout
        self.assertIn("Emergency beans", filtered)
        self.assertNotIn("Mom's curry", filtered)
        self.assertEqual(len(self.state()["meals"]), 2)

    def test_duplicate_and_invalid_adds_do_not_change_data(self):
        self.run_cli("add", "Family curry")
        before = self.path.read_bytes()
        self.run_cli("add", " family CURRY ", status=1)
        self.run_cli("add", "Eggs on toast", status=1)
        self.run_cli("add", "Soup", "--minutes", "0", status=2)
        self.run_cli("add", "\033[31munsafe", status=1)
        self.assertEqual(self.path.read_bytes(), before)

    def test_preferences_are_applied(self):
        self.run_cli()
        state = self.state()
        state["preferences"] = {"vegetarian": True, "quick": True, "cheap": True}
        self.path.write_text(json.dumps(state))
        listing = self.run_cli("list").stdout
        self.assertIn("Eggs on toast", listing)
        self.assertNotIn("Tuna rice bowl", listing)
        self.assertNotIn("Red lentil soup", listing)
        self.assertNotIn("Hummus snack plate", listing)

    def test_invalid_state_is_preserved(self):
        incomplete_meal = dict(eat.MEALS[0], id="custom-incomplete", name="Incomplete meal")
        del incomplete_meal["minutes"]
        for value in ["not json", "[]", '{"version": 9000}',
                      '{"version":1,"preferences":{},"meals":[],"history":[{}]}',
                      json.dumps({"version": 1, "preferences": {}, "meals": [],
                                  "history": [{"id": "noodles", "at": 100, "thought": "yes"}]}),
                      json.dumps({"version": 1, "preferences": {},
                                  "meals": [incomplete_meal], "history": []})]:
            self.path.write_text(value)
            result = self.run_cli(status=1)
            self.assertIn("left untouched", result.stderr)
            self.assertEqual(self.path.read_text(), value)

    def test_unwritable_data_location_exits_cleanly(self):
        blocker = Path(self.tmp.name) / "a-file"
        blocker.write_text("keep me")
        self.env["EAT_HOME"] = str(blocker)
        result = self.run_cli(status=1)
        self.assertIn("eat:", result.stderr)
        self.assertEqual(blocker.read_text(), "keep me")

    def test_small_pool_rotates_and_sessions_expire(self):
        options = eat.MEALS[:2]
        history = [{"id": options[0]["id"], "at": 100},
                   {"id": options[1]["id"], "at": 101}]
        self.assertEqual(eat.pick(options, history), options[0])
        self.assertEqual(eat.pick(options[:1], history), options[0])
        self.assertEqual(eat.reroll_count(history, 500), 1)


if __name__ == "__main__":
    unittest.main()
