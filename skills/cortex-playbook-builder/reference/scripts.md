# Automations (scripts) for playbooks

Write one only when native tasks cannot do the job (SKILL.md principle 4).

## Unified YAML (what you upload)

```yaml
commonfields:
  id: CYScoreIndicators
  version: -1
name: CYScoreIndicators
script: |-
  import demistomock as demisto  # noqa - provided at runtime
  from CommonServerPython import *  # noqa

  def main():
      try:
          args = demisto.args()
          values = argToList(args.get("values"))
          rows = [{"Value": v, "Verdict": "UNKNOWN"} for v in values]
          return_results(CommandResults(
              outputs_prefix="CYScore", outputs_key_field="Value", outputs=rows,
              readable_output=tableToMarkdown("Verdicts", rows)))
      except Exception as e:
          return_error(f"CYScoreIndicators failed: {e}")

  if __name__ in ("__main__", "__builtin__", "builtins"):
      main()
type: python
subtype: python3
dockerimage: demisto/python3:3.12.x.y     # pin: the tenant's most common tag
tags: []
comment: One line - shown in the designer.
enabled: true
args:
- name: values
  description: Comma-separated values.
  isArray: true
  required: true
outputs:
- contextPath: CYScore.Value
  type: string
- contextPath: CYScore.Verdict
  type: string
scripttarget: 0
runas: DBotWeakRole
fromversion: 6.10.0
marketplaces: [xsoar, marketplacev2]
tests:
- No tests
```

In a unified YAML the `import demistomock` / `from CommonServerPython import *`
lines are harmless; the runtime injects CommonServerPython.

## Rules

- `dockerimage` pinned. Find the tenant's common tag: `automation/search` and
  count `dockerImage`. No image → old default Python → f-string SyntaxError. [field]
- Declare every arg and every output. Undeclared outputs are invisible in the
  designer and across separate contexts.
- `return_results(CommandResults(...))`, not `demisto.results`.
- `return_error` in `except` - a raw exception gives an unhelpful task error.
- Call commands with `demisto.executeCommand("cmd", {...})`; check
  `isError(res[0])`.
- Polling / long work: `ScheduledCommand` or let the playbook loop; never
  `time.sleep` for minutes.
- XQL from a script: start (`xdr-xql-generic-query`, needs `query_name`),
  poll `xdr-xql-get-query-results`, retry the start on "maximum allowed number
  of parallel running queries" (e.g. 10 × 30 s) and set the script timeout to
  match. [field]
- Free text (email bodies, command lines) can be large: pass a context key and
  read it inside the script rather than inlining it in an argument.
- Custom script names: a client/org prefix (`CY...`) so they never collide with
  OOB names.
- Upload keeps CUSTOM via `/xsoar/automation/import` (multipart `file`) or the
  UI; re-importing the same id updates it. Verify with `automation/load/<id>`. [field]

## Testing locally

Stub `demisto` with a small object whose `args()` returns your test args and
whose `executeCommand` returns recorded outputs from the real sample; run
`main()`; check the outputs. Do this before every tenant run.
