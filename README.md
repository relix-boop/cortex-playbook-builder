# Cortex Playbook Builder - Claude Skill

A Claude skill that builds, modifies and reviews **Cortex XSOAR 6, XSOAR 8 and
XSIAM playbooks** as complete, uploadable YAML - alert triage, IOC enrichment,
XQL pivots, analyst approval forms, response actions and auto-close - plus the
automations they need.

It ships two tools the skill uses on every build:

| Tool | What it does |
|---|---|
| `tools/pb_builder.py` | Generates playbook YAML from code: task ids, uuids, routes (`#none#` / labels / `#default#` / `#error#`), designer layout, `marketplaces`. No hand-typed ids. |
| `tools/validate_playbook.py` | ~45 mechanical checks on playbooks and automation YAML (wiring, condition routes, context references, inputs, error paths, secrets, platform roots, docker image). Calibrated on the 108 shipped CommonPlaybooks: 0 errors. |

Rules are tagged by source: **[OOB]** checked against shipped content,
**[field]** learned on live MDR tenants, **[docs]** platform knowledge to verify.

> Not affiliated with or endorsed by Palo Alto Networks. Cortex, XSOAR and
> XSIAM are trademarks of Palo Alto Networks, Inc. Structure inspired by
> [git-Jimit/fortisoar-playbook-builder](https://github.com/git-Jimit/fortisoar-playbook-builder) (MIT).

## Install

**Claude Code plugin**
```
/plugin marketplace add relix-boop/cortex-playbook-builder
/plugin install cortex-playbook-builder@cortex-skills
```

**Manual**
```bash
cp -r skills/cortex-playbook-builder ~/.claude/skills/
```

**Claude.ai / desktop**: zip `skills/cortex-playbook-builder` and upload under
Customize → Skills → Upload skill.

## Usage

> Build an XSIAM playbook for "Suspicious sign-in" alerts: check the user's
> sign-in countries over 30 days with XQL, enrich the source IP, and ask the
> analyst before disabling the account.

Tools on their own:
```bash
pip install pyyaml
python3 skills/cortex-playbook-builder/examples/build_examples.py
python3 skills/cortex-playbook-builder/tools/validate_playbook.py skills/cortex-playbook-builder/examples --platform xsiam --strict
```

## Layout
```
.claude-plugin/          plugin + marketplace manifests
skills/cortex-playbook-builder/
  SKILL.md               the workflow and principles
  reference/             schema, task types, context/filters, platforms, pitfalls, checklists
  tools/                 pb_builder.py, validate_playbook.py
  examples/              two generated playbooks + the script that builds them
```

## License
MIT - see `LICENSE`.
