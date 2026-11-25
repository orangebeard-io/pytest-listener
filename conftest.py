import os
from pathlib import Path

pytest_plugins = ["pytester"]


def _load_dotenv(path: Path) -> None:
    """Minimal .env loader (KEY=VALUE lines); real environment variables win. Empty values are ignored."""
    if not path.is_file():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        value = value.strip().strip('"').strip("'")
        if value:
            os.environ.setdefault(key.strip(), value)


# conftest.py is imported before the plugin configures itself, so ORANGEBEARD_TOKEN is in place in time
_load_dotenv(Path(__file__).parent / ".env")
