"""Index project documentation into Chroma for architect agent RAG.

Indexes all markdown files from docs/ and tasks/ into a persistent Chroma
collection named 'platform-knowledge'. Run after adding or updating any
documentation or task briefs.

Usage:
    uv run python scripts/ingest_docs.py
    just ingest

The collection is created if it does not exist. Existing documents are
upserted — running this script multiple times is safe and idempotent.
Document IDs are derived from file path and chunk index, so moving or
renaming a file will create new chunks and leave orphaned old ones. Run
with --reset to wipe and rebuild the collection from scratch.
"""

import argparse
import hashlib
from pathlib import Path

import chromadb
from chromadb.utils import embedding_functions


CHROMA_DATA_DIR = Path("data/chroma")
COLLECTION_NAME = "platform-knowledge"
CHUNK_SIZE = 800        # characters per chunk
CHUNK_OVERLAP = 100     # overlap between chunks

SOURCE_DIRS = [
    Path("docs"),
    Path("tasks"),
    Path("clusters"),
]

SOURCE_EXTENSIONS = {".md"}


def chunk_text(text: str, size: int, overlap: int) -> list[str]:
    """Split text into overlapping chunks."""
    chunks = []
    start = 0
    while start < len(text):
        end = min(start + size, len(text))
        chunks.append(text[start:end])
        if end == len(text):
            break
        start += size - overlap
    return chunks


def doc_id(path: Path, chunk_index: int) -> str:
    """Stable document ID from file path and chunk index."""
    key = f"{path}::{chunk_index}"
    return hashlib.md5(key.encode()).hexdigest()


def collect_files() -> list[Path]:
    """Find all markdown files in source directories."""
    files = []
    for source_dir in SOURCE_DIRS:
        if not source_dir.exists():
            print(f"  Skipping {source_dir}/ — directory not found")
            continue
        for ext in SOURCE_EXTENSIONS:
            files.extend(sorted(source_dir.rglob(f"*{ext}")))
    return files


def ingest(reset: bool = False) -> None:
    """Ingest all source documents into Chroma."""
    CHROMA_DATA_DIR.mkdir(parents=True, exist_ok=True)

    client = chromadb.PersistentClient(path=str(CHROMA_DATA_DIR))

    # Use default embedding function (sentence-transformers, no API key needed)
    ef = embedding_functions.DefaultEmbeddingFunction()

    if reset:
        try:
            client.delete_collection(COLLECTION_NAME)
            print(f"Deleted existing collection '{COLLECTION_NAME}'")
        except Exception:
            pass

    collection = client.get_or_create_collection(
        name=COLLECTION_NAME,
        embedding_function=ef,
        metadata={"hnsw:space": "cosine"},
    )

    files = collect_files()
    if not files:
        print("No source files found.")
        return

    total_chunks = 0

    for path in files:
        try:
            text = path.read_text(encoding="utf-8")
        except Exception as e:
            print(f"  Skipping {path} — {e}")
            continue

        chunks = chunk_text(text, CHUNK_SIZE, CHUNK_OVERLAP)

        ids = [doc_id(path, i) for i in range(len(chunks))]
        metadatas = [
            {
                "source": str(path),
                "filename": path.name,
                "directory": str(path.parent),
                "chunk_index": i,
                "total_chunks": len(chunks),
            }
            for i in range(len(chunks))
        ]

        collection.upsert(
            ids=ids,
            documents=chunks,
            metadatas=metadatas,
        )

        total_chunks += len(chunks)
        print(f"  {path} — {len(chunks)} chunk(s)")

    print(f"\nDone. {len(files)} files, {total_chunks} chunks total.")
    print(f"Collection: '{COLLECTION_NAME}' in {CHROMA_DATA_DIR}/")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--reset",
        action="store_true",
        help="Delete and rebuild the collection from scratch.",
    )
    args = parser.parse_args()
    ingest(reset=args.reset)