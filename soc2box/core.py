"""SOC2BOX core engine.

Models a SOC 2 compliance program as a set of Trust Services Criteria (TSC)
controls, each backed by dated evidence artifacts. Evidence has a freshness
window; once it ages past the control's review cadence it is considered stale
and the control reverts to needing attention. This mirrors how real SOC 2
Type II audits require evidence to recur across the observation period.

Pure standard library. JSON on disk, deterministic logic, no network.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone, timedelta
from typing import Any, Dict, List, Optional

# ---------------------------------------------------------------------------
# Status constants
# ---------------------------------------------------------------------------
STATUS_SATISFIED = "satisfied"      # fresh evidence present
STATUS_STALE = "stale"              # evidence exists but aged out of cadence
STATUS_MISSING = "missing"          # no evidence at all
STATUS_NA = "not_applicable"        # control scoped out

_SCHEMA_VERSION = 1


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _parse_dt(value: str) -> datetime:
    """Parse an ISO-8601 timestamp, tolerating a trailing 'Z'."""
    if value.endswith("Z"):
        value = value[:-1] + "+00:00"
    dt = datetime.fromisoformat(value)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------
@dataclass
class Evidence:
    """A single dated evidence artifact attached to a control."""
    artifact: str
    collected_at: str            # ISO-8601 UTC
    collected_by: str = "unknown"
    note: str = ""

    def age_days(self, ref: Optional[datetime] = None) -> float:
        ref = ref or _now()
        return (ref - _parse_dt(self.collected_at)).total_seconds() / 86400.0


@dataclass
class Control:
    """A SOC 2 Trust Services Criteria control."""
    id: str                      # e.g. "CC6.1"
    category: str                # e.g. "Logical Access"
    title: str
    cadence_days: int = 90       # how often evidence must recur
    applicable: bool = True
    owner: str = ""
    evidence: List[Evidence] = field(default_factory=list)

    def latest_evidence(self) -> Optional[Evidence]:
        if not self.evidence:
            return None
        return max(self.evidence, key=lambda e: _parse_dt(e.collected_at))


@dataclass
class Program:
    """A full SOC 2 program: company + scoped controls."""
    company: str = "Acme Inc"
    framework: str = "SOC 2 Type II"
    controls: List[Control] = field(default_factory=list)
    schema_version: int = _SCHEMA_VERSION

    def get(self, control_id: str) -> Optional[Control]:
        cid = control_id.strip().upper()
        for c in self.controls:
            if c.id.upper() == cid:
                return c
        return None


# ---------------------------------------------------------------------------
# Default control library (subset of the 2017 TSC common criteria)
# ---------------------------------------------------------------------------
DEFAULT_CONTROLS: List[Dict[str, Any]] = [
    {"id": "CC1.1", "category": "Control Environment", "title": "Board oversight & integrity / ethics policy", "cadence_days": 365},
    {"id": "CC2.1", "category": "Communication", "title": "Internal security policies communicated to staff", "cadence_days": 365},
    {"id": "CC4.1", "category": "Monitoring", "title": "Ongoing monitoring / vulnerability scans", "cadence_days": 30},
    {"id": "CC5.2", "category": "Control Activities", "title": "Technology controls over infrastructure", "cadence_days": 90},
    {"id": "CC6.1", "category": "Logical Access", "title": "Logical access provisioning & MFA", "cadence_days": 90},
    {"id": "CC6.2", "category": "Logical Access", "title": "User access reviews / least privilege", "cadence_days": 90},
    {"id": "CC6.3", "category": "Logical Access", "title": "Access removal on termination", "cadence_days": 90},
    {"id": "CC7.2", "category": "System Operations", "title": "Security incident detection & alerting", "cadence_days": 30},
    {"id": "CC7.3", "category": "System Operations", "title": "Incident response & remediation", "cadence_days": 90},
    {"id": "CC8.1", "category": "Change Management", "title": "Change management / code review & approvals", "cadence_days": 90},
    {"id": "A1.2", "category": "Availability", "title": "Backups & disaster recovery testing", "cadence_days": 180},
]


def new_program(company: str = "Acme Inc", framework: str = "SOC 2 Type II") -> Program:
    """Build a fresh program seeded with the default control library."""
    controls = [Control(**spec) for spec in DEFAULT_CONTROLS]
    return Program(company=company, framework=framework, controls=controls)


# ---------------------------------------------------------------------------
# Persistence
# ---------------------------------------------------------------------------
def program_to_dict(p: Program) -> Dict[str, Any]:
    return asdict(p)


def program_from_dict(d: Dict[str, Any]) -> Program:
    controls = []
    for c in d.get("controls", []):
        ev = [Evidence(**e) for e in c.get("evidence", [])]
        cc = {k: v for k, v in c.items() if k != "evidence"}
        controls.append(Control(evidence=ev, **cc))
    return Program(
        company=d.get("company", "Acme Inc"),
        framework=d.get("framework", "SOC 2 Type II"),
        controls=controls,
        schema_version=d.get("schema_version", _SCHEMA_VERSION),
    )


def load_program(path: str) -> Program:
    with open(path, "r", encoding="utf-8") as fh:
        return program_from_dict(json.load(fh))


def save_program(p: Program, path: str) -> None:
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(program_to_dict(p), fh, indent=2, sort_keys=True)
        fh.write("\n")


# ---------------------------------------------------------------------------
# Engine logic
# ---------------------------------------------------------------------------
def add_evidence(p: Program, control_id: str, artifact: str,
                 collected_by: str = "unknown", note: str = "",
                 collected_at: Optional[str] = None) -> Evidence:
    """Attach a dated evidence artifact to a control. Raises KeyError if the
    control id is not in the program."""
    ctrl = p.get(control_id)
    if ctrl is None:
        raise KeyError(f"unknown control: {control_id}")
    ts = collected_at or _now().isoformat()
    _parse_dt(ts)  # validate format; raises ValueError on bad input
    ev = Evidence(artifact=artifact, collected_at=ts,
                  collected_by=collected_by, note=note)
    ctrl.evidence.append(ev)
    return ev


def control_status(ctrl: Control, ref: Optional[datetime] = None) -> Dict[str, Any]:
    """Compute the live status of one control given evidence freshness."""
    ref = ref or _now()
    if not ctrl.applicable:
        status = STATUS_NA
        age = None
        days_left = None
    else:
        latest = ctrl.latest_evidence()
        if latest is None:
            status = STATUS_MISSING
            age = None
            days_left = None
        else:
            age = round(latest.age_days(ref), 2)
            days_left = round(ctrl.cadence_days - age, 2)
            status = STATUS_SATISFIED if age <= ctrl.cadence_days else STATUS_STALE
    return {
        "id": ctrl.id,
        "category": ctrl.category,
        "title": ctrl.title,
        "owner": ctrl.owner,
        "cadence_days": ctrl.cadence_days,
        "evidence_count": len(ctrl.evidence),
        "latest_age_days": age,
        "days_until_stale": days_left,
        "status": status,
    }


def program_readiness(p: Program, ref: Optional[datetime] = None) -> Dict[str, Any]:
    """Aggregate readiness across all in-scope controls.

    Readiness score = satisfied / applicable controls, as a percentage.
    """
    ref = ref or _now()
    rows = [control_status(c, ref) for c in p.controls]
    applicable = [r for r in rows if r["status"] != STATUS_NA]
    counts = {
        STATUS_SATISFIED: 0,
        STATUS_STALE: 0,
        STATUS_MISSING: 0,
        STATUS_NA: 0,
    }
    for r in rows:
        counts[r["status"]] += 1
    denom = len(applicable)
    score = round(100.0 * counts[STATUS_SATISFIED] / denom, 1) if denom else 0.0
    return {
        "company": p.company,
        "framework": p.framework,
        "generated_at": ref.isoformat(),
        "total_controls": len(rows),
        "applicable_controls": denom,
        "counts": counts,
        "readiness_pct": score,
        "audit_ready": denom > 0 and counts[STATUS_SATISFIED] == denom,
        "controls": rows,
    }


def gap_list(p: Program, ref: Optional[datetime] = None) -> List[Dict[str, Any]]:
    """Return controls that need attention (missing or stale evidence),
    most urgent first."""
    ref = ref or _now()
    rows = [control_status(c, ref) for c in p.controls]
    gaps = [r for r in rows if r["status"] in (STATUS_MISSING, STATUS_STALE)]

    def sort_key(r: Dict[str, Any]):
        # missing is most urgent; then most-overdue (smallest days_until_stale)
        missing_first = 0 if r["status"] == STATUS_MISSING else 1
        dleft = r["days_until_stale"]
        dleft = dleft if dleft is not None else -1e9
        return (missing_first, dleft)

    gaps.sort(key=sort_key)
    return gaps
