#!/usr/bin/env python3
"""
pb_builder.py - build Cortex XSOAR 6 / XSOAR 8 / XSIAM playbook YAML from code.

Why build from code: task ids, uuids, routes and designer positions are where
hand-written playbook YAML breaks. This module generates all of them, so the
author only describes tasks and edges.

Usage (minimal):

    from pb_builder import Playbook, ctx, simple, cond, tf

    pb = Playbook("CY - IP Triage", "Enrich alert IPs and set a verdict.",
                  platforms=["xsoar", "xsiam"])
    pb.input("IP", ctx("alert.hostip"), "IPs to check")
    start = pb.start()
    enrich = pb.command("Enrich IPs", "ip", {"ip": ctx("inputs.IP")}, skip_unavailable=True)
    has = pb.condition("Any malicious IP?", {
        "yes": [[cond("greaterThanOrEqual", ctx("DBotScore.Score"), simple("3"))]]})
    done = pb.title("Done")
    pb.chain(start, enrich, has)
    pb.link(has, done, "#default#")
    ...
    pb.save("CY_-_IP_Triage.yml")

Only depends on PyYAML. Run `python3 validate_playbook.py <file>` afterwards.
"""
from __future__ import annotations

import json
import re
import uuid
from collections import defaultdict, deque

import yaml

# --------------------------------------------------------------------------
# Value helpers - every task argument is {simple: ...} or {complex: {...}}
# --------------------------------------------------------------------------


def simple(value) -> dict:
    """A literal (may contain ${context.path} placeholders)."""
    return {"simple": "" if value is None else str(value)}


def ctx(root: str, accessor: str | None = None, filters: list | None = None,
        transformers: list | None = None) -> dict:
    """A context reference: root + optional accessor, filters, transformers."""
    c = {"root": root}
    if filters:
        c["filters"] = filters
    if accessor:
        c["accessor"] = accessor
    if transformers:
        c["transformers"] = transformers
    return {"complex": c}


def operand(v, is_context: bool | None = None) -> dict:
    """Left/right side of a condition or filter.

    A string starting with '$ctx:' is a context path; a dict from ctx()/simple()
    is taken as-is; anything else is a literal.
    """
    if isinstance(v, dict) and "complex" in v:
        return {"value": {"complex": v["complex"]}, "iscontext": True}
    if isinstance(v, dict) and "simple" in v:
        out = {"value": {"simple": v["simple"]}}
        if is_context:
            out["iscontext"] = True
        return out
    s = str(v)
    if s.startswith("$ctx:"):
        return {"value": {"simple": s[5:]}, "iscontext": True}
    out = {"value": {"simple": s}}
    if is_context:
        out["iscontext"] = True
    return out


def cond(operator: str, left, right=None, ignorecase: bool = False) -> dict:
    """One condition clause. Context paths: pass ctx('a.b') or '$ctx:a.b'."""
    c = {"operator": operator, "left": operand(left)}
    if right is not None:
        c["right"] = operand(right)
    if ignorecase:
        c["ignorecase"] = True
    return c


def tf(operator: str, **args) -> dict:
    """A transformer, e.g. tf('uniq'), tf('join', separator=',')."""
    t = {"operator": operator}
    if args:
        t["args"] = {}
        for k, v in args.items():
            if isinstance(v, dict) and ("simple" in v or "complex" in v):
                t["args"][k] = {"value": v} if "simple" in v else {"value": v, "iscontext": True}
            elif isinstance(v, str) and v.startswith("$ctx:"):
                t["args"][k] = {"value": {"simple": v[5:]}, "iscontext": True}
            else:
                t["args"][k] = {"value": {"simple": str(v)}}
    return t


# --------------------------------------------------------------------------
# YAML dumping that matches the shape of exported content
# --------------------------------------------------------------------------


class _Dumper(yaml.SafeDumper):
    pass


def _str_repr(dumper, data):
    if "\n" in data:
        return dumper.represent_scalar("tag:yaml.org,2002:str", data, style="|")
    return dumper.represent_scalar("tag:yaml.org,2002:str", data)


_Dumper.add_representer(str, _str_repr)


# --------------------------------------------------------------------------
# Playbook
# --------------------------------------------------------------------------

MARKETPLACES = {
    "xsoar": ["xsoar"],              # XSOAR 6 and XSOAR 8 (on-prem / SaaS)
    "xsoar_saas": ["xsoar_saas"],
    "xsiam": ["marketplacev2"],      # XSIAM (and XDR+playbooks)
    "platform": ["platform"],        # Cortex unified platform tenants
}


class Playbook:
    X0, DX, Y0, DY = 450, 420, 50, 190

    def __init__(self, name: str, description: str, playbook_id: str | None = None,
                 platforms: list[str] | None = None, fromversion: str = "6.10.0",
                 quiet: bool | None = None):
        self.name = name
        self.id = playbook_id or name           # custom content: id == name is conventional
        self.description = description
        self.fromversion = fromversion
        self.platforms = platforms or ["xsoar"]
        self.quiet = quiet
        self.tasks: dict[str, dict] = {}
        self.inputs: list[dict] = []
        self.outputs: list[dict] = []
        self._next = 0
        self._labels: dict[tuple, str] = {}

    # ---- inputs / outputs --------------------------------------------------
    def input(self, key: str, value: dict | None = None, description: str = "",
              required: bool = False):
        self.inputs.append({"key": key, "value": value or {}, "required": required,
                            "description": description, "playbookInputQuery": None})
        return f"inputs.{key}"

    def output(self, context_path: str, description: str = "", type_: str = "unknown"):
        self.outputs.append({"contextPath": context_path, "description": description,
                             "type": type_})

    # ---- task factory ------------------------------------------------------
    def _task(self, type_: str, name: str, description: str = "", **inner) -> str:
        tid = str(self._next)
        self._next += 1
        u = str(uuid.uuid4())
        task = {"id": u, "version": -1, "name": name, "description": description}
        task.update({k: v for k, v in inner.items() if v is not None})
        task.setdefault("type", type_)
        task.setdefault("iscommand", False)
        task.setdefault("brand", "")
        self.tasks[tid] = {
            "id": tid, "taskid": u, "type": type_, "task": task,
            "separatecontext": False, "continueonerrortype": "",
            "view": None, "note": False, "timertriggers": [], "ignoreworker": False,
            "skipunavailable": False, "quietmode": 0,
            "isoversize": False, "isautoswitchedtoquietmode": False,
        }
        return tid

    def _args(self, tid: str, args: dict | None):
        if args:
            self.tasks[tid]["scriptarguments"] = {
                k: (v if isinstance(v, dict) else simple(v)) for k, v in args.items()}

    def start(self) -> str:
        if self.tasks:
            raise ValueError("start() must be the first task (id '0')")
        tid = self._task("start", "")
        self.tasks[tid]["task"].pop("type")
        self.tasks[tid]["task"]["description"] = ""
        return tid

    def title(self, name: str, description: str = "") -> str:
        return self._task("title", name, description)

    def manual(self, name: str, description: str) -> str:
        """A manual task an analyst must complete (no script)."""
        return self._task("regular", name, description)

    def command(self, name: str, command: str, args: dict | None = None,
                brand: str = "", description: str = "", skip_unavailable: bool = False,
                continue_on_error: bool = False, quiet: int = 0,
                extend_context: str | None = None, ignore_outputs: bool = False) -> str:
        """Integration command. brand='' runs on every enabled instance that has it."""
        script = command if "|||" in command else f"{brand}|||{command}"
        tid = self._task("regular", name, description, script=script, iscommand=True,
                         brand=brand or "")
        self._args(tid, args)
        t = self.tasks[tid]
        if extend_context:
            t.setdefault("scriptarguments", {})["extend-context"] = simple(extend_context)
        if ignore_outputs:
            t.setdefault("scriptarguments", {})["ignore-outputs"] = simple("true")
        t["skipunavailable"] = skip_unavailable
        if continue_on_error:
            t["continueonerror"] = True
        t["quietmode"] = quiet
        return tid

    def builtin(self, name: str, command: str, args: dict | None = None,
                description: str = "", continue_on_error: bool = False) -> str:
        """Server builtins: closeInvestigation, setIncident, setAlert, extractIndicators..."""
        tid = self._task("regular", name, description, script=f"Builtin|||{command}",
                         iscommand=True, brand="Builtin")
        self._args(tid, args)
        if continue_on_error:
            self.tasks[tid]["continueonerror"] = True
        return tid

    def script(self, name: str, script_name: str, args: dict | None = None,
               description: str = "", continue_on_error: bool = False, quiet: int = 0) -> str:
        """Automation (script) task: Set, SetAndHandleEmpty, Print, DeleteContext, custom..."""
        tid = self._task("regular", name, description, scriptName=script_name)
        self._args(tid, args)
        if continue_on_error:
            self.tasks[tid]["continueonerror"] = True
        self.tasks[tid]["quietmode"] = quiet
        return tid

    def set(self, name: str, key: str, value, append: bool = False, handle_empty: bool = True) -> str:
        """Set a context key. SetAndHandleEmpty skips empty values instead of writing ''."""
        args = {"key": simple(key), "value": value if isinstance(value, dict) else simple(value)}
        if append:
            args["append"] = simple("true")
        return self.script(name, "SetAndHandleEmpty" if handle_empty else "Set", args)

    def condition(self, name: str, branches: dict[str, list], description: str = "") -> str:
        """Built-in condition. branches = {label: [[clause OR clause], [AND group]...]}.

        Outer list = AND between groups, inner list = OR inside a group.
        Route '#default#' (else) with link(..., '#default#').
        """
        tid = self._task("condition", name, description)
        self.tasks[tid]["conditions"] = [{"label": lbl, "condition": groups}
                                         for lbl, groups in branches.items()]
        return tid

    def script_condition(self, name: str, script_name: str, args: dict | None = None,
                         description: str = "") -> str:
        """Condition decided by a script's return value (e.g. IsIntegrationAvailable)."""
        tid = self._task("condition", name, description, scriptName=script_name)
        self._args(tid, args)
        return tid

    def subplaybook(self, name: str, playbook_id: str, args: dict | None = None,
                    separate_context: bool = True, for_each: bool = False,
                    loop_max: int = 100, loop_wait: int = 1, exit_condition: list | None = None,
                    description: str = "", skip_unavailable: bool = True) -> str:
        tid = self._task("playbook", name, description, playbookName=playbook_id,
                         playbookId=playbook_id)
        self._args(tid, args)
        t = self.tasks[tid]
        t["separatecontext"] = separate_context
        t["loop"] = {"iscommand": False, "exitCondition": "", "wait": loop_wait,
                     "max": loop_max if (for_each or exit_condition) else 0}
        if for_each:
            t["loop"]["forEach"] = True
        if exit_condition:
            t["loop"]["exitCondition"] = exit_condition
        t["skipunavailable"] = skip_unavailable
        return tid

    def ask(self, name: str, title: str, questions: list[dict], to: str = "Analyst",
            methods: list[str] | None = None, subject: str = "", body: str = "",
            description: str = "") -> str:
        """Data-collection task (form). questions: [{'label','type','options'}].

        type: shortText | longText | singleSelect | multiSelect | number | date | boolean
        Answers land in context under <TaskName>.Answers.<n>.
        """
        tid = self._task("collection", name, description)
        t = self.tasks[tid]
        t["message"] = {
            "to": {"simple": to}, "subject": simple(subject or title), "body": simple(body),
            "methods": methods or [], "format": "", "bcc": None, "cc": None,
            "timings": {"retriescount": 2, "retriesinterval": 360, "completeafterreplies": 1,
                        "completeafterv2": True, "completeaftersla": False}}
        qs = []
        for i, q in enumerate(questions):
            qs.append({"id": str(i), "label": "", "labelarg": simple(q["label"]),
                       "required": q.get("required", True), "gridcolumns": [], "defaultrows": [],
                       "type": q.get("type", "singleSelect"), "options": [],
                       "optionsarg": [simple(o) for o in q.get("options", [])],
                       "fieldassociated": "", "placeholder": "", "tooltip": "", "readonly": False})
        t["form"] = {"questions": qs, "title": title, "description": "", "sender": "",
                     "expired": False, "totalanswers": 0}
        return tid

    # ---- wiring ------------------------------------------------------------
    def link(self, src: str, dst: str, label: str = "#none#"):
        nt = self.tasks[src].setdefault("nexttasks", {})
        nt.setdefault(label, [])
        if dst not in nt[label]:
            nt[label].append(dst)

    def chain(self, *tids: str):
        for a, b in zip(tids, tids[1:]):
            self.link(a, b)

    def on_error(self, src: str, dst: str):
        """Route task errors to dst instead of stopping (continueonerrortype=errorPath)."""
        self.tasks[src]["continueonerror"] = True
        self.tasks[src]["continueonerrortype"] = "errorPath"
        self.link(src, dst, "#error#")

    # ---- layout ------------------------------------------------------------
    def _layout(self):
        """Longest-path depth for y; spread siblings on x. Deterministic."""
        edges = defaultdict(list)
        indeg = defaultdict(int)
        for tid, t in self.tasks.items():
            for targets in t.get("nexttasks", {}).values():
                for d in targets:
                    edges[tid].append(d)
                    indeg[d] += 1
        depth = {tid: 0 for tid in self.tasks}
        q = deque([t for t in self.tasks if indeg[t] == 0])
        seen = 0
        indeg2 = dict(indeg)
        while q:
            n = q.popleft()
            seen += 1
            for d in edges[n]:
                depth[d] = max(depth[d], depth[n] + 1)
                indeg2[d] -= 1
                if indeg2[d] == 0:
                    q.append(d)
        if seen != len(self.tasks):
            raise ValueError("cycle in playbook routes - use a loop (for_each / exit condition) instead")
        rows = defaultdict(list)
        for tid in sorted(self.tasks, key=int):
            rows[depth[tid]].append(tid)
        maxw = max(len(v) for v in rows.values())
        for d, tids in rows.items():
            off = self.X0 - (len(tids) - 1) * self.DX / 2
            for i, tid in enumerate(tids):
                x = off + i * self.DX
                self.tasks[tid]["view"] = json.dumps(
                    {"position": {"x": x, "y": self.Y0 + d * self.DY}}, indent=2)
        width = max(380, maxw * self.DX)
        height = (max(rows) + 1) * self.DY + 100
        return {"linkLabelsPosition": {},
                "paper": {"dimensions": {"height": height, "width": width,
                                         "x": self.X0 - width / 2, "y": self.Y0}}}

    # ---- output ------------------------------------------------------------
    def to_dict(self) -> dict:
        if "0" not in self.tasks or self.tasks["0"]["type"] != "start":
            raise ValueError("call start() first")
        paper = self._layout()
        mkts = []
        for p in self.platforms:
            for m in MARKETPLACES.get(p, [p]):
                if m not in mkts:
                    mkts.append(m)
        d = {
            "id": self.id, "version": -1, "name": self.name, "description": self.description,
            "starttaskid": "0",
            "tasks": {k: self.tasks[k] for k in sorted(self.tasks, key=int)},
            "view": json.dumps(paper, indent=2),
            "inputs": self.inputs, "outputs": self.outputs,
            "tests": ["No tests"], "fromversion": self.fromversion,
            "marketplaces": mkts,
        }
        if self.quiet is not None:
            d["quiet"] = self.quiet
        return d

    def to_yaml(self) -> str:
        return yaml.dump(self.to_dict(), Dumper=_Dumper, sort_keys=False,
                         allow_unicode=True, width=1000)

    def save(self, path: str):
        with open(path, "w", encoding="utf-8") as f:
            f.write(self.to_yaml())
        return path


def filename_for(name: str) -> str:
    """demisto-sdk naming: playbook-<Name_with_underscores>.yml"""
    return "playbook-" + re.sub(r"[^A-Za-z0-9_\-.]", "", name.replace(" ", "_")) + ".yml"
