"""The Anthropic API key: environment variable, then the OS credential store.

The key never goes in ideas.json. On macOS it lives in the Keychain, reached through
the `security` tool that ships with the OS. Elsewhere there is no built-in store,
so it falls back to a file readable only by the user.
"""

import os
import re
import subprocess
import sys
from collections.abc import Mapping
from pathlib import Path

from .storage import APP_NAME, data_dir

ENV_VAR = "ANTHROPIC_API_KEY"
KEYCHAIN_ACCOUNT = "anthropic-api-key"
KEY_FILE = "api_key"
SECURITY = "/usr/bin/security"
NOT_FOUND = 44  # `security` exit status for "item could not be found"

# Anthropic keys are letters, digits, "-" and "_". Anything else (spaces, quotes) is
# a paste mistake, and would also confuse the command we hand to `security`.
_KEY_RE = re.compile(r"[A-Za-z0-9_-]+")


class ApiKeyError(Exception):
    """The key can't be read, stored or removed. Never carries the key itself."""


def valid_key(key: str) -> bool:
    return bool(_KEY_RE.fullmatch(key))


def _run(args: list[str], stdin: str | None = None) -> subprocess.CompletedProcess:
    try:
        return subprocess.run(
            args, input=stdin, capture_output=True, text=True, timeout=30
        )
    except (OSError, subprocess.SubprocessError) as e:
        raise ApiKeyError(f"Can't run {args[0]}: {e.__class__.__name__}") from e


def _key_file(platform: str, env: Mapping[str, str], home: Path | None) -> Path:
    return data_dir(platform, env, home) / KEY_FILE


def get_key(
    platform: str = sys.platform,
    env: Mapping[str, str] = os.environ,
    home: Path | None = None,
    run=_run,
) -> str | None:
    """The key to use, or None if there isn't one. The environment wins."""
    from_env = env.get(ENV_VAR, "").strip()
    if from_env:
        return from_env
    if platform == "darwin":
        done = run(
            [SECURITY, "find-generic-password", "-s", APP_NAME,
             "-a", KEYCHAIN_ACCOUNT, "-w"]
        )
        if done.returncode == NOT_FOUND:
            return None
        if done.returncode != 0:
            raise ApiKeyError("Can't read the API key from the Keychain.")
        return done.stdout.strip() or None
    path = _key_file(platform, env, home)
    try:
        return path.read_text(encoding="utf-8").strip() or None
    except FileNotFoundError:
        return None
    except OSError as e:
        raise ApiKeyError(f"Can't read {path}: {e.strerror}") from e


def set_key(
    key: str,
    platform: str = sys.platform,
    env: Mapping[str, str] = os.environ,
    home: Path | None = None,
    run=_run,
) -> None:
    """Store the key, replacing any earlier one."""
    key = key.strip()
    if not valid_key(key):
        raise ApiKeyError("That doesn't look like an API key.")
    if platform == "darwin":
        # `security -i` reads the command from stdin, so the key never appears in the
        # argument list that other processes can see with `ps`.
        command = (
            f"add-generic-password -U -s {APP_NAME} -a {KEYCHAIN_ACCOUNT} -w {key}\n"
        )
        if run([SECURITY, "-i"], stdin=command).returncode != 0:
            raise ApiKeyError("Can't save the API key to the Keychain.")
        return
    path = _key_file(platform, env, home)
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        # Created 0600 up front, so the key is never briefly readable by others.
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(key)
        os.chmod(path, 0o600)  # a pre-existing file keeps its old mode otherwise
    except OSError as e:
        raise ApiKeyError(f"Can't write {path}: {e.strerror}") from e


def delete_key(
    platform: str = sys.platform,
    env: Mapping[str, str] = os.environ,
    home: Path | None = None,
    run=_run,
) -> None:
    """Remove the stored key. Removing one that isn't there is not an error."""
    if platform == "darwin":
        done = run(
            [SECURITY, "delete-generic-password", "-s", APP_NAME,
             "-a", KEYCHAIN_ACCOUNT]
        )
        if done.returncode not in (0, NOT_FOUND):
            raise ApiKeyError("Can't remove the API key from the Keychain.")
        return
    path = _key_file(platform, env, home)
    try:
        path.unlink(missing_ok=True)
    except OSError as e:
        raise ApiKeyError(f"Can't remove {path}: {e.strerror}") from e
