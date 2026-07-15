from __future__ import annotations

import argparse
import asyncio

from src.mcp_servers.faiss_store import ensure_vector_store


async def build(force: bool) -> None:
    bundle = await ensure_vector_store(force=force)
    action = "Rebuilt" if bundle.rebuilt else "Reused"
    print(f"{action} {len(bundle.documents)} documents with fingerprint {bundle.fingerprint[:12]}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Build the LocalHub FAISS index from Board and post data")
    parser.add_argument("--force", action="store_true", help="Recreate the index even when the DB fingerprint is unchanged")
    args = parser.parse_args()
    asyncio.run(build(args.force))


if __name__ == "__main__":
    main()
