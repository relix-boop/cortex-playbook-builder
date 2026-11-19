# Delivery

## Message template

1. **Files** - list, upload order (scripts → child playbooks → parent).
2. **What it does** - one paragraph; branches and outcomes (verdict values).
3. **Fill in after upload** - inputs to set, trigger/automation rule/incident
   type to attach, instance names for pinned commands, approvers.
4. **Not verified** - each assumed field / command / close reason with the
   check: `!Print value=${alert.country}`, `!xdr-xql-generic-query ...`.
5. **Validator result** - `0 errors, 0 warnings` (+ INFO items that matter).
6. **Test matrix** - table from `no-access-checklist.md`.
7. **GUI steps left for the user** with menu paths (adopt, trigger order,
   automation rule) - things no API does. [field]
8. "First run is calibration" - verdict-only for a week, then AutoClose.

## Upload options

| Platform | Keeps it custom | How |
|---|---|---|
| any | yes | UI: Playbooks → Import (upload the .yml) |
| XSOAR 6 | yes | `POST /playbook/save/yaml` multipart `file`, header `Authorization: <key>` |
| XSOAR 8 / XSIAM | yes | `POST https://api-<tenant>/xsoar/playbook/save/yaml` with `Authorization` + `x-xdr-auth-id` [docs] |
| XSIAM | yes | `POST /public_api/v1/playbooks/insert` multipart ZIP [field] |
| any | yes* | `demisto-sdk upload -i playbook-X.yml` (env `DEMISTO_BASE_URL`, `DEMISTO_API_KEY`, `XSIAM_AUTH_ID` on 8/XSIAM) |
| any | **no** | uploading a whole content pack zip → System, locked in UI [field] |

*Single-file SDK upload keeps it custom; pack upload does not.

After upload: download it again and diff - invalid fields are dropped silently
on insert. [field]
