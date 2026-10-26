# Recovery and verification

1. Read the preview before adding `--apply`. Record the backup and journal paths printed by the app.
2. If an operation fails, stop and run `xnebula report`. `uncertain` or unfinished actions require checking current system state.
3. For app removal, run `xnebula scan` again. Reboot first if Windows reported pending deployment work.
4. For registry settings/startup changes, preview `xnebula restore BACKUP.json`, then add `--apply` when the plan is correct. Restore overlapping backups newest-first. The restore operation creates its own backup.
5. If a later edit conflicts with a backup, the app refuses restoration. Review that value manually rather than forcing an overwrite.
6. Sign out/restart after policies change, then inspect Windows Settings or effective group policy. Organization-managed settings can reappear.

App data, removed provisioned packages, Recall snapshots, and files deleted by Storage Sense are not contained in settings backups. They cannot be recovered by the restore command. Keep independent backups where those data matter.

Automated tests exercise preview/apply/restore, exact app selection, invalid input, permission errors, partial failures, conflicting values, profile preflight, retention boundaries, and PowerShell scripts with simulated cmdlets. Live native mutation and multi-account policy behavior need an elevated disposable Windows VM. Do not mistake a passing simulated backend test for a verified Windows deployment.

Suggested manual VM acceptance procedure:

- Snapshot a Windows 11 Pro/Enterprise VM with two test accounts and one catalog app.
- Run an elevated scan and preview; confirm no change after a preview or declined prompt.
- Remove the selected app and check both existing users and a newly created user.
- Apply one privacy setting, inspect its effective setting after sign-out, then restore it.
- Disable a disposable Run entry and restore its exact command/value type.
- Verify background restrictions with a test packaged app and validate edition skips.
- Configure Storage Sense with zero retention thresholds and verify Downloads/Recycle Bin preservation.
- On supported Recall hardware, verify the snapshot policy after acknowledging deletion of test snapshots.
