# XNebula

A Python terminal app for Windows 11, operated from PowerShell. Preview and remove selected bundled apps across all accounts, configure privacy, manage startup entries, restrict background apps, configure Storage Sense, and disable Recall snapshots. Save configurations as profiles and review local change reports.

**Every system-changing command previews by default.** Add `--apply` to make changes and confirm the displayed plan. `--yes` skips confirmation only when paired with `--apply`. Building or testing this project does not debloat the development machine.

## Requirements

- Windows 11, build 22000 or newer. Windows 10 and Windows Server are outside the supported target.
- Python **3.15.1**, the latest stable release verified on 2026-10-26. Install the full Python distribution from [python.org](https://www.python.org/downloads/), including pip and venv.
- Built-in **Windows PowerShell 5.1** for native Appx/DISM compatibility. You may launch the Python CLI from Windows PowerShell or PowerShell 7; XNebula selects the built-in shell internally.
- An **administrator** PowerShell terminal for inventory, removal, and registry operations. Catalogs, help, profile creation, and reports work without elevation.
- Policy features require Windows Pro, Enterprise, Education, or corresponding IoT Enterprise editions. Home can use app removal and startup management, but unsupported policies are reported and skipped. Some suggestion policies require Enterprise/Education. Recall requires an enabled Recall component and Windows 11 24H2 with KB5055627 (26100.3915) or later.

## Install and run

From PowerShell:

```powershell
git clone https://github.com/glitchykid/xnebula.git
Set-Location xnebula
py -3.15 -m venv .venv
.\.venv\Scripts\python.exe -m pip install .
.\.venv\Scripts\python.exe -m xnebula --help
.\.venv\Scripts\xnebula.exe catalog
```

No virtual environment activation or execution-policy change is necessary. The app has **no runtime dependencies** beyond Python and Windows. Installation downloads the pinned build backend. A release wheel can be installed without build dependencies using `python -m pip install .\xnebula-0.1.0-py3-none-any.whl`.

Open PowerShell as administrator, return to the repository directory, and use the commands below. Substitute actual IDs from the list commands for the examples.

## App removal

```powershell
.\.venv\Scripts\xnebula.exe catalog
.\.venv\Scripts\xnebula.exe scan
.\.venv\Scripts\xnebula.exe remove news weather solitaire
.\.venv\Scripts\xnebula.exe remove news weather solitaire --apply
```

Supported IDs: `news`, `weather`, `solitaire`, `clipchamp`, `feedback`, `gethelp`, `tips`, `maps`. Availability varies by Windows installation.

Removal targets existing users with `Remove-AppxPackage -AllUsers` and provisioning for future users with `Remove-AppxProvisionedPackage -Online`. Exact identities are checked again before removal and queried afterward. Bundle parents are preferred over their main packages for the same name/version/publisher. Protected packages are refused. No wildcard removals or automatic elevation are performed.

Removal can delete app data. Journals are **not app backups**. Reinstall available apps through Microsoft Store; restoring provisioning for future accounts may require the original signed package, dependencies, and license. App removal has no automatic undo.

## Privacy and Recall

```powershell
.\.venv\Scripts\xnebula.exe privacy list
.\.venv\Scripts\xnebula.exe privacy set all
.\.venv\Scripts\xnebula.exe privacy set all --apply
# Or choose individual controls:
.\.venv\Scripts\xnebula.exe privacy set advertising diagnostics location --apply
.\.venv\Scripts\xnebula.exe recall list
.\.venv\Scripts\xnebula.exe recall disable
.\.venv\Scripts\xnebula.exe recall disable --apply
```

Privacy controls cover advertising ID, optional diagnostics, tailored experiences, suggested consumer content, activity feed/publishing/upload, and location. Diagnostics are limited to required data; an existing stricter zero is preserved. Activity settings do not erase previously stored history. Disabling location affects location-dependent apps and features.

The preview identifies each registry hive: **HKLM** applies device-wide; **HKCU** applies only to the account running XNebula. Tailored experiences and Settings suggestions use HKCU. Running under a different administrator account changes that administrator's user settings. Other users' private registry hives are not loaded or edited.

Unsupported settings are explicitly reported and skipped. The command may finish successfully with skipped settings; read the preview. Domain/MDM policies can override or reapply settings. Registry verification confirms written values, not the effective behavior of every Windows component. Sign out or restart after applying policies.

**Recall:** disabling snapshots can cause Windows to delete existing snapshots. Restoring the previous policy cannot recover them. XNebula detects the installed feature and supported build; it does not claim Recall is present merely because the registry policy exists.

## Startup and background apps

```powershell
.\.venv\Scripts\xnebula.exe startup list
.\.venv\Scripts\xnebula.exe startup disable 'user:Example'
.\.venv\Scripts\xnebula.exe startup disable 'user:Example' --apply
.\.venv\Scripts\xnebula.exe background list
.\.venv\Scripts\xnebula.exe background disable 'Example_publisher'
.\.venv\Scripts\xnebula.exe background disable 'Example_publisher' --apply
```

Startup management covers exact `Run` registry entries for the current user and machine-wide 32-bit/64-bit entries. It saves the original command and value type before removing the selected startup entry. Restore uses the backup command below. Startup folders, scheduled tasks, services, and packaged startup tasks are outside this version's startup manager.

Background restrictions use exact installed package family names. Existing deny-list entries are retained; selected families are removed from conflicting allow/user-control lists. Windows packaged-app policies do not stop every desktop application or service. Notifications and background syncing may stop for selected apps.

## Storage cleanup settings

```powershell
.\.venv\Scripts\xnebula.exe storage list
.\.venv\Scripts\xnebula.exe storage configure
.\.venv\Scripts\xnebula.exe storage configure --apply
# Optional permanent cleanup after the specified number of days:
.\.venv\Scripts\xnebula.exe storage configure --downloads-days 30 --recycle-days 30 --apply
```

The default configuration enables Storage Sense and temporary-file cleanup when space is low, preserves Downloads and Recycle Bin items, and retains local cloud-backed files. Retention accepts **0–365 days**, where zero means never delete. This configures Windows' scheduled cleanup; it does not perform an immediate file purge or estimate reclaimed space. A settings backup cannot recover deleted files.

## Backups, profiles, and reports

```powershell
# Use the actual backup path printed by an apply command:
.\.venv\Scripts\xnebula.exe restore '.xnebula\logs\settings-EXAMPLE.json'
.\.venv\Scripts\xnebula.exe restore '.xnebula\logs\settings-EXAMPLE.json' --apply

.\.venv\Scripts\xnebula.exe profile save my-profile.json --apps news weather --privacy all --storage --recall
.\.venv\Scripts\xnebula.exe profile run my-profile.json
.\.venv\Scripts\xnebula.exe profile run my-profile.json --apply
.\.venv\Scripts\xnebula.exe report
```

Profiles also accept `--startup`, `--background`, `--downloads-days`, and `--recycle-days`. They contain data, not shell commands. Profile execution previews every section before applying any section, scans again during application, and stops on failure. Each applied section has its own backup/journal. Profiles are not atomic transactions; earlier sections can remain applied if a later section fails. A profile referencing a missing startup entry or background app must be updated for that machine.

Settings backups are written and flushed before mutation and bound to the machine ID and account SID. Restoration preserves previous value types and deletes values that originally did not exist. It leaves empty keys in place. Restoration refuses conflicting later edits and skips values already restored. Restore newest backups first when changes overlap. Only restore trusted backups: they may contain startup commands and local account/machine identifiers.

Default output is `.xnebula/logs` relative to the working directory. Set `--log-dir PATH` on apply/report commands to choose another location. JSONL journals track `planned`, `started`, `removed`/`configured`, and `uncertain` events. A started action without a result has an unknown outcome. After a timeout/interruption, review the journal and rescan before retrying; Windows deployment work can outlive the CLI process. Failure stops subsequent actions without claiming rollback.

Exit codes: `0` completed/previewed/cancelled at confirmation, `1` operational or validation failure, `2` invalid command-line syntax, `130` Ctrl+C or closed input. No arguments display help.

## Development and validation

```powershell
py -3.15 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e '.[dev]'
.\.venv\Scripts\python.exe -m ruff check .
.\.venv\Scripts\python.exe -m ruff format --check .
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
.\.venv\Scripts\python.exe -m coverage run tests/run_tests.py
.\.venv\Scripts\python.exe -m coverage report
.\.venv\Scripts\python.exe -m build
```

To format deliberately: `.\.venv\Scripts\python.exe -m ruff format .`. Wheels and source archives are written to `dist/`. For an offline build with the pinned backend already installed, use `python -m build --no-isolation`.

`unittest` is the test runner. Combined statement/branch coverage must be at least **90%**, enforced by `coverage report`. Windows CI runs the same lint, format, coverage, and build checks. PowerShell integration tests run the production scripts with substitute Appx/DISM functions; registry tests use an in-memory API. Tests do not uninstall packages or modify real privacy/startup settings. Validate native mutations and effective policies separately in a disposable elevated Windows VM before broad deployment. The local development terminal did not provide administrator rights, so live system-wide mutation tests were not run.

Tool versions verified against official releases: Python 3.15.1, Ruff 0.17.2, Coverage.py 7.17.0, build 1.6.1, Hatchling 1.32.4. Development/build dependencies are pinned in `pyproject.toml`.

## Layout

```text
src/xnebula/       CLI, app catalog/planner, PowerShell bridge, registry settings,
                   backups, profiles, and journals
tests/             unit tests and PowerShell integration tests
docs/wiki/         versioned wiki pages
docs/releases/     milestone release notes and validation limitations
.github/workflows/ Windows CI
pyproject.toml     package metadata, dev dependencies, lint/coverage configuration
```

There are no graphical assets or GUI. Repository guidelines remain in `AGENTS.md` unchanged. See the [wiki home](docs/wiki/Home.md), [policy reference](docs/wiki/Policies.md), and [release notes](docs/releases/v0.1.0.md).
