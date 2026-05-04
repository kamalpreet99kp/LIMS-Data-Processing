# TOF-LIMS Desktop: PyCharm Sync / Clean-State Checklist

Use this checklist when GitHub showed conflicts earlier and you want to ensure PyCharm runs the latest clean code.

## 1) Clean branch state

```bash
git fetch --all --prune
git checkout <your-feature-branch>
git reset --hard origin/<your-feature-branch>
git clean -fd
```

## 2) Confirm latest app version marker

The app window title should include:

`TOF-LIMS Professional Spectrum Studio v2.1`

If not, your local code is stale.

## 3) Verify no conflict artifacts

```bash
rg "codex/|<<<<<<<|=======|>>>>>>>" tof_lims_desktop
```

Expected: no output.

## 4) Verify package-safe imports

```bash
rg "from core\\.|from ui\\.|import core|import ui" tof_lims_desktop
```

Expected: no output.

## 5) Verify Python syntax + JSON

```bash
python -m json.tool tof_lims_desktop/data/isotope_data.json
python -m py_compile tof_lims_desktop/main.py tof_lims_desktop/ui/main_window.py tof_lims_desktop/core/*.py
```

## 6) Run app from repo root

```bash
python -m tof_lims_desktop.main
```

## 7) If PyCharm still runs stale code

- File -> Invalidate Caches / Restart
- Confirm interpreter points to same environment as terminal
- Re-open project from disk path that contains latest Git branch checkout
- Ensure no local uncommitted edits in `tof_lims_desktop/ui/main_window.py`

## 8) Quick runtime smoke checks

1. Load spectrum file.
2. Apply baseline and calibration.
3. Re-detect peaks.
4. Change line style via **Line Properties**.
5. Edit title (double-click title).
6. Check candidate dropdown in table.
7. Save project and reload.
