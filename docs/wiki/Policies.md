# Policy reference

Microsoft's current policy documentation and the installed Windows ADMX definitions are the source for registry mappings. Paths below are relative to `Software\Policies\Microsoft\Windows`.

| Control | Hive / subkey | Value | Target |
| --- | --- | --- | --- |
| Advertising ID | HKLM / AdvertisingInfo | DisabledByGroupPolicy | DWORD 1 |
| Optional diagnostics | HKLM / DataCollection | AllowTelemetry | DWORD 1; retain existing 0 |
| Tailored experiences | HKCU / CloudContent | DisableTailoredExperiencesWithDiagnosticData | DWORD 1 |
| Settings suggestions | HKCU / CloudContent | DisableWindowsSpotlightOnSettings | DWORD 1; Enterprise/Education |
| Consumer suggestions | HKLM / CloudContent | DisableWindowsConsumerFeatures | DWORD 1; Enterprise/Education |
| Activity feed | HKLM / System | EnableActivityFeed | DWORD 0 |
| Activity publishing | HKLM / System | PublishUserActivities | DWORD 0 |
| Activity upload | HKLM / System | UploadUserActivities | DWORD 0 |
| Location | HKLM / LocationAndSensors | DisableLocation | DWORD 1 |
| Recall snapshots | HKLM / WindowsAI | DisableAIDataAnalysis | DWORD 1; available updated Recall only |
| Background apps | HKLM / AppPrivacy | LetAppsRunInBackground and exception lists | Retain existing default; selected families in MULTI_SZ deny list |
| Storage Sense | HKLM / StorageSense | AllowStorageSenseGlobal | DWORD 1 |
| Temporary cleanup | HKLM / StorageSense | AllowStorageSenseTemporaryFilesCleanup | DWORD 1 |
| Cleanup schedule | HKLM / StorageSense | ConfigStorageSenseGlobalCadence | DWORD 0 (low space) |
| Downloads / Recycle Bin | HKLM / StorageSense | ConfigStorageSenseDownloadsCleanupThreshold / ConfigStorageSenseRecycleBinCleanupThreshold | DWORD 0 by default, configurable 0–365 |
| Local cloud content | HKLM / StorageSense | ConfigStorageSenseCloudContentDehydrationThreshold | DWORD 0 |

Policy commands report unsupported editions. Writing the expected registry value does not prove every component applied the policy; sign out/restart and inspect effective Windows settings. Organization management may override local values.

Official sources checked 2026-10-26:

- [Privacy policies](https://learn.microsoft.com/en-us/windows/client-management/mdm/policy-csp-privacy)
- [Experience policies and edition restrictions](https://learn.microsoft.com/en-us/windows/client-management/mdm/policy-csp-experience)
- [Diagnostics policy](https://learn.microsoft.com/en-us/windows/client-management/mdm/policy-csp-system#allowtelemetry)
- [Location policies](https://learn.microsoft.com/en-us/windows/client-management/mdm/policy-csp-admx-sensors)
- [Windows AI and Recall](https://learn.microsoft.com/en-us/windows/client-management/mdm/policy-csp-windowsai)
- [Storage Sense](https://learn.microsoft.com/en-us/windows/configuration/storage/storage-sense)
- [Startup registry locations](https://support.microsoft.com/en-au/windows/experience/startup-boot/configure-startup-applications-in-windows)
- [Appx removal](https://learn.microsoft.com/en-us/powershell/module/appx/remove-appxpackage?view=windowsserver2025-ps)
- [Provisioning removal](https://learn.microsoft.com/en-us/powershell/module/dism/remove-appxprovisionedpackage?view=windowsserver2025-ps)
- [Python winreg](https://docs.python.org/3.15/library/winreg.html)

Windows PowerShell 5.1 is used as the OS-native adapter, even when the caller uses a newer PowerShell host. Runtime application code uses Python's standard library only.
