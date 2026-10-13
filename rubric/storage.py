"""Ideas and their persistence in a single JSON file."""

import json
import os
import re
import sys
import shutil
import tempfile
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

SCHEMA_VERSION = 1
STATUSES = ("considering", "pursuing", "dropped")
LEGACY_PATH = Path.home() / ".rubric" / "ideas.json"


def _default_path() -> Path:
    """data/ideas.json next to the program: beside Rubric.app when built, else
    in the project folder."""
    if getattr(sys, "frozen", False):
        exe = Path(sys.executable).resolve()
        # .../Rubric.app/Contents/MacOS/Rubric -> the folder holding Rubric.app
        base = next((p.parent for p in exe.parents if p.suffix == ".app"), exe.parent)
    else:
        base = Path(__file__).resolve().parent.parent
    return base / "data" / "ideas.json"


DEFAULT_PATH = _default_path()


class StorageError(Exception):
    """The data file can't be read safely. The file is left untouched."""


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _valid_color(value) -> str:
    """Return value if it is a "#rrggbb" string, else "" (no color)."""
    if isinstance(value, str) and re.fullmatch(r"#[0-9a-fA-F]{6}", value):
        return value.lower()
    return ""


@dataclass
class Idea:
    name: str
    description: str = ""
    status: str = STATUSES[0]
    color: str = ""  # "#rrggbb", or "" if none chosen
    scores: dict[str, int] = field(default_factory=dict)
    reasons: dict[str, str] = field(default_factory=dict)
    weights: dict[str, int] = field(default_factory=dict)  # percent; {} = defaults
    id: str = field(default_factory=lambda: uuid.uuid4().hex)
    created: str = field(default_factory=_now)
    updated: str = field(default_factory=_now)

    def touch(self) -> None:
        self.updated = _now()

    @classmethod
    def from_dict(cls, data: dict) -> "Idea":
        try:
            return cls(
                id=str(data["id"]),
                name=str(data["name"]),
                description=str(data.get("description", "")),
                status=str(data.get("status", STATUSES[0])),
                color=_valid_color(data.get("color", "")),
                scores={str(k): int(v) for k, v in data.get("scores", {}).items()},
                reasons={str(k): str(v) for k, v in data.get("reasons", {}).items()},
                weights={str(k): int(v) for k, v in data.get("weights", {}).items()},
                created=str(data.get("created", _now())),
                updated=str(data.get("updated", _now())),
            )
        except (KeyError, TypeError, ValueError, AttributeError) as e:
            raise StorageError(f"Malformed idea entry: {e!r}") from e


class Storage:
    def __init__(self, path: Path | str = DEFAULT_PATH):
        self.path = Path(path)

    @property
    def backup_path(self) -> Path:
        return self.path.with_name(self.path.name + ".bak")

    def migrate_legacy(self, legacy: Path = LEGACY_PATH) -> None:
        """Copy data from the old ~/.rubric location the first time, if present."""
        if not self.path.exists() and legacy.exists():
            self.path.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(legacy, self.path)

    def load(self) -> list[Idea]:
        """Load all ideas. A missing file is an empty list; a bad file raises."""
        if not self.path.exists():
            return []
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, ValueError) as e:
            raise StorageError(f"Can't read {self.path}: {e}") from e
        if not isinstance(data, dict) or not isinstance(data.get("ideas"), list):
            raise StorageError(f"{self.path} is not a valid ideas file.")
        version = data.get("schema_version")
        if not isinstance(version, int) or version > SCHEMA_VERSION:
            raise StorageError(
                f"{self.path} has unsupported schema_version {version!r}."
            )
        return [Idea.from_dict(d) for d in data["ideas"]]

    def save(self, ideas: list[Idea]) -> None:
        """Atomically write ideas, keeping the previous file as a .bak."""
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "schema_version": SCHEMA_VERSION,
            "ideas": [vars(i) for i in ideas],
        }
        fd, tmp_name = tempfile.mkstemp(
            dir=self.path.parent, prefix=self.path.name, suffix=".tmp"
        )
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump(payload, f, indent=2, ensure_ascii=False)
                f.flush()
                os.fsync(f.fileno())
            if self.path.exists():
                shutil.copy2(self.path, self.backup_path)
            os.replace(tmp_name, self.path)
        except BaseException:
            Path(tmp_name).unlink(missing_ok=True)
            raise
