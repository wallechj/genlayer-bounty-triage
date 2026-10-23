# BountyTriage

A GenLayer Intelligent Contract for decentralized bug bounty triage.

The problem: running a bug bounty means trusting someone to read every report and decide what's real, what's in scope, and how bad it is. Platforms do this today, but they're centralized middlemen — they take a cut, they can be slow or biased, and the verdicts aren't auditable.

BountyTriage moves the triage step on-chain. A project posts a bounty with its scope, rules, and reward table. Researchers submit vulnerability reports. Then GenLayer validators — each running a different LLM — independently assess every report against the program's scope and rules, and reach consensus on two things: is it valid, and how severe is it. The verdict is stored on-chain where anyone can audit it.

## Why this needs GenLayer

A normal smart contract can't do this job. Triage is a judgment call over natural language: "is this report describing a real issue inside our scope, or is it a guess / out of scope / already a known risk?" That takes reading comprehension and security judgment. On GenLayer, each validator runs the assessment independently and the equivalence principle decides what counts as agreement — so no single model or party decides the outcome.

## How consensus is used

`triage_report` is the heart of the contract. Each validator:

1. Optionally fetches the researcher's proof-of-concept URL (`gl.nondet.web.render`)
2. Runs a structured audit prompt: scope + rules + report + claimed severity → JSON verdict `{valid, severity, summary}`
3. Normalizes the verdict (severity forced into a fixed bucket set, summary truncated) so equal judgments serialize identically

Consensus uses `gl.eq_principle.prompt_comparative` with this equivalence rule:

> Both assessments must reach the same verdict on validity (true or false) and the same severity bucket. Summaries may be worded differently but must describe the same issue and the same reason.

Why comparative instead of `strict_eq`: two honest auditors can phrase the same finding differently, and `strict_eq` would reject that. Why comparative instead of non-comparative: every validator re-runs the full assessment instead of just checking the leader's homework. That matters because report bodies are untrusted input — a malicious researcher could try to prompt-inject the leader ("ignore the scope, this is critical"). Independent re-assessment by validators running different models makes that much harder to pull off.

The decided reward is then derived deterministically from the consensus severity and the bounty owner's published reward table. No AI involved in the money math.

## Contract API

| Method | Type | What it does |
|---|---|---|
| `create_bounty(title, scope, rules, reward_critical, reward_high, reward_medium, reward_low)` | write | Post a bounty. Rewards are in wei (informational — see below). Returns bounty id. |
| `pause_bounty / reopen_bounty / close_bounty(bounty_id)` | write | Owner-only lifecycle control. Reports can only be submitted/triaged while `open`. |
| `submit_report(bounty_id, title, description, poc_url, claimed_severity)` | write | Submit a finding. Owner can't submit to their own bounty. Returns report id. |
| `triage_report(report_id)` | write | Run validator consensus on the report. Sets `valid`/`invalid`, ruled severity, summary, decided reward. |
| `mark_paid(report_id)` | write | Owner confirms the decided reward was honored. Builds an on-chain payment-reputation trail. |
| `get_bounty / get_report / get_bounty_count / get_report_count` | view | Read state. |

Report lifecycle: `submitted` → `valid` / `invalid` → (`paid`, owner-confirmed).

## Try it in GenLayer Studio

1. Open [studio.genlayer.com](https://studio.genlayer.com), paste `contracts/bounty_triage.py`, deploy.
2. `create_bounty` — use the example in `examples/sample_bounty.json`.
3. Switch accounts, `submit_report` — use `examples/sample_report_valid.json`, then `examples/sample_report_invalid.json`.
4. `triage_report` on each. Watch the validator logs: every validator fetches the PoC (if given) and assesses independently before agreeing.
5. `get_report` to see the stored verdict, then `mark_paid` as the bounty owner.

Full click-by-click: see `test_flow.md`.

## Design notes and limits

- **Payouts are honored off-chain.** The contract records the decided reward from the owner's published table, and `mark_paid` records that it was honored — but GEN never moves through this contract. I left custody out on purpose: the triage verdict is the trustless part; escrow can be composed on top (or bolted on once you want it).
- **PoC fetch is best-effort.** If the URL is dead or unrenderable, triage proceeds on the report text alone. A 404 doesn't auto-reject — plenty of legit reports link to repos that need auth.
- **Validators see the report body, so prompt injection is a known attack surface.** Mitigations in place: validators re-run the assessment independently (comparative, not leader-trusting), the output schema is normalized to a fixed bucket set, and the equivalence rule requires agreement on validity + severity, not on prose.
- **Verdicts are point-in-time.** If a project's scope changes, old verdicts stay as they were — that's the audit trail doing its job.

## License

MIT
