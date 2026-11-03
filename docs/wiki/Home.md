# XNebula

Download the [latest Windows x64 ZIP](https://github.com/glitchykid/xnebula/releases/latest), extract it, and open `Start-XNebula-Admin.cmd`. The app includes Python and runs in Windows PowerShell with colored terminal controls, preserving your console theme.

The six-action menu covers Windows apps, optional services, supported privacy protections, Windows animations, forced Edge removal, and settings recovery. App/service checklists use Up/Down, Space, A for all/none, Enter, and Esc; redirected input accepts numbers/ranges/all; every change previews before `APPLY`.

- [Installation and command reference](https://github.com/glitchykid/xnebula/blob/main/README.md)
- [Policies and Windows integration](Policies.md)
- [Recovery and validation](Recovery.md)
- [Runnable v0.4.0 milestone](https://github.com/glitchykid/xnebula/blob/main/docs/releases/v0.4.0.md)

App removal discovers Microsoft Appx/MSIX packages across existing accounts and future-account provisioning. Essential Windows components, runtimes, and unrelated desktop programs are excluded. Edge removal is explicit and can force-delete only the validated installation directory if the signed vendor uninstaller leaves it installed. Services are disabled with recovery data rather than deleting their registrations.

Policy availability depends on Windows edition/build. User preferences, including animations, affect the account running the app. Some privacy controls can stop microphone/camera access, notifications, location, or other features; previews describe these effects.

Automatic backups/logs live in `.xnebula/logs`. Restore backups by number from the menu. Keep backups when updating into a new extracted folder. App deletion does not undo Windows settings. Previous profile/startup/storage/report screens have been removed to keep the app focused.

Menu confirmation retries after a mistyped APPLY, preserving the selection. Terminals without cursor controls (including TERM=dumb) use numbered selection. Animation recovery checks each effect for conflicting later edits before writing.

Checklists support / to search names, Backspace to edit and Enter to finish typing. A acts on matching rows; hidden checked items stay selected. Esc clears the search, then cancels. EDIT at an app/service preview reopens the previous selection and previews revisions before APPLY. The menu reports scan activity and operation outcomes. Backup rows show local time to seconds and filename, and unreadable files are counted without hiding readable entries.

Optional media extensions such as HEVC, HEIF, AV1, VP9, MPEG-2, Web Media, WebP, and Raw Image appear by readable names in the checklist when installed and removable. Nothing is preselected. Removing a codec can affect playback, image viewing, or thumbnails in apps using Windows codecs.
