from __future__ import annotations

import sys

from cogsol.core.management import execute_from_command_line


def main() -> int:
    return execute_from_command_line(sys.argv)


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
