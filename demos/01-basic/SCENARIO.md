# Demo 01 - Basic SOC 2 readiness check

This demo shows SOC2BOX tracking a real-ish compliance program for a small
SaaS company (`demo_program.json`). The program is seeded with the default
Trust Services Criteria common-criteria controls, and some have evidence
attached at varying ages so you can see all three live states:

- **satisfied** - fresh evidence within the control's review cadence
- **stale** - evidence exists but has aged past the cadence window
- **missing** - no evidence collected yet

## Why evidence ages

SOC 2 Type II audits require evidence to *recur* across the observation
period. SOC2BOX models this: each control has a `cadence_days` window. The
monitoring controls (CC4.1, CC7.2) recur every 30 days, access controls every
90, policy controls yearly. Old evidence automatically flips a control back to
`stale`, exactly like an auditor would flag it.

The sample data was authored relative to **2026-06-08**:
- CC6.1 MFA export: 5 days old  -> satisfied (90d cadence)
- CC8.1 change-mgmt log: 10 days old -> satisfied
- CC4.1 vuln scan: 45 days old -> **stale** (30d cadence)
- CC7.2 alert config: 120 days old -> **stale** (30d cadence)
- CC1.1 ethics policy: 30 days old -> satisfied (365d cadence)
- everything else: **missing**

## Run it

```sh
# Overall readiness summary
python -m soc2box --file demos/01-basic/demo_program.json report

# Same, machine-readable
python -m soc2box --file demos/01-basic/demo_program.json --format json report

# What still needs work (exits non-zero -> works as a CI gate)
python -m soc2box --file demos/01-basic/demo_program.json gaps

# Collect a fresh vuln scan to clear the CC4.1 gap
python -m soc2box --file demos/01-basic/demo_program.json add CC4.1 \
    s3://evidence/2026-06-08-nessus-scan.pdf --by jordan --note "weekly scan"
```

Expected: `report` shows a partial readiness percentage; `gaps` lists CC4.1
and CC7.2 (stale) plus the still-uncollected controls, missing ones first.
