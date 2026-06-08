"""SOC2BOX command-line interface.

Subcommands:
  init      Create a new program file seeded with default TSC controls.
  add       Attach a dated evidence artifact to a control.
  status    Show per-control status (satisfied / stale / missing).
  report    Show overall audit-readiness summary.
  gaps      List controls needing attention, most urgent first.

Global flags: --version, --format {table,json}.
Exit non-zero on any failure.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from typing import Any, Dict, List, Optional

from . import TOOL_NAME, TOOL_VERSION
from .core import (
    new_program,
    load_program,
    save_program,
    add_evidence,
    control_status,
    program_readiness,
    gap_list,
)

DEFAULT_FILE = "soc2_program.json"


def _emit(obj: Any, fmt: str, table_fn) -> None:
    if fmt == "json":
        print(json.dumps(obj, indent=2, sort_keys=True))
    else:
        table_fn(obj)


def _print_rows(rows: List[Dict[str, Any]]) -> None:
    if not rows:
        print("(no controls)")
        return
    hdr = f"{'ID':<7} {'STATUS':<14} {'AGE':>7} {'LEFT':>7}  TITLE"
    print(hdr)
    print("-" * len(hdr))
    for r in rows:
        age = "-" if r["latest_age_days"] is None else f"{r['latest_age_days']:.0f}d"
        left = "-" if r["days_until_stale"] is None else f"{r['days_until_stale']:.0f}d"
        print(f"{r['id']:<7} {r['status']:<14} {age:>7} {left:>7}  {r['title']}")


def _load(path: str):
    if not os.path.exists(path):
        raise FileNotFoundError(
            f"program file not found: {path} (run '{TOOL_NAME} init' first)")
    return load_program(path)


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog=TOOL_NAME,
                                description="Self-hosted SOC 2 evidence collector & control tracker.")
    p.add_argument("--version", action="version",
                   version=f"{TOOL_NAME} {TOOL_VERSION}")
    p.add_argument("--format", choices=["table", "json"], default="table",
                   help="output format (default: table)")
    p.add_argument("--file", default=DEFAULT_FILE,
                   help=f"program file path (default: {DEFAULT_FILE})")
    sub = p.add_subparsers(dest="command", required=True)

    pi = sub.add_parser("init", help="create a new program seeded with default controls")
    pi.add_argument("--company", default="Acme Inc")
    pi.add_argument("--framework", default="SOC 2 Type II")
    pi.add_argument("--force", action="store_true", help="overwrite existing file")

    pa = sub.add_parser("add", help="attach evidence to a control")
    pa.add_argument("control_id")
    pa.add_argument("artifact", help="path/url/description of the evidence")
    pa.add_argument("--by", default="unknown", help="who collected it")
    pa.add_argument("--note", default="")
    pa.add_argument("--at", default=None, help="ISO-8601 collection time (default: now)")

    sub.add_parser("status", help="per-control evidence status")
    sub.add_parser("report", help="overall audit-readiness summary")
    sub.add_parser("gaps", help="controls needing attention, most urgent first")
    return p


def main(argv: Optional[List[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    fmt = args.format

    try:
        if args.command == "init":
            if os.path.exists(args.file) and not args.force:
                print(f"error: {args.file} already exists (use --force)", file=sys.stderr)
                return 1
            prog = new_program(company=args.company, framework=args.framework)
            save_program(prog, args.file)
            summary = {
                "created": args.file,
                "company": prog.company,
                "framework": prog.framework,
                "controls": len(prog.controls),
            }
            _emit(summary, fmt, lambda s: print(
                f"Created {s['created']}: {s['company']} / {s['framework']} "
                f"({s['controls']} controls)"))
            return 0

        if args.command == "add":
            prog = _load(args.file)
            ev = add_evidence(prog, args.control_id, args.artifact,
                              collected_by=args.by, note=args.note,
                              collected_at=args.at)
            save_program(prog, args.file)
            out = {
                "control": args.control_id.upper(),
                "artifact": ev.artifact,
                "collected_at": ev.collected_at,
                "collected_by": ev.collected_by,
            }
            _emit(out, fmt, lambda o: print(
                f"Added evidence to {o['control']}: {o['artifact']} "
                f"(by {o['collected_by']} @ {o['collected_at']})"))
            return 0

        if args.command == "status":
            prog = _load(args.file)
            rows = [control_status(c) for c in prog.controls]
            _emit(rows, fmt, _print_rows)
            return 0

        if args.command == "report":
            prog = _load(args.file)
            rep = program_readiness(prog)

            def show(r: Dict[str, Any]) -> None:
                print(f"{r['company']} - {r['framework']}")
                print(f"Readiness: {r['readiness_pct']}%  "
                      f"({r['counts']['satisfied']}/{r['applicable_controls']} satisfied)")
                c = r["counts"]
                print(f"  satisfied={c['satisfied']} stale={c['stale']} "
                      f"missing={c['missing']} n/a={c['not_applicable']}")
                print(f"Audit ready: {'YES' if r['audit_ready'] else 'NO'}")

            _emit(rep, fmt, show)
            return 0

        if args.command == "gaps":
            prog = _load(args.file)
            gaps = gap_list(prog)
            _emit(gaps, fmt, _print_rows)
            # non-zero exit when gaps remain: useful as a CI gate
            return 2 if gaps else 0

    except (KeyError, ValueError, FileNotFoundError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    parser.print_help(sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
