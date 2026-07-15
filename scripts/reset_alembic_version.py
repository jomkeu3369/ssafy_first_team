import argparse
import os
import sys
from pathlib import Path

from alembic import command
from alembic.config import Config


PROJECT_ROOT = Path(__file__).resolve().parents[1]
ALEMBIC_INI = PROJECT_ROOT / "alembic.ini"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Reset the current database's Alembic revision to base.",
    )
    parser.add_argument(
        "--yes",
        action="store_true",
        help="Skip the interactive RESET confirmation.",
    )
    return parser.parse_args()


def confirm_reset() -> bool:
    answer = input(
        "DB 스키마는 변경하지 않고 Alembic 버전 기록만 초기화합니다. "
        "계속하려면 RESET을 입력하세요: "
    )
    return answer == "RESET"


def main() -> int:
    args = parse_args()
    if not args.yes and not confirm_reset():
        print("Alembic 버전 초기화를 취소했습니다.")
        return 1

    os.chdir(PROJECT_ROOT)
    sys.path.insert(0, str(PROJECT_ROOT))

    alembic_config = Config(str(ALEMBIC_INI))
    command.stamp(alembic_config, "base", purge=True)
    print("Alembic 버전 기록을 base 상태로 초기화했습니다.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
