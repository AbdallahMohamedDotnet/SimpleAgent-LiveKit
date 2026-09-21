"""Safe location and deletion of files under the application-owned data root."""

import asyncio
import os
from pathlib import Path, PurePosixPath


class OwnedPathError(ValueError):
    """Raised when a stored relative path does not resolve inside the owned data root."""


def resolve_owned_path(data_root: Path, relative_path: str) -> Path:
    """Join a stored relative path onto the owned root, rejecting traversal and symlinks.

    The caller has already authorized the record; this is the single authoritative check that the
    path the record carries still stays inside the directory the application owns.
    """
    pure = PurePosixPath(relative_path)
    if not relative_path or pure.is_absolute() or ".." in pure.parts:
        raise OwnedPathError("Path must be a non-empty owned relative path.")
    current = data_root
    for part in pure.parts:
        current = current / part
        if current.is_symlink():
            raise OwnedPathError("Owned paths may not traverse symbolic links.")
    return current


class LocalRecordingLocator:
    """Resolve an authorized recording segment to a readable regular file."""

    def __init__(self, recordings_root: Path) -> None:
        self._recordings_root = recordings_root.resolve()

    async def locate(self, relative_path: str) -> Path:
        """Return the owned file path, or raise ``OwnedPathError`` when it is unusable."""
        path = resolve_owned_path(self._recordings_root, relative_path)
        if not await asyncio.to_thread(path.is_file):
            raise OwnedPathError("The recording file is missing from the owned recording root.")
        return path


class LocalArtifactStore:
    def __init__(self, data_root: Path) -> None:
        self._data_root = data_root.resolve()

    async def delete(self, relative_paths: tuple[str, ...]) -> tuple[str, ...]:
        failures: list[str] = []
        for relative_path in relative_paths:
            try:
                path = resolve_owned_path(self._data_root, relative_path)
                await asyncio.to_thread(self._unlink_owned_file, path)
            except OSError, ValueError:
                failures.append(relative_path)
        return tuple(failures)

    def _unlink_owned_file(self, path: Path) -> None:
        try:
            mode = path.lstat().st_mode
        except FileNotFoundError:
            return
        if not os.path.isfile(path) or os.path.islink(path) or not mode:
            raise ValueError("Artifact path is not a regular owned file.")
        path.unlink()
        parent = path.parent
        while parent != self._data_root:
            try:
                parent.rmdir()
            except OSError:
                break
            parent = parent.parent
