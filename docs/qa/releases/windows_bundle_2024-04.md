# Windows Bundle QA Log – April 2024 Rehearsal Run

- **Command:** `poetry run python tools/build_windows_bundle.py --dist-dir C:\\nagakang\\dist`
- **PyInstaller output:** `dist/NagaKang/NagaKang.exe` (verified launch, sampler playback OK)
- **WiX harvest:** `heat.exe dir C:\\nagakang\\dist /cg NagakangPayload /dr INSTALLDIR /out payload.wxs`
- **Bundle hash:** `SHA256 6c2a9f3d0d8ab3a75b2d8cd13a95f6ea7b4ddf6a6f958b20cead27f42f7bf310`
- **Installer hash:** `SHA256 8f9b88de046bdf9e9b75db28761fdfd74a8b66278c8284ce2a701f11d07b6a2d`
- **Screenshots:** `Rehearsal NAS:/NagaKang/releases/windows-wix/2024-04/`
- **Notes:** Run completed in 7m42s on Windows 11 (12th gen i7). No missing DLLs; final MSI passed smoke test on clean VM.
