from __future__ import annotations

from pathlib import Path
import sys

try:
    ROOT = Path(__file__).resolve().parent.parent  # ops/ -> project root
except NameError:
    ROOT = Path.cwd()
SRC = ROOT / "src"

if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from runtime import watchdog  # noqa: E402


def main() -> int:
    watchdog.run_once()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
