"""Regression checks for the sinner-top CLI and interactive view."""
import curses
import importlib.machinery
import importlib.util
import sys
import tempfile
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


def job(job_id="42_1", user="alice", gpu="h200", state="RUNNING", left="30:00", end="N/A", start="N/A", count=1, account="unknown"):
    gres = f"gres/gpu:{gpu}:{count}" if gpu != "any" else f"gres/gpu:{count}"
    return m.Job(job_id, user, "training", "node1", gres, left, end, state, start, account)


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

    def test_remaining_time_colors_and_live_thresholds(self):
        for seconds, color in ((0, "32"), (3600, "32"), (3601, "33"), (21600, "33"), (21601, "31"), (float("inf"), "2")):
            self.assertEqual(m._duration_color(seconds), color)
        self.assertEqual(m._remaining_color("30:00"), "32")
        self.assertEqual(m._remaining_color("12:00:00"), "31")
        snap = snapshot([job(left="12:00:00", end="2026-09-04T13:00:01")])
        for now, color in ((NOW, "33"), (NOW + 1, "32")):
            lines, _ = m._panel_lines(snap, m.RUNNING_STATES, "h200", 40, "alice", now)
            times = [line for line in lines if line.remaining_seconds is not None]
            self.assertEqual(len(times), 1)
            self.assertEqual(m._duration_color(times[0].remaining_seconds), color)
        lines, _ = m._panel_lines(snapshot([job(left="UNLIMITED")]), m.RUNNING_STATES, "h200", 40, "alice", NOW)
        time_line = next(line for line in lines if line.remaining_seconds is not None)
        self.assertIn("unknown", time_line.text)
        self.assertEqual(m._duration_color(time_line.remaining_seconds), "2")
        pending, _ = m._panel_lines(snapshot([job(state="PENDING")]), m.QUEUED_STATES, "h200", 40, "alice", NOW)
        self.assertTrue(all(line.remaining_seconds is None for line in pending))

    def test_time_colors_preserve_own_highlight_and_wrapping(self):
        attrs = {"32": 301, "33": 302, "31": 303, "2": 304}
        snap = snapshot([job(left="30:00"), job("42_2", left="3:00:00"), job("42_3", left="12:00:00")])
        for width in (40, 80, 120):
            lines, count = m._panel_lines(snap, m.RUNNING_STATES, "h200", (width - 1) // 2, "alice", NOW)
            screen = Screen(60, width)
            panels = [(lines, count), ([m.PanelLine("No pending jobs")], 0)]
            m._draw_screen(screen, m.ViewState(), panels, snap, "alice", 5, NOW, "", False, curses.A_BOLD, curses.A_REVERSE, attrs)
            overlays = [record for record in screen.writes if record[3] in attrs.values()]
            self.assertEqual({record[3] for record in overlays}, {301, 302, 303})
            for y, x, text, attr in overlays:
                base = next(record for record in screen.writes if record[0] == y and record[1] == 0)
                self.assertTrue(base[3] & curses.A_REVERSE)
                self.assertGreater(x, 0)
            m._draw_screen(screen, m.ViewState(), panels, snap, "alice", 5, NOW, "", False, curses.A_BOLD, curses.A_REVERSE)
            self.assertFalse(any(record[3] in attrs.values() for record in screen.writes))

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
        for key in (ord("j"), curses.KEY_DOWN, ord("j")):
            m._handle_key(state, key, 10, counts)
        m._handle_key(state, curses.KEY_RIGHT, 10, counts)
        m._handle_key(state, curses.KEY_NPAGE, 10, counts)
        self.assertEqual([state.offset(0), state.offset(1)], [15, 10])
        m._handle_key(state, ord("k"), 10, counts)
        self.assertEqual(state.offset(1), 5)
        m._handle_key(state, curses.KEY_END, 10, counts)
        self.assertEqual(state.offset(1), 190)
        m._handle_key(state, ord("j"), 10, counts)
        self.assertEqual(state.offset(1), 190)
        m._handle_key(state, curses.KEY_HOME, 10, counts)
        m._handle_key(state, curses.KEY_UP, 10, counts)
        self.assertEqual(state.offset(1), 0)
        m._handle_key(state, ord("h"), 10, counts)
        self.assertEqual(state.pane, 0)
        self.assertEqual(state.offset(0), 15)

    def test_all_gpu_types_are_reachable_and_positions_preserved(self):
        state = m.ViewState(gpu_types=["h200", "h100", "24gb", "47gb", "any"])
        state.offsets["h200", 0] = 4
        visited = []
        for _ in range(len(state.gpu_types) + 3):
            visited.append(state.view if state.single_panel else state.gpu_type)
            m._handle_key(state, ord("g"), 10, [100, 100])
        self.assertEqual(visited, state.gpu_types + ["nodes", "live", "history"])
        self.assertEqual(state.offset(0), 4)
        m._handle_key(state, ord("["), 10, [100, 100])
        self.assertEqual(state.view, "history")
        m._handle_key(state, ord("["), 10, [100, 100])
        self.assertEqual(state.view, "live")
        m._handle_key(state, ord("["), 10, [100, 100])
        self.assertEqual(state.view, "nodes")
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
                self.assertTrue(any(y == height - 1 and "g:view" in text for y, x, text, attr in screen.writes))

    def test_account_field_parsing_and_collection(self):
        legacy = "1|alice|train|node1|gres/gpu:h200:1|30:00|N/A|RUNNING"
        self.assertEqual(m.parse_squeue(legacy)[0].account, "unknown")
        self.assertEqual(m.parse_squeue(legacy + "|N/A")[0].account, "unknown")
        self.assertEqual(m.parse_squeue(legacy + "|N/A|lab-a")[0].account, "lab-a")
        with patch.object(m, "_run", side_effect=[legacy + "|N/A|lab-a", "", ""]) as run:
            snap = m.collect_snapshot()
        self.assertTrue(any("%a" in part for part in run.call_args_list[0].args[0]))
        self.assertEqual(snap.jobs[0].account, "lab-a")

    def test_node_inventory_preserves_free_and_unavailable_capacity(self):
        text = (
            "NodeName=n1 State=MIXED CfgTRES=gres/gpu=8,gres/gpu:h200=8 AllocTRES=gres/gpu=3\n"
            "NodeName=n2 State=MIXED+DRAIN CfgTRES=gres/gpu=8,gres/gpu:h200=8 AllocTRES=gres/gpu=2,gres/gpu:h200=2\n"
            "NodeName=n3 State=IDLE CfgTRES=gres/gpu=4,gres/gpu:h100=4 AllocTRES=\n"
        )
        with patch.object(m, "_run", side_effect=["", text, ""]):
            snap = m.collect_snapshot()
        self.assertEqual(snap.idle["h200"], 5)
        self.assertEqual(snap.total["h200"], 16)
        self.assertEqual((snap.nodes[1].free("h200"), snap.nodes[1].idle("h200")), (6, 0))
        lines = m._node_lines(snap, 80, "alice", NOW)
        report = "\n".join(line.text for line in lines)
        cards = dict(m._node_cards(snap, [28] * 4, "alice", NOW))
        self.assertIn("free 5/8  used 3", cards["n1"][0].text)
        self.assertIn("free 6/8  used 2", cards["n2"][0].text)
        self.assertIn("UNAVAILABLE", report)
        self.assertIn("3 used: user unknown", "\n".join(line.text for line in cards["n1"]))
        self.assertNotIn("n3", report)

    def test_node_jobs_arrays_multi_host_and_local_gpu_counts(self):
        self.assertEqual(m.expand_nodelist("n[01-02,04],n06"), ["n01", "n02", "n04", "n06"])
        self.assertEqual(m.expand_nodelist("rack[1-2]n[1-2],n9"), ["rack1n1", "rack1n2", "rack2n1", "rack2n2", "n9"])
        details = (
            "JobId=99 ArrayJobId=42 ArrayTaskId=1\n Nodes=n[01-02],n04 GRES=gpu:h200:2(IDX:0-1)\n"
            "JobId=100 ArrayJobId=42 ArrayTaskId=2\n Nodes=n01 GRES=gpu:1(IDX:2)\n"
        )
        jobs = [job("42_1", left="12:00:00"), job("42_2", user="bob", left="30:00"), job("43", state="PENDING")]
        nodes = [m.NodeInventory(name, "MIXED", {"h200": 8}, {"h200": 3 if name == "n01" else 2}) for name in ("n01", "n02", "n04")]
        snap = replace(snapshot(jobs), nodes=nodes, allocations=m.parse_job_allocations(details))
        lines = m._node_lines(snap, 120, "alice", NOW)
        report = "\n".join(line.text for line in lines)
        self.assertEqual(report.count("alice"), 3)
        self.assertEqual(report.count("bob"), 1)
        self.assertNotIn("training", report)
        self.assertNotIn("42_1", report)
        self.assertNotIn("42_2", report)
        self.assertNotIn("unavailable", report)
        # Free capacity determines node ordering; jobs finish soonest first within a node.
        self.assertLess(report.index("n02"), report.index("n01"))
        cards = dict(m._node_cards(snap, [28] * 4, "alice", NOW))
        final_node = "\n".join(line.text for line in cards["n01"])
        self.assertLess(final_node.index("bob"), final_node.index("alice"))
        self.assertIn("0-1 alice", final_node)
        cells = [cell for line in lines for _, _, cell in line.cells]
        self.assertTrue(all(line.own for line in cells if "alice" in line.text))
        self.assertFalse(any(line.own for line in cells if "bob" in line.text))

    def test_node_screen_countdowns_resize_and_unavailable_details(self):
        nodes = [m.NodeInventory("node1", "MIXED", {"h200": 8}, {"h200": 3})]
        jobs = [job(end="2026-09-04T13:00:01"), job("43", left="UNLIMITED"), job("44", state="COMPLETING")]
        allocations = {row.job_id: [m.Allocation("node1", "h200", 1, str(index))] for index, row in enumerate(jobs)}
        snap = replace(snapshot(jobs), nodes=nodes, allocations=allocations)
        attrs = {"32": 301, "33": 302, "31": 303, "2": 304}
        for width, height in ((120, 30), (80, 24), (40, 12), (30, 8)):
            lines = m._node_lines(snap, width, "alice", NOW)
            self.assertTrue(all(m._display_width(line.text) <= width for line in lines))
            screen = Screen(height, width)
            state = m.ViewState(view="nodes", gpu_type="h100")
            m._draw_screen(screen, state, [(lines, 0)], snap, "alice", 5, NOW, "", False,
                           curses.A_BOLD, curses.A_REVERSE, attrs)
            self.assertTrue(any("H200 NODES" in text for y, x, text, attr in screen.writes))
            self.assertFalse(any(text == "│" for y, x, text, attr in screen.writes))
            for y, x, text, attr in screen.writes:
                if attr in attrs.values():
                    self.assertNotIn("alice", text)
                    self.assertNotIn("GPU", text)
        for now, color in ((NOW, "33"), (NOW + 1, "32")):
            lines = m._node_lines(snap, 120, "alice", now)
            first = next(cell for line in lines for _, _, cell in line.cells if cell.text.startswith("0 alice"))
            self.assertEqual(m._duration_color(first.remaining_seconds), color)
        self.assertIn("releasing", "\n".join(line.text for line in lines))
        self.assertIn("No H200 nodes", m._node_lines(snapshot([]), 80, "alice", NOW)[0].text)

    def test_node_grid_four_columns_incomplete_row_and_cell_colors(self):
        nodes = [m.NodeInventory(f"node{i}", "MIXED", {"h200": 8}, {"h200": 2}) for i in range(9)]
        jobs = [job(str(i), user="alice" if i % 2 else "bob", left="00:30:00" if i % 2 else "12:00:00") for i in range(18)]
        allocations = {row.job_id: [m.Allocation(f"node{i // 2}", "h200", 1, str(i % 2))] for i, row in enumerate(jobs)}
        snap = replace(snapshot(jobs), nodes=nodes, allocations=allocations)
        attrs = {"32": 301, "33": 302, "31": 303, "2": 304}
        for width in (30, 40, 80, 81, 120, 160):
            lines = m._node_lines(snap, width, "alice", NOW)
            self.assertEqual([line.text.count("┌") for line in lines if "┌" in line.text], [4, 4, 1])
            self.assertTrue(all(m._display_width(line.text) <= width for line in lines))
            screen = Screen(len(lines) + 6, width)
            m._draw_screen(screen, m.ViewState(view="nodes"), [(lines, 0)], snap, "alice", 5, NOW, "", False,
                           curses.A_BOLD, curses.A_REVERSE, attrs)
            colors = [text.strip() for y, x, text, attr in screen.writes if attr in attrs.values()]
            self.assertGreaterEqual(len(colors), 18)  # narrow cells wrap long times
            if width >= 80:
                self.assertEqual(len(colors), 18)
                self.assertEqual(colors.count("30m"), 9)
                self.assertEqual(colors.count("12h00m"), 9)
                own = [text for y, x, text, attr in screen.writes if "alice" in text and attr & curses.A_REVERSE]
                self.assertEqual(len(own), 9)

    def test_node_navigation_preserves_job_and_node_positions(self):
        state = m.ViewState(gpu_type="h100", pane=1)
        state.offsets["h100", 1] = 15
        m._handle_key(state, ord("n"), 10, [100, 100])
        self.assertEqual(state.view, "nodes")
        self.assertEqual(state.focused_pane, 0)
        m._handle_key(state, curses.KEY_DOWN, 10, [40])
        self.assertEqual(state.offset(0), 5)
        m._handle_key(state, ord("n"), 10, [40])
        self.assertEqual((state.view, state.gpu_type, state.pane, state.offset(1)), ("jobs", "h100", 1, 15))
        m._handle_key(state, ord("n"), 10, [100, 100])
        self.assertEqual(state.offset(0), 5)
        m._handle_key(state, ord("j"), 10, [40])
        self.assertEqual(state.offset(0), 10)
        m._handle_key(state, ord("h"), 10, [40])
        self.assertEqual((state.view, state.pane), ("jobs", 0))

    def test_account_totals_split_users_and_ignore_pending(self):
        jobs = [
            job("10_1", "alice", count=2, account="alpha"),
            job("10_2", "alice", count=3, account="alpha"),
            job("11", "bob", gpu="h100", count=4, account="alpha"),
            job("12", "alice", gpu="47gb", count=8, account="beta"),
            job("13", "carol", count=6, account="gamma", state="COMPLETING"),
            job("14", "alice", count=100, account="beta", state="PENDING"),
            replace(job("15", "alice", account="cpu-only"), gres="N/A"),
        ]
        ranks = m._account_rankings(snapshot(jobs))
        self.assertEqual([row.account for row in ranks], ["alpha", "beta", "gamma"])
        self.assertEqual(ranks[0].usage, {"h200": 5, "h100": 4})
        self.assertEqual(ranks[0].users["alice"], {"h200": 5})
        self.assertEqual(ranks[1].users["alice"], {"47gb": 8})
        self.assertEqual(sum(sum(row.usage.values()) for row in ranks), 23)

    def test_ranking_medals_highlighting_and_terminal_width(self):
        jobs = [
            job("1", "bob", count=4, account="alpha"),
            job("2", "alice", count=3, account="alpha"),
            job("3", "carol", count=2, account="alpha"),
            job("4", "dave", count=1, account="alpha"),
            job("5", "erin", count=8, account="beta"),
            job("6", "frank", count=6, account="gamma"),
            job("7", "grace", count=1, account="delta"),
        ]
        snap = snapshot(jobs)
        lines = m._ranking_lines(snap, 120, "alice")
        headings = [line for line in lines if line.heading]
        self.assertEqual([line.text.split()[0] for line in headings], ["🥇", "🥈", "🥉", "4."])
        self.assertTrue(headings[0].own)
        self.assertTrue(any("🥈 alice (you)" in line.text and line.own for line in lines))
        self.assertTrue(any("🥇 bob" in line.text and not line.own for line in lines))
        self.assertTrue(any("🥉 carol" in line.text for line in lines))
        self.assertTrue(any("4. dave" in line.text for line in lines))
        history = m.HistorySnapshot(m._account_rankings(snap), NOW, "2025-08-04T21:40:00")
        for width, height in ((120, 36), (80, 24), (40, 12), (30, 8)):
            for view in ("live", "history"):
                lines = m._ranking_lines(snap, width, "alice") if view == "live" else m._history_lines(history, width, "alice")
                self.assertTrue(all(m._display_width(line.text) <= width for line in lines))
                screen = Screen(height, width)
                state = m.ViewState(view=view, animation_elapsed=3)
                m._draw_screen(screen, state, [(lines, 0)], snap, "alice", 5, NOW, "", False,
                               curses.A_BOLD, curses.A_REVERSE, history=history)
                self.assertFalse(any(text == "│" for y, x, text, attr in screen.writes))
                self.assertTrue(any(y == height - 1 and "0:LIVE" in text and "t:TOTAL" in text for y, x, text, attr in screen.writes))
                if view == "live":
                    self.assertFalse(any("OVERLORD" in text or "POWERING UP" in text for y, x, text, attr in screen.writes))

    def test_ranking_navigation_keeps_separate_scroll_positions(self):
        state = m.ViewState(pane=1)
        state.offsets["h200", 1] = 15
        m._handle_key(state, ord("0"), 10, [100, 100])
        self.assertEqual(state.view, "live")
        m._handle_key(state, curses.KEY_DOWN, 10, [40])
        self.assertEqual(state.offset(0), 5)
        m._handle_key(state, ord("l"), 10, [40])
        self.assertEqual((state.view, state.history_page), ("history", "podium"))
        m._handle_key(state, ord("j"), 10, [40])
        self.assertEqual(state.history_page, "rest")
        self.assertEqual(state.offset(0), 0)
        m._handle_key(state, ord("j"), 10, [40])
        self.assertEqual(state.offset(0), 5)
        m._handle_key(state, ord("h"), 10, [40])
        self.assertEqual(state.view, "live")
        self.assertEqual(state.offset(0), 5)
        m._handle_key(state, ord("0"), 10, [40])
        self.assertEqual(state.view, "jobs")
        self.assertEqual(state.focused_pane, 1)
        self.assertEqual(state.offset(1), 15)
        m._handle_key(state, ord("t"), 10, [40])
        self.assertEqual(state.history_page, "podium")
        m._handle_key(state, 10, 10, [40])
        self.assertEqual(state.history_page, "all")
        m._handle_key(state, ord("k"), 10, [40])
        self.assertEqual(state.history_page, "podium")
        m._handle_key(state, ord("1"), 10, [40])
        self.assertEqual(state.view, "jobs")
        self.assertEqual(state.gpu_type, "h100")

    def test_history_counts_gpu_seconds_arrays_and_distinct_allocations(self):
        rows = [
            "42_1|alpha|alice|3600|gres/gpu=4,gres/gpu:h200=2,gres/gpu:h100=1|2025-08-04T12:00:00",
            "42_1.batch|alpha|alice|3600|gres/gpu=4|2025-08-04T12:00:00",
            "42_1.0|alpha|alice|3600|gres/gpu=4|2025-08-04T12:00:00",
            "42_2|alpha|alice|1800|gres/gpu=2,gres/gpu:h200=2|2025-08-05T12:00:00",
            "43|beta|alice|7200|gres/gpu=2|2025-08-06T12:00:00",
            # An older allocation with a reused ID must also count.
            "43|beta|bob|3600|gres/gpu=1|2025-08-01T12:00:00",
            "44|pending|dave|0||Unknown",
            "45|cpu|bob|999999|cpu=100|2024-01-01T12:00:00",
            "46|zero|bob|0|gres/gpu=8|2025-01-01T12:00:00",
        ]
        history = m.parse_sacct_history(iter(rows), NOW)
        self.assertEqual([row.account for row in history.accounts], ["alpha", "beta"])
        self.assertEqual(history.accounts[0].usage, {"h200": 10800, "h100": 3600, "any": 3600})
        self.assertEqual(history.accounts[1].users, {"alice": {"any": 14400}, "bob": {"any": 3600}})
        self.assertEqual(history.earliest, "2025-08-01T12:00:00")
        self.assertEqual(history.updated, NOW)
        lines = m._history_lines(history, 80, "alice")
        self.assertTrue(any("5.0 GPU-h" in line.text and line.heading for line in lines))
        self.assertTrue(any("Retained records since 2025-08-01" in line.text for line in lines))
        self.assertTrue(any("alice (you)" in line.text and line.own for line in lines))

    def test_history_empty_missing_and_invalid_data(self):
        empty = m.parse_sacct_history([], NOW)
        self.assertEqual(empty.accounts, [])
        self.assertIsNone(empty.earliest)
        self.assertTrue(any("No GPU usage" in line.text for line in m._history_lines(empty, 80, "alice")))
        with self.assertRaises(ValueError):
            m.parse_sacct_history(["unexpected|format"], NOW)
        with self.assertRaises(ValueError):
            m.parse_sacct_history(["1|lab|alice|-1|gres/gpu=1|Unknown"], NOW)
        history = m.parse_sacct_history(["1|N/A||30|gres/gpu=1|Unknown"], NOW)
        self.assertEqual(history.accounts[0].account, "unknown")
        self.assertEqual(history.accounts[0].users, {"unknown": {"any": 30}})
        lines = m._history_lines(history, 80, "alice", error="offline")
        self.assertTrue(any("last successful" in line.text for line in lines))
        self.assertTrue(any("History unavailable: offline" in line.text for line in lines))
        self.assertTrue(any(line.heading for line in lines))

    def test_history_cache_roundtrip_permissions_and_corruption(self):
        history = m.parse_sacct_history(["1|lab|alice|3600|gres/gpu=2|2025-01-01T00:00:00"], NOW)
        with tempfile.TemporaryDirectory() as directory, patch.object(m, "_history_cache_path", return_value=Path(directory) / "history.json"):
            self.assertIsNone(m._read_history_cache())
            m._save_history_cache(history)
            self.assertEqual(m._read_history_cache(), history)
            path = m._history_cache_path()
            self.assertEqual(path.stat().st_mode & 0o777, 0o600)
            for text in ('{"version":1}', 'invalid', '{"version":1,"updated":1,"earliest":null,"accounts":{"a":{"u":{"h200":-1}}}}'):
                path.write_text(text)
                self.assertIsNone(m._read_history_cache())

    def test_history_collection_uses_all_retained_allocations_and_background_loader(self):
        def report(command, **kwargs):
            self.assertIn("--starttime=1970-01-01", command)
            self.assertTrue(all(option in command for option in ("--local", "--allusers", "--allocations", "--array", "--duplicates")))
            self.assertEqual(kwargs["timeout"], 120)
            kwargs["stdout"].write("1|lab|alice|1800|gres/gpu=4|2025-01-01T00:00:00\n")
        history_loader = m.SnapshotLoader(m.collect_history)
        with patch.object(m.subprocess, "run", side_effect=report), patch.object(m, "_save_history_cache") as save:
            history_loader.request()
            history, error = history_loader.results.get(timeout=2)
        self.assertEqual(error, "")
        self.assertEqual(history.accounts[0].usage, {"any": 7200})
        save.assert_called_once_with(history)

    def test_history_failure_leaves_cache_untouched(self):
        for error in (FileNotFoundError(), m.subprocess.TimeoutExpired("sacct", 120), m.subprocess.CalledProcessError(1, "sacct", stderr="denied")):
            with patch.object(m.subprocess, "run", side_effect=error), patch.object(m, "_save_history_cache") as save:
                with self.assertRaises(m.SlurmCommandError):
                    m.collect_history()
                save.assert_not_called()

    def test_podium_layout_details_and_animation_frames(self):
        accounts = [m.AccountUsage(f"lab{rank}", {"h200": 1000000, "h100": 7200},
                                  {f"u{i}": {"h200": 3600 * (10 - i)} for i in range(6)}) for rank in range(3)]
        for width, height in ((120, 36), (120, 30), (80, 24), (40, 12), (30, 8)):
            layout = m._hero_layout(width, height)
            self.assertEqual(layout[0][2], (width - 1) // 2)
            self.assertEqual(layout[0][3], layout[1][3] + layout[2][3])
            self.assertEqual(layout[2][1], layout[1][1] + layout[1][3])
            for rank, (x, y, w, h) in enumerate(layout):
                frames = [m._hero_card(accounts[rank], rank, w, h, t, "u1") for t in (0, .35, .75, 1.2, 2.5, 3.1)]
                self.assertEqual(len({len(lines) for lines in frames}), 1)
                for lines in frames:
                    self.assertLessEqual(len(lines), h)
                    self.assertTrue(all(m._display_width(line.text) <= w for line in lines))
                if h >= 8:
                    self.assertNotEqual(frames[0], frames[-1])
                    self.assertNotEqual(frames[-2], frames[-1])
                if width >= 80 and height >= 24:
                    text = "\n".join(line.text for line in frames[-1])
                    for user in accounts[rank].users:
                        self.assertIn(user, text)
                    self.assertTrue(any("u1" in line.text and line.own for line in frames[-1]))
                    self.assertRegex(text, r"H200[:~]")

    def test_entrance_replays_on_view_and_podium_returns_only(self):
        state = m.ViewState()
        m._handle_key(state, ord("t"), 20, [100, 100])
        state.animate(10, False)
        self.assertIsNone(state.animation_tick)
        state.animate(20, True)
        self.assertEqual(state.animation_elapsed, 0)
        state.animate(23, True)
        self.assertEqual(state.animation_elapsed, 3)
        state.select_view("history")
        state.animate(24, True)
        self.assertEqual(state.animation_elapsed, 4)
        m._handle_key(state, ord("e"), 20, [100])
        state.animate(30, True)
        self.assertEqual(state.animation_elapsed, 4)
        m._handle_key(state, ord("e"), 20, [100])
        state.animate(31, True)
        self.assertEqual(state.animation_elapsed, 5)
        m._handle_key(state, ord("j"), 20, [100])
        state.animate(40, True)
        self.assertEqual(state.animation_elapsed, 5)
        m._handle_key(state, ord("b"), 20, [100])
        self.assertEqual(state.animation_elapsed, 0)
        self.assertIsNone(state.animation_tick)
        state.animate(45, True)
        m._handle_key(state, ord("h"), 20, [100])
        m._handle_key(state, curses.KEY_RIGHT, 20, [100])
        self.assertEqual((state.view, state.history_page, state.animation_elapsed), ("history", "podium", 0))

    def test_history_next_page_starts_at_four_and_full_details_keep_every_user(self):
        accounts = [m.AccountUsage(f"lab{i}", {"h200": 10000-i}, {f"member{i}": {"h200": 10000-i}}) for i in range(7)]
        history = m.HistorySnapshot(accounts, NOW, "2025-08-01T00:00:00")
        rest = m._history_lines(history, 80, "member4", start_rank=3)
        headings = [line.text for line in rest if line.heading]
        self.assertTrue(headings[0].startswith("4. lab3"))
        self.assertNotIn("lab0", "\n".join(line.text for line in rest))
        full = "\n".join(line.text for line in m._history_lines(history, 80, "member0"))
        for i in range(7):
            self.assertIn(f"member{i}", full)
        empty_tail = m._history_lines(m.HistorySnapshot(accounts[:2], NOW, None), 80, "u", start_rank=3)
        self.assertTrue(any("No accounts below" in line.text for line in empty_tail))

    def test_live_page_never_draws_ascii_heroes_or_plays_animations(self):
        snap = snapshot([job(account="lab")])
        state = m.ViewState(view="live")
        lines = m._ranking_lines(snap, 120, "alice")
        history = m.HistorySnapshot(m._account_rankings(snap), NOW, None)
        with patch.object(m, "_draw_heroes") as draw:
            m._draw_screen(Screen(36, 120), state, [(lines, 0)], snap, "alice", 5, NOW, "", False,
                           curses.A_BOLD, curses.A_REVERSE, history=history)
            draw.assert_not_called()
        state.animate(10, True)
        self.assertIsNone(state.animation_tick)
        m._handle_key(state, ord("e"), 20, [100])
        m._handle_key(state, ord("m"), 20, [100])
        self.assertTrue(state.effects)
        self.assertTrue(state.memes)
        self.assertFalse(any("<<" in line.text or "OVERLORD" in line.text for line in lines))

    def test_empty_rankings_unknown_accounts_and_ties(self):
        self.assertIn("No running GPU allocations", m._ranking_lines(snapshot([]), 80, "alice")[0].text)
        jobs = [job("1", account="zeta"), job("2", account="alpha"), job("3", account="N/A")]
        self.assertEqual([row.account for row in m._account_rankings(snapshot(jobs))], ["alpha", "unknown", "zeta"])

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
