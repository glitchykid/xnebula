# Runtime logic review — 2026-11-03

Scope: CLI/menu confirmation, app/Edge deletion boundaries, settings and native preference recovery, service dependencies, malformed snapshots and durable writes. Findings below have regression coverage and are fixed in v0.4.1.

| Priority | Finding | Correction and evidence |
| --- | --- | --- |
| High | Menu APPLY rebuilt a fresh plan with automatic confirmation, allowing changes absent from the original preview. | Retain a deep copy of the reviewed plan and compare before mutations across removal, privacy, services, animations, Edge and all recovery kinds. `test_runtime_guards.py` changes state or replaces backups while the confirmation prompt is open. |
| High | Animation disabling reread preferences after confirmation and could overwrite intervening edits. | Apply the captured before/after plan; refuse changed preferences before creating a backup or writing. |
| High | Service/animation recovery reread a backup after confirmation and could apply a replacement document. | Calculate and retain the recovery plan before confirmation; apply those captured values with current-state checks. |
| High | Appx publisher matching accepted names beginning with Microsoft Corporation/Windows, including longer unrelated names. | Require a complete certificate CN boundary in discovery and installed-package removal; production PowerShell runs against substitute cmdlets in `test_windows.py`. |
| Medium | Duplicate or unsupported registry changes could produce an unusable backup and partial application before validation failed. | Validate all targets, values and labels before creating files or writing; detect case-insensitive duplicate legacy startup value names. `test_settings.py` also verifies fsync ordering/failure before registry writes. |
| Medium | Boolean/floating schema values compared equal to integer schema 1. | Require an actual integer schema in registry and native snapshot readers; `test_settings.py` and `test_recovery.py`. |
| Medium | Service dependency matching was case-sensitive despite Windows service identity rules. | Normalize dependency references for ordering, cycle detection and propagation of external-dependent blocks; `test_system_actions.py`. |
| Medium | Invalid dependency containers and malformed Appx/Edge removal fields reached native boundaries or caused unexpected exceptions. | Reject invalid data before native execution; `test_system_actions.py`, `test_windows.py`, `test_edge_validation.py`. |

Standalone app/Edge commands also recheck inventory after typed confirmation and refuse changed plans. Already-disabled animations skip confirmation and writes. Native service/animation and registry state checks remain in place immediately before application. Independent review covers the final changes.

## Verification and practical limits

Final automated test counts, coverage and builds are recorded in the v0.4.1 release notes. Tests use fake Windows mutation APIs and substitute cmdlets, including the production PowerShell scripts. The search/EDIT workflow and portable launchers remain covered.

This review does not prove the absence of bugs. Windows operations are not atomic transactions: another process can change system state, an operation can fail after earlier changes, and a timed-out native operation can still be processing. There is no automatic rollback for app/Edge deletion. Keep the backup and journal after a partial failure; inspect Windows before retrying. Real elevated uninstall, UAC, locked files, effective policies and power-loss recovery still require validation in a disposable Windows VM. No destructive operation was performed on the development host.
