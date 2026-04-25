# ingest.py — SentenceTransformer embeddings + Chroma (PersistentClient)
# Debug-friendly + safe ingest
import os
print("RUNNING FILE =", os.path.abspath(__file__))

import os
import glob
import uuid
from typing import List, Tuple, Dict, Any

import chromadb
from dotenv import load_dotenv
from sentence_transformers import SentenceTransformer


# ========= Paths & config =========
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, "data")          # nơi đặt .txt
DB_DIR = os.path.join(BASE_DIR, "vectordb")        # nơi lưu vectordb

load_dotenv(os.path.join(BASE_DIR, ".env"))
COLLECTION_NAME = os.getenv("COLLECTION_NAME", "knowledge_base")

# Chunking
CHUNK_SIZE = 800
CHUNK_OVERLAP = 120
BATCH_SIZE = 64

# Nếu muốn xoá sạch collection trước khi ingest: set = "1"
RESET_COLLECTION = os.getenv("RESET_COLLECTION", "0").strip() == "1"


def read_all_texts() -> List[Tuple[str, str]]:
    """Đọc toàn bộ .txt trong thư mục data/ (đệ quy). Bỏ qua file rỗng."""
    pattern = os.path.join(DATA_DIR, "**", "*.txt")
    paths = sorted(glob.glob(pattern, recursive=True))

    print(f"[ingest] TXT pattern: {pattern}")
    print(f"[ingest] Found {len(paths)} .txt files")

    texts: List[Tuple[str, str]] = []
    for p in paths:
        try:
            with open(p, "r", encoding="utf-8", errors="ignore") as f:
                content = f.read().strip()
            if not content:
                print(f"[ingest] Skip empty file: {os.path.relpath(p, BASE_DIR)}")
                continue
            texts.append((p, content))
        except Exception as e:
            print(f"⚠️  Không đọc được file: {p} | Lỗi: {repr(e)}")

    return texts


def chunk_text(text: str, size: int = CHUNK_SIZE, overlap: int = CHUNK_OVERLAP) -> List[str]:
    """Cắt văn bản thành các đoạn chồng lấn để truy hồi tốt hơn."""
    text = " ".join(text.split())
    if not text:
        return []
    chunks: List[str] = []

    step = max(1, size - overlap)
    start = 0
    n = len(text)

    while start < n:
        end = min(start + size, n)
        ch = text[start:end].strip()
        if ch:
            chunks.append(ch)
        start += step

    return chunks


def main():
    # === In config để khỏi chạy nhầm thư mục ===
    print("========== INGEST CONFIG ==========")
    print("BASE_DIR        =", BASE_DIR)
    print("DATA_DIR        =", DATA_DIR)
    print("DB_DIR          =", DB_DIR)
    print("COLLECTION_NAME =", COLLECTION_NAME)
    print("RESET_COLLECTION=", RESET_COLLECTION)
    print("===================================")

    os.makedirs(DB_DIR, exist_ok=True)

    # === Model ===
    model = SentenceTransformer("intfloat/multilingual-e5-small")

    # === Chroma persistent client ===
    client = chromadb.PersistentClient(path=DB_DIR)

    # (Tuỳ chọn) reset collection để test lại cho sạch
    if RESET_COLLECTION:
        try:
            client.delete_collection(COLLECTION_NAME)
            print(f"[ingest] Deleted collection '{COLLECTION_NAME}'")
        except Exception:
            pass

    coll = client.get_or_create_collection(COLLECTION_NAME)
    print("[ingest] Collection count BEFORE =", coll.count())

    docs = read_all_texts()
    if not docs:
        print(f"⚠️  Không có file .txt (hoặc toàn file rỗng) trong: {DATA_DIR}")
        return

    ids: List[str] = []
    metas: List[Dict[str, Any]] = []
    contents: List[str] = []

    total_chunks = 0
    for path, fulltext in docs:
        chunks = chunk_text(fulltext)
        rel = os.path.relpath(path, BASE_DIR)
        if not chunks:
            print(f"[ingest] Skip no-chunk file: {rel}")
            continue

        for ch in chunks:
            ids.append(str(uuid.uuid4()))
            contents.append(ch)
            metas.append({"source": rel})
        total_chunks += len(chunks)

    if not contents:
        print("⚠️  Không tạo được chunk nào để ingest (toàn rỗng).")
        return

    print(f"[ingest] Prepared {len(contents)} chunks from {len(docs)} files")

    # === Encode theo batch ===
    embeddings: List[list] = []
    for i in range(0, len(contents), BATCH_SIZE):
        batch = contents[i: i + BATCH_SIZE]
        vec = model.encode(
            batch,
            convert_to_numpy=True,
            normalize_embeddings=True,
            batch_size=min(BATCH_SIZE, len(batch)),
            show_progress_bar=False,
        )
        # Chuyển sang list để Chroma ăn chắc (tránh dtype/numpy issues)
        embeddings.extend(vec.tolist())

        if (i // BATCH_SIZE) % 10 == 0:
            print(f"[ingest] Encoded {min(i + BATCH_SIZE, len(contents))}/{len(contents)}")

    # === Add vào collection ===
    try:
        coll.add(ids=ids, metadatas=metas, documents=contents, embeddings=embeddings)
    except Exception as e:
        print("❌ coll.add failed:", repr(e))
        raise

    print("[ingest] Collection count AFTER  =", coll.count())

    print(
        f"✅ Ingested {len(contents)} chunks từ {len(docs)} file "
        f"vào collection '{COLLECTION_NAME}' tại '{DB_DIR}'."
    )


if __name__ == "__main__":
    main()
