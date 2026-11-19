# Context, filters and transformers

## Two ways to reference context - never mix them

| Where | Write | Example |
|---|---|---|
| Inside a literal string (`simple`) | `${path}` | `simple: "Closed: ${Triage.Verdict}"` |
| As a value (`complex`) | bare root/accessor | `complex: {root: Triage, accessor: Verdict}` |
| Condition operand | bare path + `iscontext: true` | `left: {value: {simple: Triage.Verdict}, iscontext: true}` |

`iscontext: true` **and** `${...}` together = double resolution; shipped
content has four of these and they only work by accident (PB-63).
A context path in an operand **without** `iscontext: true` is compared as the
literal string "Triage.Verdict" (PB-64) - the condition is silently always false.

## Roots

- `incident.<field>` (XSOAR), `alert.<field>` (XSIAM). Custom fields: lowercase
  machine name, no spaces (`incident.sourceip`, `alert.username`).
- `inputs.<Key>` - playbook inputs.
- Integration outputs: as documented per command (`IP.Address`, `DBotScore`,
  `File.SHA256`, `Endpoint.Hostname`, `PaloAltoNetworksXQL.GenericQuery.results`).
- Data collection answers: `<Task Name>.Answers.<n>`.
- XSIAM list fields: `alert.username`, `alert.hostip`, `alert.localip` are lists
  [field]; take `FirstArrayElement` or loop.
- XSIAM `occurred` is `0001-01-01`; alert time is in `alert.timestamp` /
  `CustomFields.timestamp`. [field]

## complex values

```yaml
complex:
  root: DBotScore                 # the list/object to start from
  filters:                        # outer list = AND, inner list = OR
  - - operator: inList
      left:  {value: {simple: DBotScore.Indicator}, iscontext: true}
      right: {value: {simple: Triage.IPs}, iscontext: true}
  accessor: Score                 # field taken from each remaining item
  transformers:                   # applied in order to the result
  - operator: uniq
  - operator: join
    args: {separator: {value: {simple: ","}}}
```
Filter operands refer to fields of the root **with the root prefix**
(`DBotScore.Indicator`, not `Indicator`). [OOB]

## Operators used in shipped content (top of 108 playbooks) [OOB]
Conditions/filters: `isEqualString` (360), `isNotEmpty` (241), `isExists`,
`containsString`, `isNotEqualString`, `containsGeneral`, `isNotExists`,
`inList`, `notContainsGeneral`, `stringHasLength`, `in`, `notIn`,
`notContainsString`, `greaterThanOrEqual`, `isTrue`, `isEmpty`, `isEqualNumber`,
`match`, `isAfter`, `IsNotInCidrRanges`, `lessThan`. Namespaced forms
(`general.isExists`, `number.greaterThan`, `string.isEqual`) also appear.

Transformers: `uniq` (277), `append`, `If-Then-Else`, `replace`, `SetIfEmpty`,
`AppendIfNotEmpty`, `toLowerCase`, `split`, `join`, `RegexExtractAll`,
`Stringify`, `concat`, `RemoveEmpty`, `RegexReplace`, `splitAndTrim`,
`FirstArrayElement`, `LastArrayElement`, `getField`, `sort`, `count`,
`WhereFieldEquals`, `MapValuesTransformer`.

Anything else: confirm it exists on the tenant (script with tag
`transformer` / `filter`) - the validator warns (PB-62).

## DT (inline selectors) [docs]
`${IP(val.Address == "8.8.8.8").Malicious}` or as root
`DBotScore(val.Score >= 3).Indicator`. Fine for one-liners; for anything a
human will edit, prefer `filters` - they show in the designer.

## DBotScore - the verdict source
`DBotScore: [{Indicator, Type, Vendor, Score, Reliability}]` one row per
vendor per indicator. Score: 0 unknown, 1 good, 2 suspicious, 3 bad.
Per-indicator verdict = max Score over its rows; disagreement = rows for the
same Indicator with both 1 and 3. Reliability (A+..F) lets one source outweigh
another. Many commands also set `<Type>.Malicious.Vendor` for score 3.

## Context hygiene
- Sub-playbooks with `separatecontext: true` and declared outputs.
- Write under your own namespace (`Triage.*`, `SignIn.*`), not into
  integration keys.
- `DeleteContext key=X` before a loop iteration that appends.
- Big outputs: `ignore-outputs: true` or `extend-context` with a jmespath to
  keep only what you need; oversize context slows the whole incident.
