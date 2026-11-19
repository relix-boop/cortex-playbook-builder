# Planning - seven questions before any YAML

1. **Platform** - XSOAR 6 / 8 / XSIAM / several (`platforms.md`). Decides
   roots, builtins, close reasons, `marketplaces`.
2. **Start** - incident type, playbook trigger, automation rule, sub-playbook of
   which parent, job. A job has no incident/alert fields.
3. **Data shape** - print the real sample; list the exact paths you will read
   and whether each is a list. No sample → write the assumed shape down.
4. **Shape of the work**
   - *Triage*: entity in → verdict out (+ optional close). Example 1.
   - *Investigation*: pivot (XQL / SIEM / EDR), enrich entities, decide, report.
     Example 2. Use for "investigate", "triage and tell me what to do".
   - *Sweep / job*: N checks across the estate, report what fired.
   - *Library sub-playbook*: inputs in, outputs out, no field writes.
5. **Result contract** - the context keys and War Room/field output every path
   ends with, including "nothing to do" (`NO_PUBLIC_IP`, `NO_USER`).
6. **Switches** - every threshold, list, recipient and on/off (AutoClose,
   AutoRespond) as an input with a safe default (off).
7. **Collisions** - who else writes these alerts; quotas (XQL CU/day, API rate
   limits); is the alert volume known (count through the incidents/issues API,
   not just `dataset = alerts`). [field]

Then write the task list on paper:

```
0 start
1 title Collect
2 SetAndHandleEmpty Triage.IPs <- inputs.IP | not private | uniq
3 condition Any public IP?   yes->4  #default#->X
4 title Enrich
5 |||ip  (skipunavailable, continue on error)
...
N title Done
```
Every label routed, every branch to Done, one convergence per phase.
