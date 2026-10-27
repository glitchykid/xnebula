# Windows integration reference

The main privacy action applies supported settings rather than attempting to disable every Windows facility indiscriminately. Most policies require Pro/Enterprise/Education; settings unavailable on an edition/build are reported. Required diagnostics remain enabled on Pro. On supported Enterprise/Education editions, the diagnostic level is set to zero. Domain/MDM management can override local settings.

| Feature | Windows integration | Scope |
| --- | --- | --- |
| Microsoft app removal | Get-AppxPackage / Remove-AppxPackage -AllUsers, plus online provisioning removal | Existing/new accounts |
| Optional services | Win32_Service, service manager startup controls, Stop-Service / Start-Service | Machine |
| Advertising ID | AdvertisingInfo / DisabledByGroupPolicy | Machine |
| Diagnostic data | DataCollection / AllowTelemetry | Machine |
| Tailored experiences | CloudContent / DisableTailoredExperiencesWithDiagnosticData | Current account |
| Consumer suggestions | CloudContent consumer/Spotlight policies | Edition-dependent; machine/current account |
| Activity publishing/upload | System / EnableActivityFeed, PublishUserActivities, UploadUserActivities | Machine |
| Location | LocationAndSensors / DisableLocation | Machine |
| Packaged-app access | AppPrivacy / LetAppsAccessCamera, Microphone, Contacts, Calendar, Email, CallHistory, Messaging, Tasks, AccountInfo | Machine |
| App diagnostics/background | AppPrivacy / LetAppsGetDiagnosticInfo, LetAppsRunInBackground | Machine |
| Speech | Software\Policies\Microsoft\InputPersonalization / AllowInputPersonalization | Machine |
| Clipboard sync | System / AllowCrossDeviceClipboard | Machine |
| Recall snapshots | WindowsAI / DisableAIDataAnalysis, after feature/build checks | Machine |
| Animations | SystemParametersInfoW preference flags and Explorer Advanced / TaskbarAnimations | Current account |
| Edge | Signed vendor uninstall; bounded ownership/access and deletion fallback | Machine/current account installation |

Privacy paths are below `Software\Policies\Microsoft\Windows` except where shown. Packaged-app access is force-denied with DWORD 2, with existing allow/user-control exception lists cleared so they cannot override the chosen protection. Browser/desktop app permissions are not universally controlled by these packaged-app policies.

Windows app discovery checks Microsoft publisher metadata and protects frameworks, resources, SystemApps, the terminal host, Windows Security, sign-in/shell components, and runtimes. Edge's WebView2 runtime is excluded. Service selection is restricted to the documented optional catalog, with active dependency checks before each change.

Official references:

- [Get-AppxPackage](https://learn.microsoft.com/en-us/powershell/module/appx/get-appxpackage?view=windowsserver2025-ps), [Remove-AppxPackage](https://learn.microsoft.com/en-us/powershell/module/appx/remove-appxpackage?view=windowsserver2025-ps), [provisioning removal](https://learn.microsoft.com/en-us/powershell/module/dism/remove-appxprovisionedpackage?view=windowsserver2025-ps)
- [Windows privacy policies](https://learn.microsoft.com/en-us/windows/client-management/mdm/policy-csp-privacy), [experience policies](https://learn.microsoft.com/en-us/windows/client-management/mdm/policy-csp-experience), [diagnostic policy](https://learn.microsoft.com/en-us/windows/client-management/mdm/policy-csp-system#allowtelemetry)
- [Windows AI/Recall policies](https://learn.microsoft.com/en-us/windows/client-management/mdm/policy-csp-windowsai)
- [Win32_Service](https://learn.microsoft.com/en-us/windows/win32/cimwin32prov/win32-service), [Set-Service](https://learn.microsoft.com/en-us/powershell/module/microsoft.powershell.management/set-service?view=powershell-5.1)
- [SystemParametersInfoW](https://learn.microsoft.com/en-us/windows/win32/api/winuser/nf-winuser-systemparametersinfow)
- [Edge uninstall policy and regional limitations](https://learn.microsoft.com/en-us/deployedge/microsoft-edge-update-policies#uninstall)
- [takeown](https://learn.microsoft.com/en-us/windows-server/administration/windows-commands/takeown), [icacls](https://learn.microsoft.com/en-us/windows-server/administration/windows-commands/icacls), [Remove-Item](https://learn.microsoft.com/en-us/powershell/module/microsoft.powershell.management/remove-item?view=powershell-5.1)

Edge force deletion is a file-removal fallback, not Microsoft's supported regional uninstall policy. It does not promise clean application registration removal or persistence across Windows updates. All recursive file operations are restricted to a verified Edge installation root; reparse points cause refusal.
