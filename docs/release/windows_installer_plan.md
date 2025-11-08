# Windows Installer Enablement – Musician-Friendly Distribution

The Step 3 roadmap targets a Windows installer for the first public musician
preview. This note captures the groundwork required to wrap the Python-based
tracker prototype inside an MSI (or MSIX) so rehearsal leads can install it
without development tooling.

## Distribution Goals

- **Zero-dependency install:** Musicians should launch a guided installer that
  bundles Python, native DLLs, and audio assets without touching PowerShell or
  `pip`.
- **Code-signing ready:** Packaging choices must support Authenticode signatures
  so stage computers avoid SmartScreen warnings.
- **Upgrade-safe:** New builds should upgrade in-place without losing sample
  libraries or user presets.
- **Scriptable pipeline:** The repo should expose a repeatable CLI (invoked from
  CI) that produces the installer artifact alongside hashes for QA sign-off.

## Recommended Toolchain

1. **Executable bundling:** Use `pyinstaller` (or `briefcase`) to generate a
   standalone folder containing Python, compiled modules, and our entry-point
   console scripts. This keeps audio dependencies co-located for offline
   rehearsal rooms.
2. **MSI authoring:** Wrap the PyInstaller folder using [WiX Toolset 4](https://wixtoolset.org/).
   - Define product/upgrade codes for NagaKang.
   - Add shortcuts for the tracker launcher and documentation PDFs.
   - Register required VC++ runtimes (if any) via `Bundle` packages.
3. **Optional MSIX bridge:** Evaluate [MSIX Packaging Tool] for Microsoft Store
   distribution after MSI support lands.
4. **Signing & timestamping:** Configure a `sign.bat` helper that runs `signtool`
   using a repo-provided certificate thumbprint. CI can skip signing while local
   release builds sign artefacts.

## Prototype Tasks

- [x] Add a `tools/build_windows_bundle.py` script that drives PyInstaller using
      our `poetry` environment and exports a `dist/nagakang` folder.
- [x] Scaffold a WiX `.wxs` template under `tools/packaging/windows/` with
      placeholders for version, product codes, and install directories.
- [ ] Document environment prerequisites (`choco install wix`, `pip install
      pyinstaller`) in `docs/release/windows_installer_plan.md` once scripts land.
- [ ] Extend GitHub Actions with a Windows job that runs the bundler in dry-run
      mode to ensure cross-platform determinism before enabling signing.

## Testing & QA Notes

- Use a clean Windows 10/11 VM to verify audio playback, sample loading, and
  tracker notebooks without developer tools installed.
- Capture screenshots of each installer wizard panel for inclusion in the Step 4
  musician onboarding guide.
- Record hash/signature outputs for QA in `docs/qa/releases/` so facilitators can
  verify downloads onsite.

## Next Steps

1. Land the PyInstaller bundler script with musician-oriented CLI defaults.
2. Draft the WiX manifest and smoke-test uninstall/upgrade scenarios.
3. Hook the new tooling into the release checklist before the Step 3 freeze.

## Usage Notes

- Run `poetry run python tools/build_windows_bundle.py --dry-run` to verify the
  PyInstaller command before producing artefacts. Remove `--dry-run` for actual
  bundles. Use `--extra-data path/to/samples=samples` to include curated demo
  libraries for rehearsal leads.
- After bundling, feed `dist/nagakang` into `tools/packaging/windows/
  nagakang_product_template.wxs` by harvesting files with WiX `heat.exe` and
  compiling via `candle`/`light` once Windows build hosts are available.
