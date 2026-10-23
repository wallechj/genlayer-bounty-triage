# Test flow (GenLayer Studio, hosted)

Paste `contracts/bounty_triage.py` into the Studio editor and deploy. You'll need
two Studio accounts: A (bounty owner) and B (researcher). All reward values below
are in wei.

## 1. Create a bounty (account A)

`create_bounty` with:

- title: `Acme DEX - Q4 audit bounty`
- scope: `Solidity contracts in github.com/acme/dex, tag v2.3.0 only. In scope: fund loss, access control, oracle manipulation.`
- rules: `Out of scope: frontend, gas griefing, known issues listed in AUDIT.md. One finding per report. Severity follows the table published here.`
- reward_critical: `5000000000000000000` (5 GEN)
- reward_high: `2000000000000000000`
- reward_medium: `500000000000000000`
- reward_low: `100000000000000000`

Expect: returns `0`.

Negative checks: empty title → `UserError: title is required`.

## 2. Submit reports (account B)

Valid-looking report, `submit_report`:

- bounty_id: `0`
- title: `Missing access control on settle() lets anyone drain the pool`
- description: `settle() in Pool.sol is external with no onlyOwner / role check. Anyone can call it after the epoch ends and redirect pending fees to an arbitrary address. Reproduced on a local fork of v2.3.0.`
- poc_url: `` (empty is fine — triage works on text alone)
- claimed_severity: `critical`

Expect: returns `0`.

Invalid-looking report, `submit_report`:

- title: `Typo in README`
- description: `The word "recieve" is misspelled in README.md.`
- poc_url: ``
- claimed_severity: `low`

Expect: returns `1`.

Negative checks: account A (owner) submitting → `UserError: bounty owner cannot submit reports`.
Bad severity string → `UserError: claimed_severity must be one of ...`.

## 3. Triage (any account)

`triage_report(0)` — watch the validator logs. Each validator independently runs the
audit prompt; the comparative equivalence check requires agreement on validity +
severity bucket. Expect return `"valid"`, and `get_report(0)` shows a ruled severity
(high or critical), a one-sentence summary, and the matching decided reward.

`triage_report(1)` — expect `"invalid"`, `ruled_severity: "none"`, `decided_reward: 0`.
A typo report should not survive triage.

Re-running `triage_report(0)` → `UserError: report has already been triaged`.

## 4. Lifecycle + payment trail (account A)

- `pause_bounty(0)`, then submit as B → `UserError: bounty is not open for submissions`.
- `reopen_bounty(0)`.
- `mark_paid(0)` → `get_report(0).status == "paid"`.
- `mark_paid(1)` → `UserError: only valid (triaged) reports can be marked paid`.
- `mark_paid` as account B → `UserError: only the bounty owner can mark a report paid`.
- `close_bounty(0)` ends the program.

## 5. Views

`get_bounty(0)` returns the full bounty incl. reward table; `get_bounty_count()` → `1`;
`get_report_count()` → `2`.
