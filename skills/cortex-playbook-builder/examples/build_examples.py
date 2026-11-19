#!/usr/bin/env python3
"""Builds the example playbooks in this folder with tools/pb_builder.py.

    python3 build_examples.py && python3 ../tools/validate_playbook.py . --strict

Re-running regenerates uuids; that is expected (uuids are per build).
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "tools"))
from pb_builder import Playbook, ctx, simple, cond, tf, filename_for  # noqa: E402

PRIVATE = "10.0.0.0/8,172.16.0.0/12,192.168.0.0/16,127.0.0.0/8,169.254.0.0/16,100.64.0.0/10"


# ---------------------------------------------------------------------------
# 1. Cross-platform (XSOAR 6/8 + XSIAM): IP reputation triage, per-IP verdicts
# ---------------------------------------------------------------------------
def ip_triage():
    pb = Playbook(
        "CY - IP Reputation Triage",
        "Drops private/empty IPs, enriches the rest with every enabled reputation "
        "integration, gives each IP a verdict with its reasons, and optionally closes "
        "the incident/alert when nothing is suspicious. Verdict-only by default.",
        platforms=["xsoar", "xsiam"])
    pb.input("IP", None, "IPs to triage. Map from the parent: incident.* on XSOAR, alert.hostip / alert.remoteip on XSIAM.", required=True)
    pb.input("InternalRanges", simple(PRIVATE), "CIDRs never sent to reputation sources.")
    pb.input("AutoClose", simple("false"), "true = close when every public IP is benign/unknown.")
    pb.input("CloseReason", simple("Resolved"),
             "XSOAR: Resolved / False Positive. XSIAM: 'Resolved - False Positive' etc.")
    pb.output("Triage.Verdict", "MALICIOUS | SUSPICIOUS | CLEAN | NO_PUBLIC_IP")
    pb.output("Triage.IPs", "Public IPs that were checked")

    s = pb.start()
    t_collect = pb.title("Collect")
    set_ips = pb.set("Keep public IPs only", "Triage.IPs", ctx(
        "inputs.IP",
        filters=[[cond("IsNotInCidrRanges", ctx("inputs.IP"), ctx("inputs.InternalRanges"))],
                 [cond("isNotEmpty", ctx("inputs.IP"))]],
        transformers=[tf("uniq")]))
    any_ip = pb.condition("Any public IP to check", {
        "yes": [[cond("isNotEmpty", ctx("Triage.IPs"))]]})
    no_ip = pb.set("Verdict NO_PUBLIC_IP", "Triage.Verdict", "NO_PUBLIC_IP")

    t_enrich = pb.title("Enrich")
    enrich = pb.command("Get IP reputation", "ip", {"ip": ctx("Triage.IPs")},
                        description="Runs on every enabled integration that implements !ip.",
                        skip_unavailable=True, continue_on_error=True)

    t_verdict = pb.title("Verdict")
    dbot_for_ips = [[cond("inList", ctx("DBotScore.Indicator"), ctx("Triage.IPs"))]]
    verdict = pb.condition("Highest score among the IPs", {
        "malicious": [[cond("greaterThanOrEqual",
                            ctx("DBotScore", accessor="Score", filters=dbot_for_ips), simple("3"))]],
        "suspicious": [[cond("isEqualNumber",
                             ctx("DBotScore", accessor="Score", filters=dbot_for_ips), simple("2"))]],
    }, description="Any IP scoring 3 wins; otherwise any 2. Sources that disagree show in the summary.")
    v_mal = pb.set("Verdict MALICIOUS", "Triage.Verdict", "MALICIOUS")
    v_sus = pb.set("Verdict SUSPICIOUS", "Triage.Verdict", "SUSPICIOUS")
    v_cln = pb.set("Verdict CLEAN", "Triage.Verdict", "CLEAN")

    summary = pb.script("Write verdict summary", "Print", {"value": simple(
        "### IP triage: ${Triage.Verdict}\n"
        "Checked: ${Triage.IPs}\n\n"
        "Per-source scores (indicator / vendor / score):\n"
        "${DBotScore}")}, description="Readable War Room entry; the analyst should not need raw context.")

    t_close = pb.title("Close or hand over")
    can_close = pb.condition("Auto-close allowed", {
        "yes": [[cond("isEqualString", ctx("inputs.AutoClose"), simple("true"), ignorecase=True)],
                [cond("isNotEqualString", ctx("Triage.Verdict"), simple("MALICIOUS"))],
                [cond("isNotEqualString", ctx("Triage.Verdict"), simple("SUSPICIOUS"))]],
    }, description="AND: AutoClose=true and verdict is CLEAN or NO_PUBLIC_IP.")
    close = pb.builtin("Close as benign", "closeInvestigation", {
        "closeReason": ctx("inputs.CloseReason"),
        "closeNotes": simple("Auto-closed by CY - IP Reputation Triage: ${Triage.Verdict} (${Triage.IPs})")})
    done = pb.title("Done")

    pb.chain(s, t_collect, set_ips, any_ip)
    pb.link(any_ip, t_enrich, "yes")
    pb.link(any_ip, no_ip, "#default#")
    pb.chain(t_enrich, enrich, t_verdict, verdict)
    pb.link(verdict, v_mal, "malicious")
    pb.link(verdict, v_sus, "suspicious")
    pb.link(verdict, v_cln, "#default#")
    for v in (v_mal, v_sus, v_cln, no_ip):
        pb.link(v, summary)
    pb.chain(summary, t_close, can_close)
    pb.link(can_close, close, "yes")
    pb.link(can_close, done, "#default#")
    pb.link(close, done)
    return pb


# ---------------------------------------------------------------------------
# 2. XSIAM: user sign-in review - XQL pivot, analyst approval, sub-playbook loop
# ---------------------------------------------------------------------------
def signin_review():
    pb = Playbook(
        "CY - XSIAM Sign-in Review",
        "For the alert user, counts sign-in countries over 30 days with XQL, flags a new "
        "country, asks an analyst before any account action, and runs IP triage per IP.",
        platforms=["xsiam"])
    pb.input("Username", ctx("alert.username", transformers=[tf("FirstArrayElement")]),
             "Alert user. alert.username is a list on XSIAM - first element.")
    pb.input("Days", simple("30"), "History window in days.")
    pb.output("SignIn.NewCountry", "true when the alert country was not seen in the window")

    s = pb.start()
    has_user = pb.condition("Alert has a user", {"yes": [[cond("isNotEmpty", ctx("inputs.Username"))]]})
    no_user = pb.set("Note no user", "SignIn.Status", "NO_USER")

    xql = pb.command(
        "XQL sign-in countries for user", "xdr-xql-generic-query", {
            "query_name": simple("cy_signin_countries_${alert.id}"),
            "time_frame": simple("${inputs.Days} days"),
            "query": simple(
                'dataset = authentication_story '
                '| alter u = lowercase(json_extract_scalar(auth_normalized_user, "$.username")) '
                '| filter u != null and lowercase("${inputs.Username}") contains u '
                '| comp count() as logins by action_country '
                '| sort desc logins | limit 50')},
        description="Polling command: waits for the XQL result. One query per alert (quota).",
        skip_unavailable=False)
    pb.on_error(xql, no_user)  # XQL quota / parse errors -> note and stop, do not fail the alert

    new_country = pb.condition("Alert country seen before", {
        "seen": [[cond("inList", ctx("alert.country"),
                       ctx("PaloAltoNetworksXQL.GenericQuery.results.action_country"))]]})
    mark_new = pb.set("Mark new country", "SignIn.NewCountry", "true")
    mark_seen = pb.set("Mark known country", "SignIn.NewCountry", "false")

    triage = pb.subplaybook("IP triage per IP", "CY - IP Reputation Triage", {
        "IP": ctx("alert.remoteip"), "AutoClose": simple("false")},
        for_each=True, loop_max=20)

    ask = pb.ask("Analyst decision", "New sign-in country for ${inputs.Username}",
                 [{"label": "Action", "type": "singleSelect",
                   "options": ["Disable account", "Reset sessions", "No action"]}],
                 to="Investigator")
    decide = pb.condition("Which action", {
        "disable": [[cond("isEqualString", ctx("Analyst decision.Answers.0"), simple("Disable account"))]],
        "sessions": [[cond("isEqualString", ctx("Analyst decision.Answers.0"), simple("Reset sessions"))]]})
    disable = pb.manual("Disable the account", "Response action left manual on purpose: wire the "
                        "client's IdP command here (e.g. |||msgraph-user-account-disable) once confirmed.")
    sessions = pb.manual("Revoke sessions", "Wire |||msgraph-user-session-revoke (or the client's IdP) here.")
    done = pb.title("Done")

    pb.chain(s, has_user)
    pb.link(has_user, xql, "yes")
    pb.link(has_user, no_user, "#default#")
    pb.link(no_user, done)
    pb.link(xql, new_country)
    pb.link(new_country, mark_seen, "seen")
    pb.link(new_country, mark_new, "#default#")
    pb.link(mark_seen, done)
    pb.chain(mark_new, triage, ask, decide)
    pb.link(decide, disable, "disable")
    pb.link(decide, sessions, "sessions")
    pb.link(decide, done, "#default#")
    pb.link(disable, done)
    pb.link(sessions, done)
    return pb


if __name__ == "__main__":
    for build in (ip_triage, signin_review):
        pb = build()
        path = os.path.join(HERE, filename_for(pb.name))
        pb.save(path)
        print("wrote", path)
