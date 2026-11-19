#!/usr/bin/env python3
"""
validate_playbook.py - mechanical checks for Cortex XSOAR 6 / 8 and XSIAM playbook YAML
(and automation/script YAML), as listed in reference/validation-checklist.md.

    python3 validate_playbook.py <file-or-dir> [...] [--platform xsoar6|xsoar8|xsiam] [--strict]

Exit code: 0 = no ERROR (and no WARN with --strict), 1 otherwise.
Check ids (PB-xx / SC-xx) match the checklist so a finding can be looked up.
Only depends on PyYAML.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
from collections import Counter, defaultdict, deque

import yaml

UUID_RE = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$")
TASK_TYPES = {"start", "regular", "condition", "playbook", "title", "collection", "section"}
KNOWN_OPERATORS = {
    # conditions / filters seen in shipped content
    "isEqualString", "isNotEqualString", "isEqualNumber", "isNotEqualNumber", "isNotEmpty",
    "isEmpty", "isExists", "isNotExists", "containsString", "notContainsString",
    "containsGeneral", "notContainsGeneral", "inList", "notInList", "in", "notIn",
    "greaterThan", "greaterThanOrEqual", "lessThan", "lessThanOrEqual", "isTrue", "isFalse",
    "startWith", "endWith", "notStartWith", "notEndWith", "match", "notMatch",
    "stringHasLength", "isAfter", "isBefore", "isSame", "isInCidrRanges", "IsNotInCidrRanges",
    "isIdenticalIncident", "hasLength", "IsInCidrRanges", "inRange", "isEqualDate",
    "general.isExists", "general.isEqual", "string.isEqual", "string.containsString",
    "number.greaterThan", "number.greaterThanOrEqual", "number.lessThan",
    "number.lessThanOrEqual", "number.isEqual",
    # transformers (built-in + common content transformers)
    "uniq", "append", "If-Then-Else", "replace", "SetIfEmpty", "AppendIfNotEmpty",
    "toLowerCase", "toUpperCase", "split", "join", "RegexExtractAll", "Stringify", "concat",
    "RemoveEmpty", "RegexReplace", "splitAndTrim", "StringifyArray", "FirstArrayElement",
    "LastArrayElement", "getField", "MakePair", "sort", "replaceMatch", "MapValuesTransformer",
    "StringContainsArray", "ConvertToSingleElementArray", "count", "WhereFieldEquals",
    "multiply", "round", "RemoveNullBytes", "trim", "substring", "substringFrom", "substringTo",
    "slice", "atIndex", "toString", "Base64Encode", "Base64Decode", "URLEncode", "URLDecode",
    "ParseJSON", "DT", "jmespath", "TimeStampToDate", "DateStringToISOFormat",
    "FormatDate", "ModifyDateTime", "addition", "subtraction", "division", "abs", "floor",
    "ceil", "precision", "toPercent", "length", "LowerCase", "UpperCase", "ExtractDomainFromUrlAndEmail",
    "ExtractDomainAndFQDNFromUrlAndEmail", "MapRegex", "RegexGroups", "StripChars",
    "ReplaceMatches", "AppendIfNotEmpty", "SetIfEmpty", "Cut", "CutTheEnd", "JSONtoMarkdown",
    "EncodeToAscii", "Sanitize", "GetFields", "DecodeMimeHeader", "JoinIfSingleElementOnly",
    "SortBy", "FilterByList", "Strptime", "ConvertDatetoUTC", "TimeComponents",
    "ExtractEmailV2", "IsInternalDomainName", "RemoveDuplicatesFromList",
}
SECRET_RE = re.compile(
    r"(?i)(api[_-]?key|apikey|secret|password|passwd|token|authorization)\s*[:=]\s*['\"]?[A-Za-z0-9_\-/+=]{16,}")
BUILTIN_CLOSE = {"Builtin|||closeInvestigation"}


class Report:
    def __init__(self, path):
        self.path = path
        self.items = []

    def add(self, sev, cid, msg):
        self.items.append((sev, cid, msg))

    def count(self, sev):
        return sum(1 for s, _, _ in self.items if s == sev)


def walk(o, fn, path=()):
    fn(o, path)
    if isinstance(o, dict):
        for k, v in o.items():
            walk(v, fn, path + (k,))
    elif isinstance(o, list):
        for i, v in enumerate(o):
            walk(v, fn, path + (i,))


def iter_strings(o):
    out = []
    walk(o, lambda x, p: out.append((p, x)) if isinstance(x, str) else None)
    return out


# --------------------------------------------------------------------------
# Playbook checks
# --------------------------------------------------------------------------

def check_playbook(d: dict, r: Report, platform: str | None):
    # 1. top level -------------------------------------------------------
    for k in ("id", "version", "name", "starttaskid", "tasks", "inputs", "outputs", "fromversion"):
        if k not in d:
            r.add("ERROR", "PB-01", f"missing top-level key '{k}'")
    if d.get("version") not in (-1, None):
        r.add("WARN", "PB-02", f"version is {d.get('version')}; custom content uploads with version: -1")
    tasks = d.get("tasks") or {}
    if not isinstance(tasks, dict) or not tasks:
        r.add("ERROR", "PB-03", "tasks is empty or not a mapping")
        return
    start = str(d.get("starttaskid", ""))
    if start not in tasks:
        r.add("ERROR", "PB-04", f"starttaskid '{start}' is not a task")
    elif tasks[start].get("type") != "start":
        r.add("ERROR", "PB-04", f"starttaskid '{start}' is type '{tasks[start].get('type')}', not start")
    starts = [k for k, t in tasks.items() if t.get("type") == "start"]
    if len(starts) > 1:
        r.add("ERROR", "PB-05", f"more than one start task: {starts}")
    mk = d.get("marketplaces")
    if platform == "xsiam" and mk and "marketplacev2" not in mk and "platform" not in mk:
        r.add("ERROR", "PB-06", f"marketplaces {mk} excludes XSIAM (needs marketplacev2)")
    if platform in ("xsoar6", "xsoar8") and mk and not ({"xsoar", "xsoar_saas", "xsoar_on_prem"} & set(mk)):
        r.add("ERROR", "PB-06", f"marketplaces {mk} excludes XSOAR")
    if d.get("system") is True:
        r.add("WARN", "PB-07", "system: true - an uploaded system playbook is locked and cannot be edited in the UI")

    # 2. task identity ---------------------------------------------------
    uuids = Counter()
    names = Counter()
    for key, t in tasks.items():
        key = str(key)
        if str(t.get("id")) != key:
            r.add("ERROR", "PB-10", f"task key '{key}' != task.id '{t.get('id')}'")
        inner = t.get("task") or {}
        if not inner:
            r.add("ERROR", "PB-11", f"task {key}: missing inner 'task' object")
            continue
        if t.get("taskid") != inner.get("id"):
            r.add("ERROR", "PB-12", f"task {key}: taskid != task.task.id")
        if not UUID_RE.match(str(t.get("taskid", ""))):
            r.add("ERROR", "PB-13", f"task {key}: taskid is not a uuid")
        uuids[t.get("taskid")] += 1
        if t.get("type") not in TASK_TYPES:
            r.add("ERROR", "PB-14", f"task {key}: unknown type '{t.get('type')}'")
        if t.get("type") not in ("start",):
            nm = inner.get("name", "")
            if not nm:
                r.add("WARN", "PB-15", f"task {key}: empty name")
            names[nm] += 1
        if t.get("quietmode", 0) not in (0, 1, 2):
            r.add("ERROR", "PB-16", f"task {key}: quietmode must be 0, 1 or 2")
        try:
            v = json.loads(t.get("view") or "{}")
            _ = v["position"]["x"], v["position"]["y"]
        except Exception:
            r.add("WARN", "PB-17", f"task {key}: view is not JSON with position.x/y (designer will stack it at 0,0)")
    for u, n in uuids.items():
        if n > 1:
            r.add("ERROR", "PB-13", f"taskid {u} used {n} times")
    for nm, n in names.items():
        if n > 1 and nm:
            r.add("WARN", "PB-18", f"task name '{nm}' used {n} times - War Room and context errors become ambiguous")
    pos = Counter()
    for key, t in tasks.items():
        try:
            p = json.loads(t.get("view") or "{}")["position"]
            pos[(p["x"], p["y"])] += 1
        except Exception:
            pass
    for p, n in pos.items():
        if n > 1:
            r.add("WARN", "PB-17", f"{n} tasks share designer position {p}")

    # 3. per-type shape --------------------------------------------------
    for key, t in tasks.items():
        key = str(key)
        inner = t.get("task") or {}
        typ = t.get("type")
        nt = t.get("nexttasks") or {}
        script = inner.get("script")
        sname = inner.get("scriptName")
        if typ == "regular":
            if inner.get("iscommand"):
                if not script:
                    r.add("ERROR", "PB-20", f"task {key} '{inner.get('name')}': iscommand true but no script")
                elif "|||" not in script:
                    r.add("INFO", "PB-20", f"task {key}: bare command '{script}' - the exported form is '|||{script}'")
                elif script.split("|||")[0] not in ("", "Builtin"):
                    r.add("INFO", "PB-21", f"task {key}: pinned to brand '{script.split('|||')[0]}' - runs only on that integration")
            elif script and "|||" in script:
                r.add("ERROR", "PB-20", f"task {key}: integration command with iscommand false")
            if sname in ("Set", "SetAndHandleEmpty"):
                sa = t.get("scriptarguments") or {}
                if "key" not in sa:
                    r.add("ERROR", "PB-22", f"task {key}: {sname} without 'key'")
                if "value" not in sa:
                    r.add("WARN", "PB-22", f"task {key}: {sname} without 'value'")
                if sname == "Set":
                    r.add("INFO", "PB-23", f"task {key}: Set writes '' when value is empty; SetAndHandleEmpty skips it")
        if typ == "condition":
            conds = t.get("conditions") or []
            labels = {c.get("label") for c in conds}
            if not conds and not sname:
                r.add("INFO", "PB-30", f"condition {key} '{inner.get('name')}': manual decision - an analyst picks the branch, so the playbook waits")
            if conds:
                for lbl in labels:
                    if lbl not in nt and str(lbl).lower() not in {str(x).lower() for x in nt}:
                        r.add("WARN", "PB-31", f"condition {key}: branch '{lbl}' has no route (flow stops there)")
                low = {str(x).lower() for x in labels}
                for lbl in nt:
                    if lbl in labels or lbl in ("#default#", "#error#"):
                        continue
                    if str(lbl).lower() in low:
                        r.add("WARN", "PB-32", f"condition {key}: route '{lbl}' differs only in case from its condition label - make them identical")
                    else:
                        r.add("ERROR", "PB-32", f"condition {key}: route '{lbl}' matches no condition label")
                for c in conds:
                    for g in c.get("condition") or []:
                        if not isinstance(g, list):
                            r.add("ERROR", "PB-33", f"condition {key} '{c.get('label')}': groups must be lists (AND of OR-lists)")
            if "#default#" not in nt and (conds or sname):
                r.add("WARN", "PB-34", f"condition {key} '{inner.get('name')}': no '#default#' (else) route")
        elif typ in ("regular", "playbook", "title", "start", "collection"):
            for lbl in nt:
                if lbl not in ("#none#", "#error#"):
                    r.add("ERROR", "PB-35", f"task {key} ({typ}): route label '{lbl}' only exists on conditions")
        if "#error#" in nt and t.get("continueonerrortype") != "errorPath":
            r.add("ERROR", "PB-36", f"task {key}: '#error#' route without continueonerrortype: errorPath")
        if t.get("continueonerrortype") == "errorPath" and "#error#" not in nt:
            r.add("WARN", "PB-36", f"task {key}: errorPath set but no '#error#' route")
        if t.get("continueonerror") and t.get("continueonerrortype") != "errorPath":
            r.add("INFO", "PB-37", f"task {key} '{inner.get('name')}': continue-on-error - confirm a later task checks the result")
        if typ == "playbook":
            if not (inner.get("playbookId") or inner.get("playbookName")):
                r.add("ERROR", "PB-40", f"playbook task {key}: no playbookId/playbookName")
            loop = t.get("loop") or {}
            if loop.get("forEach") and not loop.get("max"):
                r.add("WARN", "PB-41", f"playbook task {key}: forEach with max 0")
            if not t.get("separatecontext"):
                r.add("INFO", "PB-42", f"playbook task {key}: separatecontext false - child writes straight into parent context")
        if typ == "collection":
            if not (t.get("form") or t.get("message")):
                r.add("ERROR", "PB-45", f"collection task {key}: no form or message")
        sa = t.get("scriptarguments") or {}
        for an, av in sa.items():
            if isinstance(av, dict) and "simple" in av and "complex" in av:
                r.add("ERROR", "PB-46", f"task {key} arg '{an}': both simple and complex")

    # 4. routes and reachability ----------------------------------------
    edges = defaultdict(list)
    for key, t in tasks.items():
        for lbl, targets in (t.get("nexttasks") or {}).items():
            for dst in targets or []:
                if str(dst) not in tasks:
                    r.add("ERROR", "PB-50", f"task {key} -> '{dst}' ({lbl}): target does not exist")
                else:
                    edges[str(key)].append(str(dst))
    if start in tasks:
        seen = {start}
        q = deque([start])
        while q:
            n = q.popleft()
            for m in edges[n]:
                if m not in seen:
                    seen.add(m)
                    q.append(m)
        for k in tasks:
            if str(k) not in seen:
                r.add("WARN", "PB-51", f"task {k} '{tasks[k]['task'].get('name')}' is unreachable from start")
        # cycles
        color = {}
        cyc = []

        def dfs(n, stack):
            color[n] = 1
            for m in edges[n]:
                if color.get(m) == 1:
                    cyc.append(stack + [n, m])
                elif not color.get(m):
                    dfs(m, stack + [n])
            color[n] = 2
        sys.setrecursionlimit(10000)
        dfs(start, [])
        for c in cyc[:3]:
            r.add("WARN", "PB-52", f"route cycle {' -> '.join(c[-4:])}: prefer a loop (forEach / exit condition) on a sub-playbook")
    terminals = [k for k, t in tasks.items() if not (t.get("nexttasks") or {})]
    if not terminals:
        r.add("ERROR", "PB-53", "no terminal task - the playbook never finishes")

    # 5. inputs / context references ------------------------------------
    declared = {i.get("key") for i in d.get("inputs") or []}
    used = set()
    blob = yaml.safe_dump(tasks, width=100000)
    keys_longest_first = sorted((k for k in declared if k), key=len, reverse=True)
    for m in re.finditer(r"inputs\.", blob):
        rest = blob[m.end():]
        hit = next((k for k in keys_longest_first if rest.startswith(k)), None)
        if hit:
            used.add(hit)
        else:
            w = re.match(r"[A-Za-z0-9_\-]+", rest)
            if w:
                used.add(w.group(0))
    for u in sorted(used - declared):
        r.add("ERROR", "PB-60", f"inputs.{u} is referenced but not declared in inputs")
    for u in sorted(declared - used):
        r.add("WARN", "PB-61", f"input '{u}' is declared but never read")

    def opcheck(o, p):
        if isinstance(o, dict) and "operator" in o:
            if o["operator"] not in KNOWN_OPERATORS:
                r.add("WARN", "PB-62", f"unknown operator/transformer '{o['operator']}' at {'/'.join(map(str, p[:4]))} - confirm it exists on the tenant")
            for side in ("left", "right"):
                s = o.get(side)
                if isinstance(s, dict) and s.get("iscontext"):
                    val = (s.get("value") or {}).get("simple", "")
                    if isinstance(val, str) and "${" in val:
                        r.add("WARN", "PB-63", f"{side} operand '{val}' has iscontext: true AND ${{}} - write the bare path")
                if isinstance(s, dict) and not s.get("iscontext"):
                    val = (s.get("value") or {}).get("simple", "")
                    if side == "left" and isinstance(val, str) and re.match(r"^(incident|alert|inputs|[A-Z][A-Za-z]+)\.[A-Za-z]", val):
                        r.add("WARN", "PB-64", f"left operand '{val}' looks like a context path but iscontext is not set - compared as a literal")
    walk(tasks, opcheck)

    for p, s in iter_strings(tasks):
        if s.count("${") != s.count("}") and "${" in s and "${" in s and s.count("${") > s.count("}"):
            r.add("WARN", "PB-65", f"unbalanced ${{...}} in {'/'.join(map(str, p[:3]))}: {s[:60]!r}")
        if SECRET_RE.search(s):
            r.add("ERROR", "PB-66", f"possible hard-coded secret at {'/'.join(map(str, p[:3]))}")

    roots = re.findall(r"(?:root: |\$\{)(incident|alert)\.", blob)
    if platform == "xsiam" and "incident" in roots:
        r.add("WARN", "PB-67", "incident.* used on XSIAM - alert fields live under alert.* (verify on the tenant)")
    if platform in ("xsoar6", "xsoar8") and "alert" in roots:
        r.add("ERROR", "PB-67", "alert.* used on XSOAR - incident fields live under incident.*")

    # 6. info -----------------------------------------------------------
    closes = [k for k, t in tasks.items() if (t.get("task") or {}).get("script") in BUILTIN_CLOSE]
    if closes:
        r.add("INFO", "PB-70", f"closes the incident/alert in task(s) {closes} - confirm no other playbook/automation rule also closes it")
    custom = Counter((t.get("task") or {}).get("scriptName") for t in tasks.values()
                     if (t.get("task") or {}).get("scriptName"))
    r.add("INFO", "PB-71", f"{len(tasks)} tasks; scripts used: {dict(custom) or 'none'}")


# --------------------------------------------------------------------------
# Script (automation) checks
# --------------------------------------------------------------------------

def check_script(d: dict, r: Report, platform: str | None):
    for k in ("commonfields", "name", "script", "type"):
        if k not in d:
            r.add("ERROR", "SC-01", f"missing key '{k}'")
    cf = d.get("commonfields") or {}
    if cf.get("id") != d.get("name"):
        r.add("WARN", "SC-02", "commonfields.id != name - the UI and !commands use the name, uploads key on the id")
    if cf.get("version", -1) != -1:
        r.add("WARN", "SC-03", "commonfields.version should be -1 for custom upload")
    if d.get("type") == "python":
        if d.get("subtype") != "python3":
            r.add("ERROR", "SC-10", "subtype is not python3")
        if not d.get("dockerimage"):
            r.add("ERROR", "SC-11", "no dockerimage - runs on an old default image (f-strings fail). Pin the tenant's most common demisto/python3:<tag>")
        elif d["dockerimage"].endswith(":latest"):
            r.add("WARN", "SC-11", "dockerimage :latest - pin a tag")
    code = d.get("script") or ""
    if code.strip() in ("", "-"):
        r.add("INFO", "SC-12", "script body is '-' (unified from a .py file?) - upload the unified YAML")
    if "return_error" not in code and "except" not in code and code.strip() not in ("", "-"):
        r.add("WARN", "SC-13", "no error handling - an exception surfaces as a bare task error")
    if SECRET_RE.search(code):
        r.add("ERROR", "SC-14", "possible hard-coded secret in script body")
    if "demisto.results(" in code:
        r.add("INFO", "SC-15", "demisto.results() - prefer return_results(CommandResults(...)) so outputs are declared")
    outs = {o.get("contextPath") for o in d.get("outputs") or []}
    for m in re.finditer(r"outputs_prefix\s*=\s*['\"]([^'\"]+)", code):
        if not any((o or "").startswith(m.group(1)) for o in outs):
            r.add("WARN", "SC-16", f"outputs_prefix '{m.group(1)}' not declared in outputs - playbook designer will not offer it")
    names = [a.get("name") for a in d.get("args") or []]
    for m in set(re.findall(r"args\.get\(['\"]([A-Za-z0-9_\-]+)", code)):
        if m not in names:
            r.add("WARN", "SC-17", f"args.get('{m}') but '{m}' is not declared in args")


# --------------------------------------------------------------------------

def check_file(path, platform):
    r = Report(path)
    try:
        with open(path, encoding="utf-8") as f:
            d = yaml.safe_load(f)
    except Exception as e:
        r.add("ERROR", "PB-00", f"YAML does not parse: {e}")
        return r
    if not isinstance(d, dict):
        r.add("ERROR", "PB-00", "top level is not a mapping")
        return r
    if "tasks" in d and "starttaskid" in d:
        check_playbook(d, r, platform)
    elif "commonfields" in d and "script" in d:
        check_script(d, r, platform)
    else:
        r.add("ERROR", "PB-00", "neither a playbook (tasks/starttaskid) nor a script (commonfields/script)")
    return r


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("paths", nargs="+")
    ap.add_argument("--platform", choices=["xsoar6", "xsoar8", "xsiam"])
    ap.add_argument("--strict", action="store_true", help="fail on WARN as well")
    ap.add_argument("--quiet-info", action="store_true")
    a = ap.parse_args()
    files = []
    for p in a.paths:
        if os.path.isdir(p):
            for root, _, fs in os.walk(p):
                files += [os.path.join(root, f) for f in fs if f.endswith((".yml", ".yaml"))]
        else:
            files.append(p)
    bad = False
    for f in sorted(files):
        r = check_file(f, a.platform)
        e, w = r.count("ERROR"), r.count("WARN")
        print(f"\n== {f}: {e} error(s), {w} warning(s)")
        for sev, cid, msg in r.items:
            if sev == "INFO" and a.quiet_info:
                continue
            print(f"  {sev:5} {cid}  {msg}")
        if e or (a.strict and w):
            bad = True
    sys.exit(1 if bad else 0)


if __name__ == "__main__":
    main()
