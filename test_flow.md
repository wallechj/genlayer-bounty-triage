# Test flow (GenLayer Studio, hosted)

Paste `contracts/bounty_triage.py` into the Studio editor and deploy. You'll need
two Studio accounts: A (bounty owner) and B (researcher). All reward values below
are in wei.

## 0. Prerequisite: fixtures must be live first

Validators fetch the demo target material and known-issues list from public URLs
during triage, so push `examples/` to GitHub BEFORE running this flow and check
both URLs open in a browser:

- https://raw.githubusercontent.com/wallechj/genlayer-bounty-triage/main/examples/target_contract.sol
- https://raw.githubusercontent.com/wallechj/genlayer-bounty-triage/main/examples/known_issues.md

If your default branch isn't `main`, adjust the URLs in `sample_bounty.json` first.

## 1. Create a bounty (account A)

`create_bounty` with:

- title: `Acme DEX - Q4 audit bounty`
- scope: `Solidity contracts in the AcmePool target file (see target_url). In scope: fund loss, access control flaws, oracle manipulation.`
- rules: `Out of scope: frontend, gas griefing, issues already listed in the published known-issues page. One finding per report. Severity follows the published reward table.`
- target_url: `https://raw.githubusercontent.com/wallechj/genlayer-bounty-triage/main/examples/target_contract.sol`
- known_issues_url: `https://raw.githubusercontent.com/wallechj/genlayer-bounty-triage/main/examples/known_issues.md`
- reward_critical: `5000000000000000000` (5 GEN)
- reward_high: `2000000000000000000`
- reward_medium: `500000000000000000`
- reward_low: `100000000000000000`

Expect: returns `0`.

Negative checks: empty target_url → `UserError: target_url is required`.
Non-URL target_url → `UserError: target_url must be an http(s) URL`.

## 2. Submit reports (account B)

Valid report, `submit_report` (matches the fetched fixture: `settle()` with no
access check):

- bounty_id: `0`
- title: `Missing access control on settle() lets anyone drain pending fees`
- description: `settle() in AcmePool is declared external with no onlyOwner / role check. Anyone can call settle(user, to) and redirect that user's pending fees to an arbitrary address. Reproduced locally: deployed AcmePool, called settle(victim, attacker) from a fresh account, observed the pending fee balance move to attacker.`
- poc_url: ``
- claimed_severity: `critical`

Expect: returns `0`.

Unknown-target report, `submit_report` (claims a contract that is NOT in the
fetched target material):

- title: `Flash loan manipulation in FlashLender.sol drains the pool`
- description: `FlashLender.sol allows flash loans with no fee check, letting an attacker borrow the whole pool balance, manipulate the price, and repay in the same transaction for a risk-free profit.`
- poc_url: ``
- claimed_severity: `high`

Expect: returns `1`.

Duplicate report, `submit_report` (matches the fetched known-issues list:
deposit gas griefing is an accepted risk):

- title: `Gas griefing via deposit() inflates bookkeeping`
- description: `Calling deposit() repeatedly with tiny amounts inflates pendingFees bookkeeping and bloats state. Each dust deposit adds an entry the pool must track.`
- poc_url: ``
- claimed_severity: `medium`

Expect: returns `2`.

Negative checks: account A (owner) submitting → `UserError: bounty owner cannot submit reports`.
Bad severity string → `UserError: claimed_severity must be one of ...`.

## 3. Triage (any account)

Watch the validator logs on each call: every validator fetches the target file
and the known-issues page before assessing.

`triage_report(0)` — expect `"valid"`, ruled severity high or critical, decided
reward matching the ruled bucket, and `get_report_evidence(0)` naming the fetched
`settle()` code (e.g. that the target file shows `settle()` with no access check).

`triage_report(1)` — expect `"invalid"`, `ruled_severity: "none"`, `decided_reward: 0`,
and evidence noting that `FlashLender.sol` does not appear in the fetched target
material. A claim about a component the contract never saw must not survive triage.

`triage_report(2)` — expect `"invalid"`, `ruled_severity: "none"`, `decided_reward: 0`,
and evidence noting the deposit gas-griefing entry in the fetched known-issues list
(or the prior on-chain record). Known issues are not new findings.

Re-running `triage_report(0)` → `UserError: report has already been triaged`.

## 4. Ungroundable bounty: no fetch, no valid verdict (account A)

`create_bounty` with the same scope/rules/rewards but:

- target_url: `https://example.invalid/acme/target.sol` (unresolvable domain)
- known_issues_url: ``

Expect: returns `1`. Then as B, `submit_report` the settle() report against
bounty `1` (expect report id `3`), and `triage_report(3)` — expect `"invalid"` with
evidence noting the target material could not be retrieved. This is the grounding
rule enforced: without fetched evidence, a report cannot be valid, even if the
claim itself sounds plausible.

## 5. Lifecycle + payment trail (account A)

- `pause_bounty(0)`, then submit as B → `UserError: bounty is not open for submissions`.
- `reopen_bounty(0)`.
- `mark_paid(0)` → `get_report(0).status == "paid"`.
- `mark_paid(1)` → `UserError: only valid (triaged) reports can be marked paid`.
- `mark_paid` as account B → `UserError: only the bounty owner can mark a report paid`.
- `close_bounty(0)` ends the program.

## 6. Views

`get_bounty(0)` returns the full bounty incl. target_url, known_issues_url, and
reward table; `get_bounty_count()` → `2`; `get_report_count()` → `4`.
`get_report_evidence(n)` returns each verdict's one-sentence evidence note.
