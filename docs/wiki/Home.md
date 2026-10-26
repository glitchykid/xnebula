# XNebula wiki

XNebula is a terminal application for Windows 11. Download the Windows x64 portable ZIP from the [latest release](https://github.com/glitchykid/xnebula/releases/latest), extract it, and open `Start-XNebula.cmd`. Python is included. For system-wide operations, open `Start-XNebula-Admin.cmd` and accept the Windows administrator prompt. The terminal menu previews changes before asking you to type `APPLY`.

- [Installation and command reference](https://github.com/glitchykid/xnebula/blob/main/README.md)
- [Privacy and policy reference](Policies.md)
- [Recovery and verification](Recovery.md)
- [Runnable v0.2.0 release notes](https://github.com/glitchykid/xnebula/blob/main/docs/releases/v0.2.0.md)

The entire extracted folder must stay together. Backups/reports live in `.xnebula/logs` inside it. Extract updates into a fresh folder and preserve existing backups and profiles. Deleting the app does not undo Windows changes. Source/developer installations can use `.venv` with the same launchers.

App removal covers all existing accounts and future-account provisioning. User-scoped privacy policies apply to the account running the app. Current startup support covers Run registry values. The app reports Windows edition restrictions and creates settings backups before writing.

These pages are maintained in `docs/wiki` alongside the code and can be mirrored to the repository's GitHub Wiki.
