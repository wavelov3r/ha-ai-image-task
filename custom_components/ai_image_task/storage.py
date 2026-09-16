"""Filesystem helpers: atomic writes, history rotation and pruning.

Every function in this module is blocking and must be called through
``hass.async_add_executor_job``.
"""

from __future__ import annotations

import json
import logging
import os
import re
import shutil
import time
from dataclasses import dataclass
from datetime import datetime

from .const import (
    RETENTION_KEEP_DAYS,
    RETENTION_KEEP_LAST,
    RETENTION_OVERWRITE,
)

_LOGGER = logging.getLogger(__name__)

_INVALID_CHARS = re.compile(r"[^A-Za-z0-9._\- ]+")


def sanitize_filename(name: str, default: str = "image.jpg") -> str:
    """Make ``name`` a safe single-segment file name."""
    name = (name or "").strip().replace("\\", "/").split("/")[-1]
    name = _INVALID_CHARS.sub("_", name).strip()
    name = re.sub(r"\s+", "_", name)
    if not name or name in (".", ".."):
        name = default
    if not os.path.splitext(name)[1]:
        name += ".jpg"
    return name


@dataclass(slots=True)
class SaveResult:
    """Outcome of a save operation."""

    path: str
    archived_path: str | None
    history_count: int
    pruned: int


def ensure_directory(path: str) -> None:
    """Create ``path`` (and parents) if needed; raise on failure."""
    os.makedirs(path, exist_ok=True)
    if not os.access(path, os.W_OK):
        raise PermissionError(f"Directory '{path}' is not writable")


def check_directory(path: str) -> None:
    """Config-flow validation helper."""
    ensure_directory(path)
    probe = os.path.join(path, ".ai_image_task_write_test")
    with open(probe, "wb") as handle:
        handle.write(b"ok")
    os.remove(probe)


def _history_dir(output_dir: str, history_subdir: str | None) -> str:
    if history_subdir:
        return os.path.join(output_dir, history_subdir)
    return output_dir


def _archive_name(filename: str, when: datetime) -> str:
    stem, ext = os.path.splitext(filename)
    return f"{stem}_{when.strftime('%Y%m%d_%H%M%S')}{ext}"


def _history_files(history_dir: str, filename: str) -> list[str]:
    """Archived copies of ``filename``, oldest first."""
    stem, ext = os.path.splitext(filename)
    pattern = re.compile(rf"^{re.escape(stem)}_\d{{8}}_\d{{6}}{re.escape(ext)}$")
    if not os.path.isdir(history_dir):
        return []
    found = [
        os.path.join(history_dir, entry)
        for entry in os.listdir(history_dir)
        if pattern.match(entry)
    ]
    found.sort(key=lambda p: os.path.getmtime(p))
    return found


def prune_history(
    output_dir: str,
    filename: str,
    history_subdir: str | None,
    retention_mode: str,
    keep_count: int,
    keep_days: int,
) -> int:
    """Delete archived copies according to the retention policy."""
    history_dir = _history_dir(output_dir, history_subdir)
    files = _history_files(history_dir, filename)
    removed = 0

    if retention_mode == RETENTION_KEEP_LAST:
        excess = len(files) - max(int(keep_count), 0)
        for path in files[: max(excess, 0)]:
            try:
                os.remove(path)
                removed += 1
            except OSError as err:  # pragma: no cover - defensive
                _LOGGER.warning("Cannot delete %s: %s", path, err)
    elif retention_mode == RETENTION_KEEP_DAYS:
        cutoff = time.time() - max(int(keep_days), 0) * 86400
        for path in files:
            try:
                if os.path.getmtime(path) < cutoff:
                    os.remove(path)
                    removed += 1
            except OSError as err:  # pragma: no cover - defensive
                _LOGGER.warning("Cannot delete %s: %s", path, err)
    return removed


def save_image(
    data: bytes,
    output_dir: str,
    filename: str,
    retention_mode: str = RETENTION_OVERWRITE,
    keep_count: int = 10,
    keep_days: int = 7,
    history_subdir: str | None = "history",
    metadata: dict | None = None,
) -> SaveResult:
    """Write ``data`` to ``output_dir/filename`` applying the retention policy.

    The "current" file always keeps the same name so dashboards / e-ink frames
    can point at a stable URL.  Previous versions are moved into the history
    directory with a timestamp suffix (unless the mode is ``overwrite``).
    """
    filename = sanitize_filename(filename)
    ensure_directory(output_dir)
    target = os.path.join(output_dir, filename)
    archived: str | None = None

    if retention_mode != RETENTION_OVERWRITE and os.path.exists(target):
        history_dir = _history_dir(output_dir, history_subdir)
        ensure_directory(history_dir)
        stamp = datetime.fromtimestamp(os.path.getmtime(target))
        archived = os.path.join(history_dir, _archive_name(filename, stamp))
        counter = 1
        while os.path.exists(archived):
            stem, ext = os.path.splitext(_archive_name(filename, stamp))
            archived = os.path.join(history_dir, f"{stem}_{counter}{ext}")
            counter += 1
        try:
            shutil.move(target, archived)
        except OSError as err:  # pragma: no cover - defensive
            _LOGGER.warning("Cannot archive %s: %s", target, err)
            archived = None

    tmp = f"{target}.tmp"
    with open(tmp, "wb") as handle:
        handle.write(data)
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(tmp, target)
    try:
        os.chmod(target, 0o644)
    except OSError:  # pragma: no cover - non POSIX / permissions
        pass

    if metadata is not None:
        meta_path = os.path.splitext(target)[0] + ".json"
        try:
            with open(meta_path, "w", encoding="utf-8") as handle:
                json.dump(metadata, handle, indent=2, ensure_ascii=False)
        except OSError as err:  # pragma: no cover - defensive
            _LOGGER.warning("Cannot write metadata %s: %s", meta_path, err)

    pruned = prune_history(
        output_dir, filename, history_subdir, retention_mode, keep_count, keep_days
    )
    history_count = len(
        _history_files(_history_dir(output_dir, history_subdir), filename)
    )
    return SaveResult(
        path=target, archived_path=archived, history_count=history_count, pruned=pruned
    )


def clear_history(
    output_dir: str, filename: str, history_subdir: str | None
) -> int:
    """Delete every archived copy of ``filename``. Returns how many were removed."""
    filename = sanitize_filename(filename)
    history_dir = _history_dir(output_dir, history_subdir)
    removed = 0
    for path in _history_files(history_dir, filename):
        try:
            os.remove(path)
            removed += 1
        except OSError as err:  # pragma: no cover - defensive
            _LOGGER.warning("Cannot delete %s: %s", path, err)
    return removed


def count_history(output_dir: str, filename: str, history_subdir: str | None) -> int:
    """Number of archived copies currently on disk."""
    return len(
        _history_files(_history_dir(output_dir, history_subdir), sanitize_filename(filename))
    )


def read_file(path: str) -> bytes | None:
    """Read a file, returning ``None`` when it does not exist."""
    try:
        with open(path, "rb") as handle:
            return handle.read()
    except OSError:
        return None
