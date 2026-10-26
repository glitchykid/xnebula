# XNebula

A Python terminal app for Windows 11, operated from PowerShell. Preview and remove selected bundled apps across all accounts, configure privacy, manage startup entries, restrict background apps, configure Storage Sense, and disable Recall snapshots. Save configurations as profiles and review local change reports.

**Every system-changing command previews by default.** Add `--apply` to make changes and confirm the displayed plan. `--yes` skips confirmation only when paired with `--apply`. Building or testing this project does not debloat the development machine.

## Requirements

- Windows 11, build 22000 or newer. Windows 10 and Windows Server are outside the supported target.
- The portable release includes **Python 3.15.2**, the latest stable release verified on 2026-10-27. No separate Python installation is needed. The portable ZIP targets **Windows x64**; ARM64 users can use a native Python installation and the developer setup below.
- Built-in **Windows PowerShell 5.1** for native Appx/DISM compatibility. You may launch the Python CLI from Windows PowerShell or PowerShell 7; XNebula selects the built-in shell internally.
- An **administrator** PowerShell terminal for inventory, removal, and registry operations. Catalogs, help, profile creation, and reports work without elevation.
- Policy features require Windows Pro, Enterprise, Education, or corresponding IoT Enterprise editions. Home can use app removal and startup management, but unsupported policies are reported and skipped. Some suggestion policies require Enterprise/Education. Recall requires an enabled Recall component and Windows 11 24H2 with KB5055627 (26100.3915) or later.

## Download, extract, and start

1. Download **[xnebula-0.2.1-windows-x64.zip](https://github.com/glitchykid/xnebula/releases/download/v0.2.1/xnebula-0.2.1-windows-x64.zip)** from the [release page](https://github.com/glitchykid/xnebula/releases/latest).
2. Right-click the ZIP, choose **Extract All**, and keep the complete folder somewhere writable, such as Documents.
3. Open the extracted `XNebula` folder and double-click **`Start-XNebula.cmd`**. A numbered terminal menu opens in Windows PowerShell.
4. For system-wide scans and changes, open **`Start-XNebula-Admin.cmd`** and accept Windows' administrator prompt. Opening either launcher does not apply changes.

No Python setup, Git, pip, PATH changes, or internet connection is needed to start the portable app. Keep the bundled `.runtime`, `src`, and `scripts` folders with the launchers. The launchers use a process-only execution-policy setting; they do not change your saved PowerShell policy. Organization-enforced restrictions may still block unsigned scripts.

Choose a menu number, select IDs, review the preview, and type `APPLY` only when ready. Enter returns from a preview, and `0` exits. Existing CLI commands still work from PowerShell:

```powershell
.\Start-XNebula.cmd --help
.\Start-XNebula.cmd privacy list
.\Start-XNebula-Admin.cmd scan
```

The standard launcher does not request elevation. Use the administrator launcher or an already elevated PowerShell session for commands requiring it. Both launchers preserve arguments and exit codes and keep relative profiles, backups, and reports in the extracted app folder.

For updates, extract the new release into a **new folder**, retain the old `.xnebula` backups and saved profiles, and copy them across if needed. To uninstall the app, retain required backups and remove its extracted folder; this does not undo Windows changes. Use `restore` first when you want to revert settings.

Source checkouts do not include the runtime. Developers can install the app into `.venv` using the development commands below; the same launchers will use that environment. A wheel remains available for existing Python installations: `python -m pip install .\xnebula-0.2.1-py3-none-any.whl`.

## App removal

In the terminal menu, choose **2 — Remove selected apps**. Apps appear with numbers and their removal effects. Enter `1 3 5`, `1,3,5`, or a range such as `2-4`. Choose **9 — Select All** (or type `all`) to select all eight supported apps. `0` or an empty entry returns to the main menu. Invalid entries let you retry without reopening the picker. The selected app names appear before the removal preview; type `APPLY` only after reviewing it. Apps absent from the machine are skipped.

CLI commands continue to accept app IDs:

```powershell
.\Start-XNebula.cmd catalog
.\Start-XNebula.cmd scan
.\Start-XNebula.cmd remove news weather solitaire
.\Start-XNebula.cmd remove news weather solitaire --apply
```

Supported IDs: `news`, `weather`, `solitaire`, `clipchamp`, `feedback`, `gethelp`, `tips`, `maps`. Availability varies by Windows installation.

Removal targets existing users with `Remove-AppxPackage -AllUsers` and provisioning for future users with `Remove-AppxProvisionedPackage -Online`. Exact identities are checked again before removal and queried afterward. Bundle parents are preferred over their main packages for the same name/version/publisher. Protected packages and wildcard removals are refused. Elevation is requested only by the explicit administrator launcher.

Removal can delete app data. Journals are **not app backups**. Reinstall available apps through Microsoft Store; restoring provisioning for future accounts may require the original signed package, dependencies, and license. App removal has no automatic undo.

## Privacy and Recall

```powershell
.\Start-XNebula.cmd privacy list
.\Start-XNebula.cmd privacy set all
.\Start-XNebula.cmd privacy set all --apply
# Or choose individual controls:
.\Start-XNebula.cmd privacy set advertising diagnostics location --apply
.\Start-XNebula.cmd recall list
.\Start-XNebula.cmd recall disable
.\Start-XNebula.cmd recall disable --apply
```

Privacy controls cover advertising ID, optional diagnostics, tailored experiences, suggested consumer content, activity feed/publishing/upload, and location. Diagnostics are limited to required data; an existing stricter zero is preserved. Activity settings do not erase previously stored history. Disabling location affects location-dependent apps and features.

The preview identifies each registry hive: **HKLM** applies device-wide; **HKCU** applies only to the account running XNebula. Tailored experiences and Settings suggestions use HKCU. Running under a different administrator account changes that administrator's user settings. Other users' private registry hives are not loaded or edited.

Unsupported settings are explicitly reported and skipped. The command may finish successfully with skipped settings; read the preview. Domain/MDM policies can override or reapply settings. Registry verification confirms written values, not the effective behavior of every Windows component. Sign out or restart after applying policies.

**Recall:** disabling snapshots can cause Windows to delete existing snapshots. Restoring the previous policy cannot recover them. XNebula detects the installed feature and supported build; it does not claim Recall is present merely because the registry policy exists.

## Startup and background apps

```powershell
.\Start-XNebula.cmd startup list
.\Start-XNebula.cmd startup disable 'user:Example'
.\Start-XNebula.cmd startup disable 'user:Example' --apply
.\Start-XNebula.cmd background list
.\Start-XNebula.cmd background disable 'Example_publisher'
.\Start-XNebula.cmd background disable 'Example_publisher' --apply
```

Startup management covers exact `Run` registry entries for the current user and machine-wide 32-bit/64-bit entries. It saves the original command and value type before removing the selected startup entry. Restore uses the backup command below. Startup folders, scheduled tasks, services, and packaged startup tasks are outside this version's startup manager.

Background restrictions use exact installed package family names. Existing deny-list entries are retained; selected families are removed from conflicting allow/user-control lists. Windows packaged-app policies do not stop every desktop application or service. Notifications and background syncing may stop for selected apps.

## Storage cleanup settings

```powershell
.\Start-XNebula.cmd storage list
.\Start-XNebula.cmd storage configure
.\Start-XNebula.cmd storage configure --apply
# Optional permanent cleanup after the specified number of days:
.\Start-XNebula.cmd storage configure --downloads-days 30 --recycle-days 30 --apply
```

The default configuration enables Storage Sense and temporary-file cleanup when space is low, preserves Downloads and Recycle Bin items, and retains local cloud-backed files. Retention accepts **0–365 days**, where zero means never delete. This configures Windows' scheduled cleanup; it does not perform an immediate file purge or estimate reclaimed space. A settings backup cannot recover deleted files.

## Backups, profiles, and reports

```powershell
# Use the actual backup path printed by an apply command:
.\Start-XNebula.cmd restore '.xnebula\logs\settings-EXAMPLE.json'
.\Start-XNebula.cmd restore '.xnebula\logs\settings-EXAMPLE.json' --apply

.\Start-XNebula.cmd profile save my-profile.json --apps news weather --privacy all --storage --recall
.\Start-XNebula.cmd profile run my-profile.json
.\Start-XNebula.cmd profile run my-profile.json --apply
.\Start-XNebula.cmd report
```

Profiles also accept `--startup`, `--background`, `--downloads-days`, and `--recycle-days`. They contain data, not shell commands. Profile execution previews every section before applying any section, scans again during application, and stops on failure. Each applied section has its own backup/journal. Profiles are not atomic transactions; earlier sections can remain applied if a later section fails. A profile referencing a missing startup entry or background app must be updated for that machine.

Settings backups are written and flushed before mutation and bound to the machine ID and account SID. Restoration preserves previous value types and deletes values that originally did not exist. It leaves empty keys in place. Restoration refuses conflicting later edits and skips values already restored. Restore newest backups first when changes overlap. Only restore trusted backups: they may contain startup commands and local account/machine identifiers.

Default output is `.xnebula/logs` relative to the working directory. Set `--log-dir PATH` on apply/report commands to choose another location. JSONL journals track `planned`, `started`, `removed`/`configured`, and `uncertain` events. A started action without a result has an unknown outcome. After a timeout/interruption, review the journal and rescan before retrying; Windows deployment work can outlive the CLI process. Failure stops subsequent actions without claiming rollback.

Exit codes: `0` completed/previewed/cancelled at confirmation, `1` operational or validation failure, `2` invalid command-line syntax, `130` Ctrl+C or closed input. No arguments open the menu in an interactive terminal; redirected input displays help. The launchers explicitly open the menu when no command is given. `xnebula menu` also opens it directly.

## Development and validation

Install full Python 3.15.2 from [python.org](https://www.python.org/downloads/), then clone this repository. The embedded release runtime is for running the app, not pip/venv development.

```powershell
git clone https://github.com/glitchykid/xnebula.git
Set-Location xnebula
py -3.15 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e '.[dev]'
.\.venv\Scripts\python.exe -m ruff check .
.\.venv\Scripts\python.exe -m ruff format --check .
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
.\.venv\Scripts\python.exe -m coverage run tests/run_tests.py
.\.venv\Scripts\python.exe -m coverage report
.\.venv\Scripts\python.exe -m build
```

Build the portable release before running tests to include the actual launcher tests:

```powershell
Invoke-WebRequest -Uri https://www.python.org/ftp/python/3.15.2/python-3.15.2-embed-amd64.zip -OutFile "$env:TEMP\python-embed.zip"
.\.venv\Scripts\python.exe scripts/build_portable.py --runtime "$env:TEMP\python-embed.zip"
.\.venv\Scripts\python.exe -m unittest discover -s tests -p test_launcher.py -v
```

The builder checks the Python archive against the SHA-256 published on the [official 3.15.2 release page](https://www.python.org/downloads/release/python-3152/). It includes Python's license and writes a `.zip.sha256` checksum file alongside the ZIP. Only application source, launchers, runtime, and documentation enter the bundle; local profiles, backups, and developer tools are excluded. Windows CI builds this ZIP before the full coverage run so launcher tests are not skipped. UAC command encoding is tested without showing a UAC prompt; approval/cancellation of the real Windows prompt remains a manual check.

To format deliberately: `.\.venv\Scripts\python.exe -m ruff format .`. Wheels and source archives are written to `dist/`. For an offline build with the pinned backend already installed, use `python -m build --no-isolation`.

`unittest` is the test runner. Combined statement/branch coverage must be at least **90%**, enforced by `coverage report`. Windows CI runs the same lint, format, coverage, and build checks. PowerShell integration tests run the production scripts with substitute Appx/DISM functions; registry tests use an in-memory API. Tests do not uninstall packages or modify real privacy/startup settings. Validate native mutations and effective policies separately in a disposable elevated Windows VM before broad deployment. The local development terminal did not provide administrator rights, so live system-wide mutation tests were not run.

Tool versions verified against official releases: Python 3.15.2, Ruff 0.17.2, Coverage.py 7.17.0, build 1.6.1, Hatchling 1.32.4. Development/build dependencies are pinned in `pyproject.toml`.

## Layout

```text
src/xnebula/       CLI, app catalog/planner, PowerShell bridge, registry settings,
                   backups, profiles, and journals
tests/             unit tests and PowerShell integration tests
docs/wiki/         versioned wiki pages
docs/releases/     milestone release notes and validation limitations
.github/workflows/ Windows CI
scripts/           PowerShell launcher and verified portable ZIP builder
Start-XNebula*.cmd Standard and administrator double-click entry points
START-HERE.txt     Portable quick-start instructions
pyproject.toml     package metadata, dev dependencies, lint/coverage configuration
```

There are no graphical assets or GUI. Repository guidelines remain in `AGENTS.md` unchanged. See the [wiki home](docs/wiki/Home.md), [policy reference](docs/wiki/Policies.md), and [release notes](docs/releases/v0.2.1.md).
