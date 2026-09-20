"""Safe deletion under the application-owned data root."""

import asyncio
import os
from pathlib import Path, PurePosixPath


class LocalArtifactStore:
    def __init__(self, data_root: Path) -> None:
        self._data_root = data_root.resolve()

    async def delete(self, relative_paths: tuple[str, ...]) -> tuple[str, ...]:
        failures: list[str] = []
        for relative_path in relative_paths:
            try:
                path = self._validate(relative_path)
                await asyncio.to_thread(self._unlink_owned_file, path)
            except OSError, ValueError:
                failures.append(relative_path)
        return tuple(failures)

    def _validate(self, relative_path: str) -> Path:
        pure = PurePosixPath(relative_path)
        if pure.is_absolute() or not relative_path or ".." in pure.parts:
            raise ValueError("Artifact path must be a non-empty owned relative path.")
        candidate = self._data_root.joinpath(*pure.parts)
        current = self._data_root
        for part in pure.parts:
            current = current / part
            if current.is_symlink():
                raise ValueError("Artifact paths may not traverse symbolic links.")
        return candidate

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
