from __future__ import annotations

from pathlib import Path


def main() -> int:
    root = Path(__file__).resolve().parents[1]
    target = root / 'Ex345_calibrated-Test.csv'
    print('TOF-LIMS Desktop diagnostics')
    print('Repo root:', root)
    print('Expected test file:', target)
    print('Test file exists:', target.exists())
    if target.exists():
        print('File size (bytes):', target.stat().st_size)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
