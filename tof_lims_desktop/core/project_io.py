from __future__ import annotations

import json
from pathlib import Path


def save_project(path: str, payload: dict):
    Path(path).write_text(json.dumps(payload, indent=2), encoding='utf-8')


def load_project(path: str) -> dict:
    return json.loads(Path(path).read_text(encoding='utf-8'))
