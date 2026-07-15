#!/usr/bin/env bash

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$PROJECT_ROOT" || exit 1

if [[ "${1:-}" == "--help" ]]; then
    echo "Usage: bash scripts/manage_db.sh"
    echo
    echo "Opens an interactive menu for Alembic revision, upgrade, status,"
    echo "stamp, and revision reset operations."
    exit 0
fi

wait_for_key() {
    echo
    read -r -n 1 -s -p "계속하려면 아무 키나 누르세요..."
    echo
}

while true; do
    clear
    echo "=========================================="
    echo "    Busan LocalHub 데이터베이스 관리 도구"
    echo "=========================================="
    echo "1. 마이그레이션 파일 생성"
    echo "2. DB 스키마 최신화 (upgrade head)"
    echo "3. 현재 DB 버전 및 이력 확인"
    echo "4. DB 버전을 최신으로 표시 (stamp head)"
    echo "5. Alembic 버전 기록 초기화 (stamp base)"
    echo "6. 종료"
    echo "=========================================="
    read -r -p "원하는 작업 번호를 입력하세요: " choice

    case "$choice" in
        1)
            read -r -p "마이그레이션 메시지를 입력하세요: " message
            if [[ -z "$message" ]]; then
                echo "메시지가 비어 있어 작업을 취소합니다."
            else
                uv run alembic revision --autogenerate -m "$message"
            fi
            wait_for_key
            ;;
        2)
            uv run alembic upgrade head
            wait_for_key
            ;;
        3)
            echo "[현재 DB 버전]"
            uv run alembic current
            echo
            echo "[마이그레이션 이력]"
            uv run alembic history
            wait_for_key
            ;;
        4)
            echo "[경고] DB 스키마를 변경하지 않고 버전 기록만 head로 설정합니다."
            read -r -p "계속하시겠습니까? (y/N): " confirm
            if [[ "$confirm" =~ ^[yY]$ ]]; then
                uv run alembic stamp head
            else
                echo "작업을 취소했습니다."
            fi
            wait_for_key
            ;;
        5)
            echo "[경고] DB 스키마를 변경하지 않고 Alembic 버전 기록을 초기화합니다."
            uv run python scripts/reset_alembic_version.py
            wait_for_key
            ;;
        6)
            echo "도구를 종료합니다."
            exit 0
            ;;
        *)
            echo "잘못된 입력입니다."
            sleep 1
            ;;
    esac
done
