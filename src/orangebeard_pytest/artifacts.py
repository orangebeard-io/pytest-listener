"""Find files (screenshots, traces, videos...) that a test produced in watched directories."""
import os
from pathlib import Path
from typing import Dict, List, Tuple

Snapshot = Dict[Path, Tuple[int, int]]


class DirectoryWatcher:
    def __init__(self, root: Path):
        self.root = Path(root)

    def snapshot(self) -> Snapshot:
        found: Snapshot = {}
        if not self.root.is_dir():
            return found
        for folder, _, files in os.walk(self.root):
            for name in files:
                path = Path(folder) / name
                try:
                    stat = path.stat()
                except OSError:
                    continue
                found[path] = (stat.st_mtime_ns, stat.st_size)
        return found

    def new_files(self, before: Snapshot) -> List[Path]:
        """Files that are new or modified since `before` was taken."""
        return sorted(path for path, signature in self.snapshot().items() if before.get(path) != signature)


def describe(path: Path) -> str:
    """Human friendly label for an artifact; Playwright files are recognisable."""
    name = Path(path).name
    suffix = Path(path).suffix.lower()
    if name == 'trace.zip':
        return f'{name} (Playwright trace; view with: playwright show-trace {name})'
    if suffix in ('.webm', '.mp4'):
        return f'Video recording: {name}'
    if suffix in ('.png', '.jpg', '.jpeg') and name.startswith('test-'):
        return f'Screenshot: {name}'
    return name
