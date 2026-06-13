"""Smoke tests for SOC2BOX. Standard library only, no network, no temp services."""
import os
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from soc2box import (  # noqa: E402
    TOOL_NAME, TOOL_VERSION, new_program, add_evidence, control_status,
    program_readiness, gap_list, save_program, load_program,
)
from soc2box.core import (  # noqa: E402
    STATUS_SATISFIED, STATUS_STALE, STATUS_MISSING, STATUS_NA,
)
from soc2box.cli import main  # noqa: E402

NOW = datetime(2026, 6, 8, 12, 0, 0, tzinfo=timezone.utc)


def _iso(days_ago):
    return (NOW - timedelta(days=days_ago)).isoformat()


class TestMeta(unittest.TestCase):
    def test_version(self):
        self.assertEqual(TOOL_NAME, "soc2box")
        self.assertRegex(TOOL_VERSION, r"^\d+\.\d+\.\d+$")


class TestEngine(unittest.TestCase):
    def test_default_program_seeded(self):
        p = new_program(company="X")
        self.assertEqual(p.company, "X")
        self.assertTrue(len(p.controls) >= 10)
        self.assertIsNotNone(p.get("cc6.1"))  # case-insensitive lookup

    def test_status_transitions(self):
        p = new_program()
        # missing by default
        c = p.get("CC6.1")
        self.assertEqual(control_status(c, NOW)["status"], STATUS_MISSING)
        # fresh -> satisfied
        add_evidence(p, "CC6.1", "okta://mfa", collected_at=_iso(5))
        self.assertEqual(control_status(c, NOW)["status"], STATUS_SATISFIED)
        # aged past 90d cadence -> stale
        add_evidence(p, "CC6.1", "old", collected_at=_iso(200))
        # latest is still the 5d-old one -> still satisfied
        self.assertEqual(control_status(c, NOW)["status"], STATUS_SATISFIED)
        # a control whose only evidence is old
        add_evidence(p, "CC4.1", "scan", collected_at=_iso(45))  # 30d cadence
        self.assertEqual(control_status(p.get("CC4.1"), NOW)["status"], STATUS_STALE)

    def test_not_applicable(self):
        p = new_program()
        c = p.get("A1.2")
        c.applicable = False
        self.assertEqual(control_status(c, NOW)["status"], STATUS_NA)

    def test_add_unknown_control_raises(self):
        p = new_program()
        with self.assertRaises(KeyError):
            add_evidence(p, "ZZ9.9", "x")

    def test_bad_timestamp_raises(self):
        p = new_program()
        with self.assertRaises(ValueError):
            add_evidence(p, "CC6.1", "x", collected_at="not-a-date")

    def test_readiness_and_gaps(self):
        p = new_program()
        add_evidence(p, "CC6.1", "a", collected_at=_iso(1))
        add_evidence(p, "CC8.1", "b", collected_at=_iso(1))
        rep = program_readiness(p, NOW)
        self.assertEqual(rep["counts"][STATUS_SATISFIED], 2)
        self.assertGreater(rep["counts"][STATUS_MISSING], 0)
        self.assertFalse(rep["audit_ready"])
        self.assertTrue(0 < rep["readiness_pct"] < 100)
        gaps = gap_list(p, NOW)
        # missing controls sort before stale; all gap entries are missing here
        self.assertTrue(all(g["status"] in (STATUS_MISSING, STATUS_STALE) for g in gaps))
        self.assertEqual(len(gaps), rep["counts"][STATUS_MISSING] + rep["counts"][STATUS_STALE])

    def test_round_trip_persistence(self):
        p = new_program(company="RT")
        add_evidence(p, "CC6.1", "a", collected_at=_iso(2))
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "prog.json")
            save_program(p, path)
            p2 = load_program(path)
        self.assertEqual(p2.company, "RT")
        self.assertEqual(len(p2.get("CC6.1").evidence), 1)


class TestCli(unittest.TestCase):
    def test_full_cli_flow(self):
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "p.json")
            self.assertEqual(main(["--file", path, "init", "--company", "Q"]), 0)
            self.assertTrue(os.path.exists(path))
            # init again without --force fails
            self.assertEqual(main(["--file", path, "init"]), 1)
            # add evidence
            self.assertEqual(
                main(["--file", path, "add", "CC6.1", "okta://x", "--by", "me"]), 0)
            # status json is valid
            self.assertEqual(main(["--file", path, "--format", "json", "status"]), 0)
            # report ok
            self.assertEqual(main(["--file", path, "report"]), 0)
            # gaps -> non-zero because controls still missing
            self.assertEqual(main(["--file", path, "gaps"]), 2)

    def test_missing_file_errors(self):
        self.assertEqual(main(["--file", "/no/such/file.json", "report"]), 1)

    def test_add_unknown_control_cli(self):
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "p.json")
            main(["--file", path, "init"])
            self.assertEqual(main(["--file", path, "add", "NOPE", "x"]), 1)


if __name__ == "__main__":
    unittest.main()
