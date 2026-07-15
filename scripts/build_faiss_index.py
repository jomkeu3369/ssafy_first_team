from __future__ import annotations

import argparse
import json
from pathlib import Path

import faiss
import numpy as np
from langchain_openai import OpenAIEmbeddings

from src.core.config import PROJECT_ROOT, get_settings


DEFAULT_SOURCE = PROJECT_ROOT / "data" / "faiss_documents.jsonl"


def load_documents(source: Path) -> list[dict]:
    documents = []
    with source.open(encoding="utf-8") as file:
        for line_number, line in enumerate(file, start=1):
            if not line.strip():
                continue
            item = json.loads(line)
            content = str(item.pop("content", "")).strip()
            if not content:
                raise ValueError(f"Missing content at line {line_number}")
            documents.append({"content": content, "metadata": item})
    return documents


def main() -> None:
    parser = argparse.ArgumentParser(description="Build the LocalHub FAISS index")
    parser.add_argument("--source", type=Path, default=DEFAULT_SOURCE)
    args = parser.parse_args()
    settings = get_settings()
    if not settings.openai_api_key:
        raise RuntimeError("OPENAI_API_KEY is required to create embeddings")
    if not args.source.exists():
        raise FileNotFoundError(
            f"Source not found: {args.source}. Create a UTF-8 JSONL file first."
        )

    documents = load_documents(args.source)
    if not documents:
        raise ValueError("No documents were found in the source file")
    embeddings = OpenAIEmbeddings(
        model=settings.openai_embedding_model,
        api_key=settings.openai_api_key,
    )
    vectors = np.asarray(
        embeddings.embed_documents([item["content"] for item in documents]),
        dtype="float32",
    )
    faiss.normalize_L2(vectors)
    index = faiss.IndexFlatIP(vectors.shape[1])
    index.add(vectors)
    settings.faiss_index_dir.mkdir(parents=True, exist_ok=True)
    faiss.write_index(index, str(settings.faiss_index_dir / "index.faiss"))
    with (settings.faiss_index_dir / "documents.json").open(
        "w", encoding="utf-8"
    ) as file:
        json.dump(documents, file, ensure_ascii=False)
    print(f"Indexed {len(documents)} documents into {settings.faiss_index_dir}")


if __name__ == "__main__":
    main()
