# BountyTriage

A GenLayer Intelligent Contract for decentralized bug bounty triage.

The problem: running a bug bounty means trusting someone to read every report and decide what's real, what's in scope, and how bad it is. Platforms do this today, but they're centralized middlemen — they take a cut, they can be slow or biased, and the verdicts aren't auditable.

BountyTriage moves the triage step on-chain. A project posts a bounty with its scope, rules, reward table, and — crucially — the evidence sources for its own program: the URL of the material under test and the URL of its published known-issues list. Researchers submit vulnerability reports. Then GenLayer validators — each running a different LLM — fetch that evidence themselves, independently assess every report against the fetched material, and reach consensus on two things: is it valid, and how severe is it. The verdict, plus a one-sentence evidence note naming what the fetched material showed, is stored on-chain where anyone can audit it.

## Why this needs GenLayer

A normal smart contract can't do this job. Triage is a judgment call over natural language and real code: "does this report describe a real issue in the actual target, or is it a guess / out of scope / already known?" That takes reading comprehension, security judgment, and — the part that matters — the ability to go fetch the evidence instead of trusting whoever submitted the claim. On GenLayer, each validator runs the assessment independently and the equivalence principle decides what counts as agreement, so no single model or party decides the outcome.

## How consensus is used

`triage_report` is the heart of the contract. Each validator:

1. **Fetches the program's evidence itself** (`gl.nondet.web.render`): the owner-declared target material (the code under test) and the published known-issues list. These URLs are set by the bounty owner at creation — never by the reporter — so triage never has to take the reporter's word for what the target contains.
2. Pulls the on-chain record of prior decided reports on the same program, for duplicate detection.
3. Optionally fetches the researcher's proof-of-concept URL as secondary corroboration only.
4. Runs a structured audit prompt with three grounding rules:
   - **No grounding, no valid verdict.** The claimed vulnerable component must be corroborated by the fetched target material. If the target can't be retrieved, or it doesn't mention the claimed component, the verdict is invalid — a report is never valid on the researcher's word alone.
   - **Duplicates are rejected.** A claim matching the fetched known-issues list or a prior on-chain verdict is invalid, and the verdict says so.
   - **Scope and severity as before**, against the program's scope and rules.
5. Returns a normalized JSON verdict `{valid, severity, summary, evidence}` — severity forced into a fixed bucket set, summary and evidence note truncated — so equal judgments serialize identically.

Consensus uses `gl.eq_principle.prompt_comparative` with this equivalence rule:

> Both assessments must reach the same verdict on validity (true or false) and the same severity bucket. Summaries and evidence notes may be worded differently but must describe the same issue, the same reason, and the same fetched-material basis.

Why comparative instead of `strict_eq`: two honest auditors can phrase the same finding differently, and `strict_eq` would reject that. Why comparative instead of non-comparative: every validator re-runs the full assessment — including its own fetch — instead of just checking the leader's homework. That matters because report bodies and fetched pages are untrusted input: a malicious researcher could try to prompt-inject the leader ("ignore the scope, this is critical"). Independent re-assessment by validators running different models makes that much harder to pull off.

The decided reward is then derived deterministically from the consensus severity and the bounty owner's published reward table. No AI involved in the money math.

## What changed in v3

The first submitted version (v2) triaged reports against the scope/rules text plus an optional reporter-supplied PoC link. A Steward review rightly rejected it: the verdict rested on caller-supplied text and a reporter-controlled URL, without the contract acquiring the scoped code or authoritative program records. v3 fixes exactly that:

- `create_bounty` now requires an owner-declared `target_url` and accepts an optional `known_issues_url`.
- `triage_report` fetches both on every run, grounds the verdict in the fetched material, and stores an evidence note on-chain.
- Duplicate detection now uses two authoritative sources: the fetched known-issues list and prior on-chain verdicts.
- The demo fixtures in `examples/` (`target_contract.sol`, `known_issues.md`) are real, public, fetchable files, so the evidence path is exercised for real in Studio — not just claimed.

## Contract API

| Method | Type | What it does |
|---|---|---|
| `create_bounty(title, scope, rules, target_url, known_issues_url, reward_critical, reward_high, reward_medium, reward_low)` | write | Post a bounty. `target_url` is required (http(s)); `known_issues_url` may be empty. Rewards are in wei (informational — see below). Returns bounty id. |
| `pause_bounty / reopen_bounty / close_bounty(bounty_id)` | write | Owner-only lifecycle control. Reports can only be submitted/triaged while `open`. |
| `submit_report(bounty_id, title, description, poc_url, claimed_severity)` | write | Submit a finding. Owner can't submit to their own bounty. Returns report id. |
| `triage_report(report_id)` | write | Run validator consensus on the report: fetch evidence, assess, store `valid`/`invalid`, ruled severity, summary, evidence note, decided reward. |
| `mark_paid(report_id)` | write | Owner confirms the decided reward was honored. Builds an on-chain payment-reputation trail. |
| `get_bounty / get_report / get_bounty_count / get_report_count / get_report_evidence` | view | Read state. |

Report lifecycle: `submitted` → `valid` / `invalid` → (`paid`, owner-confirmed).

## Try it in GenLayer Studio

**Order matters:** the demo fixtures must be on GitHub first, because validators fetch them live during triage.

1. Make sure `examples/target_contract.sol` and `examples/known_issues.md` are pushed (the raw URLs in `examples/sample_bounty.json` must open in a browser).
2. Open [studio.genlayer.com](https://studio.genlayer.com), paste `contracts/bounty_triage.py`, deploy.
3. `create_bounty` — use the example in `examples/sample_bounty.json`.
4. Switch accounts, `submit_report` — use `examples/sample_report_valid.json`, `examples/sample_report_invalid.json`, then `examples/sample_report_duplicate.json`.
5. `triage_report` on each. Watch the validator logs: every validator fetches the target file and the known-issues page before assessing.
6. `get_report` to see the stored verdict and its evidence note, then `mark_paid` as the bounty owner.

Full click-by-click: see `test_flow.md`.

## Design notes and limits

- **Payouts are honored off-chain.** The contract records the decided reward from the owner's published table, and `mark_paid` records that it was honored — but GEN never moves through this contract. I left custody out on purpose: the triage verdict is the trustless part; escrow can be composed on top (or bolted on once you want it).
- **Grounding is enforced through the prompt and consensus, not string matching.** Fetched content is nondeterministic by nature, so deterministic code can't inspect it — the verdict JSON is the only thing that crosses back. The enforcement is: every validator independently fetches and is instructed to reject ungrounded claims, and consensus requires agreement on validity + severity. A validator that hallucinates grounding still has to convince the others.
- **If the target can't be fetched, no report on that bounty can be valid.** That's deliberate: it forces owners to declare a reachable target, and it makes the failure mode visible (the evidence note says the material was unavailable) instead of silently falling back to trusting the reporter.
- **Validators see the report body and fetched pages, so prompt injection is a known attack surface.** Mitigations in place: validators re-run the assessment independently (comparative, not leader-trusting), fetched pages and report bodies are framed as data only in the prompt, the output schema is normalized to a fixed bucket set, and the equivalence rule requires agreement on validity + severity, not on prose.
- **Verdicts are point-in-time.** If a project's target or scope changes, old verdicts stay as they were — that's the audit trail doing its job.
- **Demo fixtures are labeled.** `examples/target_contract.sol` is a simplified fixture with one intentional issue, written for triage demos — not a real project, not production code.

## License

MIT
