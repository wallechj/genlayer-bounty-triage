# { "Depends": "py-genlayer:1jb45aa8ynh2a9c9xn3b7qqh8sm5q93hwfp7jqmwsfhh8jpz09h6" }
from genlayer import *
import json
from dataclasses import dataclass


@allow_storage
@dataclass
class Bounty:
    owner: str
    title: str
    scope: str
    rules: str
    reward_critical: u256
    reward_high: u256
    reward_medium: u256
    reward_low: u256
    status: str  # open | paused | closed
    created_at: u256


@allow_storage
@dataclass
class Report:
    bounty_id: u256
    researcher: str
    title: str
    description: str
    poc_url: str
    claimed_severity: str
    status: str  # submitted | valid | invalid | paid
    ruled_severity: str  # critical | high | medium | low | none
    triage_summary: str
    decided_reward: u256
    submitted_at: u256


SEVERITIES = ("critical", "high", "medium", "low")


class BountyTriage(gl.Contract):
    bounty_counter: u256
    report_counter: u256
    bounties: TreeMap[u256, Bounty]
    reports: TreeMap[u256, Report]

    def __init__(self):
        self.bounty_counter = u256(0)
        self.report_counter = u256(0)

    # ---------- bounty lifecycle ----------

    @gl.public.write
    def create_bounty(
        self,
        title: str,
        scope: str,
        rules: str,
        reward_critical: u256,
        reward_high: u256,
        reward_medium: u256,
        reward_low: u256,
    ) -> u256:
        if not title.strip():
            raise gl.vm.UserError("title is required")
        if not scope.strip():
            raise gl.vm.UserError("scope is required")
        if not rules.strip():
            raise gl.vm.UserError("rules are required")

        bounty_id = self.bounty_counter
        self.bounties[bounty_id] = Bounty(
            owner=str(gl.message.sender_address),
            title=title,
            scope=scope,
            rules=rules,
            reward_critical=reward_critical,
            reward_high=reward_high,
            reward_medium=reward_medium,
            reward_low=reward_low,
            status="open",
            created_at=gl.block.timestamp,
        )
        self.bounty_counter = bounty_id + u256(1)
        return bounty_id

    @gl.public.write
    def _set_bounty_status(self, bounty_id: u256, status: str) -> None:
        bounty = self.bounties[bounty_id]
        if str(gl.message.sender_address) != bounty.owner:
            raise gl.vm.UserError("only the bounty owner can do this")
        bounty.status = status
        self.bounties[bounty_id] = bounty

    @gl.public.write
    def pause_bounty(self, bounty_id: u256) -> None:
        self._set_bounty_status(bounty_id, "paused")

    @gl.public.write
    def reopen_bounty(self, bounty_id: u256) -> None:
        self._set_bounty_status(bounty_id, "open")

    @gl.public.write
    def close_bounty(self, bounty_id: u256) -> None:
        self._set_bounty_status(bounty_id, "closed")

    # ---------- reporting ----------

    @gl.public.write
    def submit_report(
        self,
        bounty_id: u256,
        title: str,
        description: str,
        poc_url: str,
        claimed_severity: str,
    ) -> u256:
        bounty = self.bounties[bounty_id]
        if bounty.status != "open":
            raise gl.vm.UserError("bounty is not open for submissions")
        if str(gl.message.sender_address) == bounty.owner:
            raise gl.vm.UserError("bounty owner cannot submit reports")
        if not title.strip() or not description.strip():
            raise gl.vm.UserError("title and description are required")
        if claimed_severity.strip().lower() not in SEVERITIES:
            raise gl.vm.UserError("claimed_severity must be one of critical/high/medium/low")

        report_id = self.report_counter
        self.reports[report_id] = Report(
            bounty_id=bounty_id,
            researcher=str(gl.message.sender_address),
            title=title,
            description=description,
            poc_url=poc_url,
            claimed_severity=claimed_severity.strip().lower(),
            status="submitted",
            ruled_severity="",
            triage_summary="",
            decided_reward=u256(0),
            submitted_at=gl.block.timestamp,
        )
        self.report_counter = report_id + u256(1)
        return report_id

    # ---------- AI triage (the consensus part) ----------

    @gl.public.write
    def triage_report(self, report_id: u256) -> str:
        report = self.reports[report_id]
        if report.status != "submitted":
            raise gl.vm.UserError("report has already been triaged")
        bounty = self.bounties[report.bounty_id]
        if bounty.status != "open":
            raise gl.vm.UserError("bounty is not open")

        # Storage is not visible inside the nondet block, so capture everything first.
        scope = bounty.scope
        rules = bounty.rules
        rep_title = report.title
        rep_body = report.description
        rep_poc = report.poc_url
        rep_claimed = report.claimed_severity

        def assess() -> str:
            poc_text = ""
            if rep_poc.strip():
                try:
                    poc_text = gl.nondet.web.render(rep_poc, mode="text")[:4000]
                except Exception:
                    poc_text = ""

            task = (
                "You are a senior smart contract security auditor triaging a bug bounty submission. "
                "Be skeptical: researchers sometimes submit guesses, out-of-scope targets, or "
                "theoretical issues with no real impact.\n\n"
                f"Program scope:\n{scope}\n\n"
                f"Program rules:\n{rules}\n\n"
                f"Report title: {rep_title}\n"
                f"Report body:\n{rep_body}\n"
                f"Researcher-claimed severity: {rep_claimed}\n"
            )
            if poc_text:
                task += f"\nProof-of-concept page content:\n{poc_text}\n"
            task += (
                "\nDecide two things:\n"
                "1. VALID: is this a real vulnerability inside the program scope and not excluded "
                "by the rules? Reject duplicates-by-guess, out-of-scope targets, issues with no "
                "demonstrable impact, and already-known/accepted risks.\n"
                "2. SEVERITY: if valid, the bucket: critical, high, medium, or low.\n"
                "Reply with ONLY this JSON object, no other text:\n"
                '{"valid": true, "severity": "high", "summary": "one sentence describing the issue"}\n'
                'or {"valid": false, "severity": "none", "summary": "one sentence on why it was rejected"}.'
            )

            raw = gl.nondet.exec_prompt(task).strip()
            data = json.loads(raw)
            valid = bool(data.get("valid", False))
            severity = str(data.get("severity", "none")).strip().lower()
            if severity not in SEVERITIES:
                severity = "none"
            if not valid:
                severity = "none"
            summary = str(data.get("summary", ""))[:280]
            # sort_keys keeps the output byte-identical across validators for equal verdicts
            return json.dumps({"valid": valid, "severity": severity, "summary": summary}, sort_keys=True)

        decided = json.loads(
            gl.eq_principle.prompt_comparative(
                assess,
                "Both assessments must reach the same verdict on validity (true or false) "
                "and the same severity bucket (critical, high, medium, low, or none). "
                "The one-sentence summaries may be worded differently but must describe "
                "the same underlying issue and the same reason for the verdict.",
            )
        )

        if decided["valid"]:
            table = {
                "critical": bounty.reward_critical,
                "high": bounty.reward_high,
                "medium": bounty.reward_medium,
                "low": bounty.reward_low,
            }
            report.decided_reward = table.get(decided["severity"], u256(0))
            report.status = "valid"
        else:
            report.decided_reward = u256(0)
            report.status = "invalid"
        report.ruled_severity = decided["severity"]
        report.triage_summary = decided["summary"]
        self.reports[report_id] = report
        return report.status

    @gl.public.write
    def mark_paid(self, report_id: u256) -> None:
        report = self.reports[report_id]
        bounty = self.bounties[report.bounty_id]
        if str(gl.message.sender_address) != bounty.owner:
            raise gl.vm.UserError("only the bounty owner can mark a report paid")
        if report.status != "valid":
            raise gl.vm.UserError("only valid (triaged) reports can be marked paid")
        report.status = "paid"
        self.reports[report_id] = report

    # ---------- views ----------

    @gl.public.view
    def get_bounty(self, bounty_id: u256) -> dict:
        b = self.bounties[bounty_id]
        return {
            "id": int(bounty_id),
            "owner": b.owner,
            "title": b.title,
            "scope": b.scope,
            "rules": b.rules,
            "rewards": {
                "critical": int(b.reward_critical),
                "high": int(b.reward_high),
                "medium": int(b.reward_medium),
                "low": int(b.reward_low),
            },
            "status": b.status,
            "created_at": int(b.created_at),
        }

    @gl.public.view
    def get_report(self, report_id: u256) -> dict:
        r = self.reports[report_id]
        return {
            "id": int(report_id),
            "bounty_id": int(r.bounty_id),
            "researcher": r.researcher,
            "title": r.title,
            "description": r.description,
            "poc_url": r.poc_url,
            "claimed_severity": r.claimed_severity,
            "status": r.status,
            "ruled_severity": r.ruled_severity,
            "triage_summary": r.triage_summary,
            "decided_reward": int(r.decided_reward),
            "submitted_at": int(r.submitted_at),
        }

    @gl.public.view
    def get_bounty_count(self) -> int:
        return int(self.bounty_counter)

    @gl.public.view
    def get_report_count(self) -> int:
        return int(self.report_counter)
