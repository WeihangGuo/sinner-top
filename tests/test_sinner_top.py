"""Regression checks for the sinner-top CLI and interactive view."""
import curses
import importlib.machinery
import importlib.util
import sys
import unittest
from dataclasses import replace
from datetime import datetime
from pathlib import Path
from unittest.mock import patch

sys.dont_write_bytecode = True
loader = importlib.machinery.SourceFileLoader("sinner_top", str(Path(__file__).resolve().parents[1] / "sinner-top"))
spec = importlib.util.spec_from_loader(loader.name, loader)
m = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = m
loader.exec_module(m)
NOW = datetime(2026, 9, 4, 12).timestamp()


def job(job_id="42_1", user="alice", gpu="h200", state="RUNNING", left="30:00", end="N/A", start="N/A", count=1):
    gres = f"gres/gpu:{gpu}:{count}" if gpu != "any" else f"gres/gpu:{count}"
    return m.Job(job_id, user, "training", "node1", gres, left, end, state, start)


def snapshot(jobs):
    inventory = {"h200": 8, "h100": 4, "24gb": 8, "47gb": 4, "a100": 2}
    return m.Snapshot(dict(inventory), dict(inventory), inventory, jobs, {})


class Screen:
    def __init__(self, height, width):
        self.height, self.width = height, width
        self.writes = []

    def getmaxyx(self):
        return self.height, self.width

    def erase(self):
        self.writes.clear()

    def refresh(self):
        pass

    def addstr(self, y, x, text, attr):
        assert 0 <= y < self.height
        assert 0 <= x < self.width
        assert x + m._display_width(text) <= self.width
        self.writes.append((y, x, text, attr))


class SinnerTopChecks(unittest.TestCase):
    def test_inventory_discovers_types_without_double_counting(self):
        text = (
            "NodeName=n1 State=MIXED CfgTRES=gres/gpu=6,gres/gpu:24gb=4,gres/gpu:47gb=2 "
            "AllocTRES=gres/gpu=3,gres/gpu:24gb=1,gres/gpu:47gb=2\n"
            "NodeName=n2 State=DRAIN CfgTRES=gres/gpu=8,gres/gpu:a100=8 AllocTRES=\n"
            "NodeName=n3 State=IDLE CfgTRES=gres/gpu=2 AllocTRES="
        )
        idle, active, total = m.parse_gpu_inventory(text)
        self.assertEqual(total, {"24gb": 4, "47gb": 2, "a100": 8, "any": 2})
        self.assertEqual(idle, {"24gb": 3, "47gb": 0, "a100": 0, "any": 2})
        self.assertEqual(active["a100"], 0)

    def test_array_allocations_keep_all_gpu_types(self):
        detail = (
            "JobId=99 ArrayJobId=42 ArrayTaskId=1\n"
            " Nodes=node1 GRES=gpu:47gb:0(IDX:),gpu:24gb:1(IDX:5),gpu:a100:2(IDX:0-1)"
        )
        allocations = m.parse_job_allocations(detail)
        self.assertEqual(m._gpu_usage(allocations["42_1"]), {"24gb": 1, "a100": 2})
        snap = replace(snapshot([job(gpu="any")]), allocations=allocations)
        self.assertEqual(m._group_jobs(snap, m.RUNNING_STATES, "24gb")[0][0], 1)
        self.assertFalse(m._group_jobs(snap, m.RUNNING_STATES, "any"))

    def test_pending_generic_and_multiple_type_requests(self):
        generic = m._fallback_allocations(job(gpu="any", state="PENDING"))
        self.assertEqual(m._gpu_usage(generic), {"any": 1})
        mixed = replace(job(), gres="gres/gpu:24gb:2,gres/gpu:47gb:1")
        self.assertEqual(m._gpu_usage(m._fallback_allocations(mixed)), {"24gb": 2, "47gb": 1})
        self.assertFalse(m._fallback_allocations(replace(job(), gres="N/A")))

    def test_collection_expands_array_subjobs(self):
        rows = "\n".join(f"42_{i}|alice|batch||gres/gpu:a100:2|1:00:00|N/A|PENDING|N/A" for i in (10, 2, 1))
        with patch.object(m, "_run", side_effect=[rows, "", ""]) as run:
            snap = m.collect_snapshot()
        self.assertIn("--array", run.call_args_list[0].args[0])
        self.assertTrue(any("%S" in arg for arg in run.call_args_list[0].args[0]))
        self.assertEqual(m._group_jobs(snap, m.QUEUED_STATES, "a100")[0][0], 6)
        lines, count = m._panel_lines(snap, m.QUEUED_STATES, "a100", 80, "alice", NOW)
        self.assertEqual(count, 3)
        text = "\n".join(line.text for line in lines)
        self.assertLess(text.index("42_1]"), text.index("42_2]"))
        self.assertLess(text.index("42_2]"), text.index("42_10]"))

    def test_finish_sorting_and_estimates(self):
        early = job("1", left="1:00:00", state="PENDING", start="2026-09-04T13:00:00", end="2026-09-04T14:00:00")
        late = job("2", left="10:00", state="PENDING", start="2026-09-04T16:00:00", end="2026-09-04T16:10:00", count=8)
        unknown = job("3", state="PENDING")
        ordered = sorted([unknown, late, early], key=lambda j: m._finish_key(j, NOW))
        self.assertEqual([j.job_id for j in ordered], ["1", "2", "3"])
        self.assertEqual(m._start_label(early.start, NOW), "start in ~1h 00m")
        self.assertEqual(m._start_label("N/A", NOW), "start unknown")
        self.assertEqual(m._start_label("2026-09-04T11:00:00", NOW), "start overdue")
        self.assertLess(m._finish_key(job(left="10:00"), NOW), m._finish_key(job(left="4:00:00", count=8), NOW))

    def test_filtering_highlighting_and_all_rows_are_scrollable(self):
        jobs = [job(str(i), "alice", "24gb") for i in range(12)]
        jobs += [job("30", "bob", "24gb"), job("31", "alice", "h200")]
        lines, count = m._panel_lines(snapshot(jobs), m.RUNNING_STATES, "24gb", 40, "alice", NOW)
        self.assertEqual(count, 13)
        text = "\n".join(line.text for line in lines)
        self.assertIn("alice (you)", text)
        self.assertIn("[11]", text)
        self.assertNotIn("[31]", text)
        self.assertTrue(all(line.own for line in lines if "[" in line.text and "[30]" not in line.text))
        self.assertTrue(all(not line.own for line in lines if "[30]" in line.text))
        self.assertTrue(all(m._display_width(line.text) <= 40 for line in lines))

    def test_navigation_independent_offsets_and_boundaries(self):
        state = m.ViewState()
        counts = [100, 200]
        for _ in range(3):
            m._handle_key(state, ord("j"), 10, counts)
        m._handle_key(state, curses.KEY_RIGHT, 10, counts)
        m._handle_key(state, curses.KEY_NPAGE, 10, counts)
        self.assertEqual([state.offset(0), state.offset(1)], [3, 10])
        m._handle_key(state, ord("k"), 10, counts)
        self.assertEqual(state.offset(1), 9)
        m._handle_key(state, curses.KEY_END, 10, counts)
        self.assertEqual(state.offset(1), 190)
        m._handle_key(state, ord("j"), 10, counts)
        self.assertEqual(state.offset(1), 190)
        m._handle_key(state, curses.KEY_HOME, 10, counts)
        m._handle_key(state, curses.KEY_UP, 10, counts)
        self.assertEqual(state.offset(1), 0)
        m._handle_key(state, ord("h"), 10, counts)
        self.assertEqual(state.pane, 0)
        self.assertEqual(state.offset(0), 3)

    def test_all_gpu_types_are_reachable_and_positions_preserved(self):
        state = m.ViewState(gpu_types=["h200", "h100", "24gb", "47gb", "any"])
        state.offsets["h200", 0] = 4
        visited = []
        for _ in state.gpu_types:
            visited.append(state.gpu_type)
            m._handle_key(state, ord("g"), 10, [100, 100])
        self.assertEqual(visited, state.gpu_types)
        self.assertEqual(state.offset(0), 4)
        m._handle_key(state, ord("["), 10, [100, 100])
        self.assertEqual(state.gpu_type, "any")
        m._handle_key(state, ord("3"), 10, [100, 100])
        self.assertEqual(state.gpu_type, "24gb")
        state.clamp([0, 0], 10)
        self.assertEqual(state.offset(0), 0)

    def test_screen_fits_and_highlights_without_colors(self):
        state = m.ViewState(gpu_types=["h200", "h100", "24gb", "47gb", "any"])
        panels = [([m.PanelLine("alice (you)", own=True, heading=True), m.PanelLine("own job", own=True)], 1), ([m.PanelLine("No pending jobs")], 0)]
        for width, height in ((120, 30), (80, 24), (40, 12), (30, 8), (20, 5)):
            screen = Screen(height, width)
            m._draw_screen(screen, state, panels, snapshot([]), "alice", 5, NOW, "", False, curses.A_BOLD, curses.A_REVERSE)
            if width >= 30:
                own_rows = [record for record in screen.writes if "alice (you)" in record[2]]
                self.assertTrue(own_rows)
                self.assertTrue(own_rows[0][3] & curses.A_REVERSE)
                self.assertTrue(any(y == height - 1 and "[/]/g:GPU" in text for y, x, text, attr in screen.writes))

    def test_loader_failure_is_reported_and_can_retry(self):
        loader = m.SnapshotLoader()
        with patch.object(m, "collect_snapshot", side_effect=m.SlurmCommandError("offline")):
            loader.request()
            result = loader.results.get(timeout=2)
        self.assertEqual(result, (None, "offline"))
        loader.results.put(result)
        self.assertEqual(loader.poll(), result)
        self.assertFalse(loader.running)
        with patch.object(m, "collect_snapshot", return_value=snapshot([])):
            loader.request()
            result = loader.results.get(timeout=2)
        self.assertIsNotNone(result[0])

    def test_cli_defaults_and_printable_any_gpu_filter(self):
        args = m.build_parser().parse_args([])
        self.assertEqual(args.gpu, "h200")
        self.assertIsNone(args.max_jobs)
        self.assertEqual(m.build_parser().parse_args(["--gpu", "A100"]).gpu, "a100")
        out = m.render(snapshot([job(gpu="a100")]), gpu_type="a100", width=120, current_user="alice", now=NOW)
        self.assertIn("A100", out)
        self.assertNotIn("H200", out)
        self.assertIn("(you)", out)


if __name__ == "__main__":
    unittest.main(verbosity=2)
