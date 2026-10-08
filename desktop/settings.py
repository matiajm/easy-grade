"""App settings (API key, model, privacy options), stored per computer user.

Location (never inside the repo or the submissions folder):
    macOS:   ~/Library/Application Support/Easy Grade/settings.json
    Windows: %APPDATA%\\Easy Grade\\settings.json
    Linux:   ~/.config/easy-grade/settings.json
Set EASYGRADE_CONFIG_DIR to use another folder (the tests do this).
If no key is saved, the ANTHROPIC_API_KEY environment variable is used.
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

from grader.ai_grader import DEFAULT_MODEL

DEFAULTS = {"api_key": "", "model": DEFAULT_MODEL, "anonymize": True, "send_images": True}


def config_dir() -> Path:
    if os.environ.get("EASYGRADE_CONFIG_DIR"):
        return Path(os.environ["EASYGRADE_CONFIG_DIR"])
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / "Easy Grade"
    if sys.platform.startswith("win"):
        return Path(os.environ.get("APPDATA", Path.home())) / "Easy Grade"
    return Path.home() / ".config" / "easy-grade"


def _path() -> Path:
    return config_dir() / "settings.json"


def load_settings() -> dict:
    data = dict(DEFAULTS)
    try:
        saved = json.loads(_path().read_text(encoding="utf-8"))
        data.update({k: v for k, v in saved.items() if k in DEFAULTS})
    except (FileNotFoundError, ValueError):
        pass
    data["key_source"] = "settings" if data["api_key"] else None
    if not data["api_key"] and os.environ.get("ANTHROPIC_API_KEY"):
        data["api_key"] = os.environ["ANTHROPIC_API_KEY"]
        data["key_source"] = "environment"
    return data


def save_settings(updates: dict) -> dict:
    current = {k: v for k, v in load_settings().items() if k in DEFAULTS}
    if current.get("api_key") == os.environ.get("ANTHROPIC_API_KEY") and load_settings()["key_source"] == "environment":
        current["api_key"] = ""  # don't copy an environment key into the file
    for k in DEFAULTS:
        if k in updates and updates[k] is not None:
            v = updates[k]
            current[k] = v.strip() if isinstance(v, str) else bool(v)
    if not current["model"]:
        current["model"] = DEFAULT_MODEL
    path = _path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(current, indent=2), encoding="utf-8")
    try:
        os.chmod(path, 0o600)  # readable only by this user
    except OSError:
        pass
    return load_settings()


def mask(key: str) -> str:
    if not key:
        return ""
    return key[:7] + "…" + key[-4:] if len(key) > 12 else "…" + key[-2:]
