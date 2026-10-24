"""Ideas and their persistence in a single JSON file."""

import json
import os
import re
import shutil
import sys
import tempfile
import uuid
from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath

SCHEMA_VERSION = 2
STATUSES = ("considering", "pursuing", "dropped")


APP_NAME = "Rubric"


def data_dir(
    platform: str = sys.platform,
    env: Mapping[str, str] = os.environ,
    home: Path | None = None,
) -> Path:
    """The per-user folder where this OS expects application data."""
    home = home or Path.home()
    if platform == "darwin":
        return home / "Library" / "Application Support" / APP_NAME
    if platform.startswith("win"):
        base = env.get("APPDATA")
        return (Path(base) if base else home / "AppData" / "Roaming") / APP_NAME
    # Linux and other Unix: XDG Base Directory spec (relative values are invalid).
    base = env.get("XDG_DATA_HOME", "")
    root = Path(base) if base and PurePosixPath(base).is_absolute() else home / ".local" / "share"
    return root / APP_NAME.lower()


DEFAULT_PATH = data_dir() / "ideas.json"


class StorageError(Exception):
    """The data file can't be read safely. The file is left untouched."""


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


# Criterion ids that were renamed; old keys in saved data are carried over on load.
RENAMED_IDS = {"problem_severity": "solution_importance"}


def _rename_ids(d: dict) -> dict:
    return {RENAMED_IDS.get(k, k): v for k, v in d.items()}


def _valid_color(value) -> str:
    """Return value if it is a "#rrggbb" string, else "" (no color)."""
    if isinstance(value, str) and re.fullmatch(r"#[0-9a-fA-F]{6}", value):
        return value.lower()
    return ""


# The four-part description of an idea, as the Roast council needs it.
DESCRIPTION_FIELDS = ("concept", "customer", "edge", "constraints")

SWOT_FIELDS = ("strengths", "weaknesses", "opportunities", "threats")


@dataclass
class Idea:
    name: str
    concept: str = ""  # what the idea is and does
    customer: str = ""  # who it is for, and how it makes money
    edge: str = ""  # your relevant skills, audience, assets
    constraints: str = ""  # budget, timeline, time to first dollar
    strengths: str = ""
    weaknesses: str = ""
    opportunities: str = ""
    threats: str = ""
    status: str = STATUSES[0]
    color: str = ""  # "#rrggbb", or "" if none chosen
    scores: dict[str, int] = field(default_factory=dict)
    reasons: dict[str, str] = field(default_factory=dict)
    weights: dict[str, float] = field(default_factory=dict)  # percent; {} = defaults
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
                # Schema 1 had one free-text "description"; it becomes the concept.
                concept=str(data.get("concept", data.get("description", ""))),
                customer=str(data.get("customer", "")),
                edge=str(data.get("edge", "")),
                constraints=str(data.get("constraints", "")),
                strengths=str(data.get("strengths", "")),
                weaknesses=str(data.get("weaknesses", "")),
                opportunities=str(data.get("opportunities", "")),
                threats=str(data.get("threats", "")),
                status=str(data.get("status", STATUSES[0])),
                color=_valid_color(data.get("color", "")),
                scores={str(k): int(v) for k, v in _rename_ids(data.get("scores", {})).items()},
                reasons={str(k): str(v) for k, v in _rename_ids(data.get("reasons", {})).items()},
                weights={str(k): float(v) for k, v in _rename_ids(data.get("weights", {})).items()},
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
