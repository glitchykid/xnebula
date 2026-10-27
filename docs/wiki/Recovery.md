# Recovery and verification

1. Read each preview and its feature effects. Enter returns to the menu; applying requires `APPLY`.
2. Keep the backup path printed before settings/service/animation changes. Menu option **6** lists backups automatically, newest-first.
3. Restore overlapping changes newest-first. The app skips already-restored values and refuses conflicting later edits. Restoring creates a new backup for the recovery operation.
4. Service backups preserve startup mode, delayed automatic startup, and running/stopped state. Restore order reverses the disabling order so dependencies can come back first.
5. Animation backups capture all supported preference flags plus the old taskbar value, including an absent value. Restoration changes the account running the app; sign out if taskbar behavior has not refreshed.
6. Failed or interrupted actions can leave partial changes. Keep the automatic JSONL log and check Windows before retrying. App removal attempts remaining packages while reporting each failure; other operation groups stop at the failure.

Backups are bound to machine/account identities and restricted to known registry/service/animation targets. Older registry snapshots remain accepted for recognized targets even though their original feature screens were removed.

**App binaries, app data, Edge installation files, and deleted Recall snapshots are not in these backups.** Reinstall removed applications/Edge separately. Removing Store/App Installer may require original signed packages or Windows media for recovery. Forced Edge file removal can leave an installed-app entry, and updates can recreate the browser.

Automated tests use fake Appx/service/browser cmdlets, intercepted native permission commands, and an in-memory Windows preference API. They exercise actual production PowerShell scripts without deleting host files or changing host services. Manual elevated disposable-VM testing remains necessary for:

- Actual uninstall/provisioning changes across two existing accounts and a new account.
- Real Edge vendor uninstall, locked files, ownership/deletion fallback, and reinstall recovery.
- Service dependency behavior and restoration on the target Windows edition.
- Effective privacy policies after sign-out/restart, including organization-managed devices.
- Animation behavior across desktop/taskbar/apps and restoration of preferences.
- Black console rendering, colored status readability, and the real UAC prompt.
