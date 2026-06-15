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


class TestHardening(unittest.TestCase):
    """Edge-case and error-path tests added during production hardening."""

    # --- core: malformed / invalid input ---

    def test_empty_artifact_raises(self):
        """add_evidence must reject a blank artifact string."""
        p = new_program()
        with self.assertRaises(ValueError):
            add_evidence(p, "CC6.1", "")
        with self.assertRaises(ValueError):
            add_evidence(p, "CC6.1", "   ")

    def test_empty_company_raises(self):
        with self.assertRaises(ValueError):
            new_program(company="")
        with self.assertRaises(ValueError):
            new_program(company="   ")

    def test_empty_framework_raises(self):
        with self.assertRaises(ValueError):
            new_program(framework="")

    def test_program_from_dict_missing_required_control_field(self):
        """A control JSON dict without 'id' must raise ValueError, not TypeError."""
        from soc2box.core import program_from_dict
        d = {
            "company": "X",
            "framework": "SOC 2",
            "schema_version": 1,
            "controls": [{"category": "C", "title": "T"}],
        }
        with self.assertRaises(ValueError):
            program_from_dict(d)

    def test_program_from_dict_extra_fields_ignored(self):
        """A control with unknown extra fields must deserialise cleanly."""
        from soc2box.core import program_from_dict
        d = {
            "company": "X",
            "framework": "SOC 2",
            "schema_version": 1,
            "controls": [
                {
                    "id": "CC6.1",
                    "category": "Logical Access",
                    "title": "MFA",
                    "cadence_days": 90,
                    "applicable": True,
                    "owner": "",
                    "evidence": [],
                    "future_field": "ignored",
                }
            ],
        }
        prog = program_from_dict(d)
        self.assertIsNotNone(prog.get("CC6.1"))

    # --- CLI: malformed JSON file -> exit 1, not traceback ---

    def test_malformed_json_exits_1(self):
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "bad.json")
            with open(path, "w") as f:
                f.write("{not valid json")
            self.assertEqual(main(["--file", path, "report"]), 1)

    def test_missing_control_field_json_exits_1(self):
        """A structurally broken JSON program (missing 'id') exits 1 cleanly."""
        import json as _json
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "bad.json")
            with open(path, "w") as f:
                _json.dump(
                    {
                        "company": "X",
                        "framework": "SOC 2",
                        "schema_version": 1,
                        "controls": [{"category": "C", "title": "T"}],
                    },
                    f,
                )
            self.assertEqual(main(["--file", path, "report"]), 1)

    # --- MCP server module is importable (no top-level crash) ---

    def test_mcp_server_importable(self):
        import importlib
        mod = importlib.import_module("soc2box.mcp_server")
        self.assertTrue(callable(mod.serve))

    # --- gaps returns exit 0 when all controls are satisfied ---

    def test_gaps_zero_exit_when_all_satisfied(self):
        from soc2box import gap_list
        p = new_program()
        ref = NOW
        # satisfy every applicable control
        for c in p.controls:
            if c.applicable:
                add_evidence(p, c.id, "evidence", collected_at=_iso(1))
        gaps = gap_list(p, ref)
        self.assertEqual(gaps, [])

    def test_gaps_cli_exit_0_when_all_satisfied(self):
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "p.json")
            main(["--file", path, "init"])
            from soc2box import load_program, save_program
            p = load_program(path)
            for c in p.controls:
                if c.applicable:
                    add_evidence(p, c.id, "ev", collected_at=_iso(1))
            save_program(p, path)
            self.assertEqual(main(["--file", path, "gaps"]), 0)


if __name__ == "__main__":
    unittest.main()
