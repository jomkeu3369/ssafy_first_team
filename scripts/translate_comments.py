import argparse
import os
import time

import httpx


DEFAULT_BASE_URL = "https://ssafy-first-team.onrender.com"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Translate existing comments into Korean and English.")
    parser.add_argument("--base-url", default=DEFAULT_BASE_URL)
    parser.add_argument("--import-key", default=os.getenv("DATA_IMPORT_API_KEY"))
    parser.add_argument("--limit", type=int, choices=range(1, 101), default=100, metavar="1-100")
    return parser.parse_args()


def translate_comments(base_url: str, import_key: str, limit: int) -> int:
    endpoint = f"{base_url.rstrip('/')}/api/v1/admin/data-import/comment-translations"
    headers = {"X-Import-Key": import_key}
    total_translated = 0

    with httpx.Client(timeout=120) as client:
        while True:
            response = client.post(endpoint, headers=headers, params={"limit": limit})
            response.raise_for_status()
            result = response.json()
            translated_count = int(result["translatedCount"])
            remaining_count = int(result["remainingCount"])
            total_translated += translated_count
            print(f"Translated: {translated_count} / Remaining: {remaining_count} / Total: {total_translated}")

            if remaining_count == 0:
                return total_translated
            if translated_count == 0:
                raise RuntimeError("No progress was made. Check the server logs and OpenAI API configuration.")
            time.sleep(1)


def main() -> None:
    args = parse_args()
    if not args.import_key:
        raise SystemExit("X-Import-Key is required. Pass --import-key or set DATA_IMPORT_API_KEY.")
    try:
        total = translate_comments(args.base_url, args.import_key, args.limit)
    except httpx.HTTPStatusError as exc:
        detail = exc.response.text.strip()
        raise SystemExit(f"Request failed with HTTP {exc.response.status_code}: {detail}") from exc
    except httpx.HTTPError as exc:
        raise SystemExit(f"Request failed: {exc}") from exc
    print(f"Comment translation completed. Total: {total}")


if __name__ == "__main__":
    main()
