from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Iterable

import pandas as pd

from .config import PROJECT_ROOT, SETTINGS


DATA_ROOT = SETTINGS.legacy_rag_dir
DEFAULT_FOLDERS = (
    DATA_ROOT / "data",
    DATA_ROOT / "data_csv",
    DATA_ROOT / "data_plus",
    DATA_ROOT / "data_except",
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Ingest SilverSynk RAG files into Supabase.")
    parser.add_argument("--reset", action="store_true", help="Delete existing knowledge_base rows first.")
    parser.add_argument("--dry-run", action="store_true", help="Scan files without uploading.")
    parser.add_argument("--csv-limit", type=int, default=SETTINGS.ingest_csv_limit)
    parser.add_argument("--batch-size", type=int, default=50)
    parser.add_argument(
        "--include-except",
        action="store_true",
        help="Deprecated: data_except is now included by default.",
    )
    parser.add_argument("--exclude-except", action="store_true", help="Skip data_except ingestion.")
    parser.add_argument("--folder", action="append", help="Additional folder to ingest.")
    return parser


def main() -> None:
    args = build_parser().parse_args()
    supabase = None if args.dry_run else create_supabase_client()
    embeddings = None if args.dry_run else create_embeddings()

    folders = list(DEFAULT_FOLDERS)
    if args.exclude_except:
        folders = [folder for folder in folders if folder.name != "data_except"]
    if args.folder:
        folders.extend(Path(folder) for folder in args.folder)
    folders = unique_paths(folders)

    print("=" * 70)
    print("Supabase RAG ingestion")
    print(f"Project root: {PROJECT_ROOT}")
    print(f"RAG source:   {DATA_ROOT}")
    print(f"Table:        {SETTINGS.supabase_table}")
    print(f"Dry run:      {args.dry_run}")
    print("=" * 70)

    if args.reset and not args.dry_run:
        reset_table(supabase)

    total = 0
    for folder in folders:
        total += ingest_folder(
            folder=folder,
            supabase=supabase,
            embeddings=embeddings,
            dry_run=args.dry_run,
            csv_limit=args.csv_limit,
            batch_size=args.batch_size,
        )

    print("=" * 70)
    print(f"Done. Prepared/uploaded rows: {total}")
    print("=" * 70)


def create_supabase_client():
    if not SETTINGS.supabase_url or not SETTINGS.supabase_key:
        raise RuntimeError("SUPABASE_URL and SUPABASE_KEY must be set.")
    from supabase import create_client

    return create_client(SETTINGS.supabase_url, SETTINGS.supabase_key)


def create_embeddings():
    from langchain_huggingface import HuggingFaceEmbeddings

    return HuggingFaceEmbeddings(model_name=SETTINGS.embedding_model)


def reset_table(supabase) -> None:
    print("Deleting existing knowledge_base rows...")
    while True:
        response = supabase.table(SETTINGS.supabase_table).select("id").limit(500).execute()
        rows = response.data or []
        if not rows:
            break
        for row in rows:
            supabase.table(SETTINGS.supabase_table).delete().eq("id", row["id"]).execute()
        print(f"  deleted {len(rows)} rows")


def ingest_folder(
    folder: Path,
    supabase,
    embeddings,
    dry_run: bool,
    csv_limit: int,
    batch_size: int,
) -> int:
    if not folder.exists():
        print(f"Skip missing folder: {folder}")
        return 0

    count = 0
    print(f"\nFolder: {folder}")
    for path in sorted(folder.iterdir()):
        if dry_run:
            if path.suffix.lower() not in {".pdf", ".csv", ".json"}:
                continue
            row_count = count_file_rows(path, csv_limit=csv_limit)
            print(f"  {path.name}: {row_count} rows")
            count += row_count
            continue

        if path.suffix.lower() == ".pdf":
            if embeddings is None:
                raise RuntimeError("embeddings must be initialized outside dry-run.")
            rows = list(pdf_rows(path, embeddings))
        elif path.suffix.lower() == ".csv":
            if embeddings is None:
                raise RuntimeError("embeddings must be initialized outside dry-run.")
            rows = list(csv_rows(path, embeddings, limit=csv_limit))
        elif path.suffix.lower() == ".json":
            if embeddings is None:
                raise RuntimeError("embeddings must be initialized outside dry-run.")
            rows = list(json_rows(path, embeddings))
        else:
            continue

        count += len(rows)
        print(f"  {path.name}: {len(rows)} rows")
        upload_rows(supabase, rows, batch_size=batch_size)
    return count


def unique_paths(paths: Iterable[Path]) -> list[Path]:
    seen: set[str] = set()
    unique: list[Path] = []
    for path in paths:
        key = str(path.resolve())
        if key not in seen:
            seen.add(key)
            unique.append(path)
    return unique


def count_file_rows(path: Path, csv_limit: int) -> int:
    try:
        if path.suffix.lower() == ".pdf":
            from langchain_text_splitters import RecursiveCharacterTextSplitter

            splitter = RecursiveCharacterTextSplitter(chunk_size=800, chunk_overlap=100)
            return len(splitter.split_documents(load_pdf_documents(path)))
        if path.suffix.lower() == ".csv":
            row_count = len(read_csv(path))
            return min(row_count, csv_limit) if csv_limit > 0 else row_count
        if path.suffix.lower() == ".json":
            data = json.loads(path.read_text(encoding="utf-8"))
            return len(data) if isinstance(data, list) else 1
    except Exception as exc:
        print(f"  {path.name}: dry-run count failed ({exc})")
    return 0


def pdf_rows(path: Path, embeddings) -> Iterable[dict]:
    from langchain_text_splitters import RecursiveCharacterTextSplitter

    splitter = RecursiveCharacterTextSplitter(chunk_size=800, chunk_overlap=100)
    pages = load_pdf_documents(path)
    chunks = splitter.split_documents(pages)
    for chunk in chunks:
        content = clean_text(chunk.page_content)
        if content:
            yield payload(content, embeddings, {**chunk.metadata, **source_metadata(path, "pdf")})


def load_pdf_documents(path: Path):
    errors: list[str] = []
    for loader_name in ("PyMuPDFLoader", "PyPDFLoader"):
        try:
            if loader_name == "PyMuPDFLoader":
                from langchain_community.document_loaders import PyMuPDFLoader

                pages = PyMuPDFLoader(str(path)).load()
            else:
                from langchain_community.document_loaders import PyPDFLoader

                pages = PyPDFLoader(str(path)).load()
            if pages and any(page.page_content.strip() for page in pages):
                return pages
        except Exception as exc:
            errors.append(f"{loader_name}: {exc}")
    if errors:
        print(f"  {path.name}: PDF extraction failed ({' | '.join(errors)})")
    return []


def csv_rows(path: Path, embeddings, limit: int) -> Iterable[dict]:
    df = read_csv(path)
    if limit > 0:
        df = df.head(limit)
    for index, row in df.iterrows():
        content = " | ".join(f"{col}: {value}" for col, value in row.items() if pd.notna(value))
        content = clean_text(content)
        if content:
            yield payload(content, embeddings, {**source_metadata(path, "csv"), "row": int(index) + 1})


def json_rows(path: Path, embeddings) -> Iterable[dict]:
    data = json.loads(path.read_text(encoding="utf-8"))
    items = data if isinstance(data, list) else [data]
    for index, item in enumerate(items, 1):
        content = json.dumps(item, ensure_ascii=False) if isinstance(item, (dict, list)) else str(item)
        content = clean_text(content)
        if content:
            yield payload(content, embeddings, {**source_metadata(path, "json"), "row": index})


def read_csv(path: Path) -> pd.DataFrame:
    for encoding in ("utf-8", "cp949", "euc-kr"):
        try:
            return pd.read_csv(path, encoding=encoding, low_memory=False)
        except UnicodeDecodeError:
            continue
    return pd.read_csv(path, low_memory=False)


def source_metadata(path: Path, file_type: str) -> dict:
    try:
        source_path = path.relative_to(DATA_ROOT).as_posix()
    except ValueError:
        source_path = path.name
    return {
        "source": path.name,
        "source_folder": path.parent.name,
        "source_path": source_path,
        "file_type": file_type,
    }


def payload(content: str, embeddings, metadata: dict) -> dict:
    return {
        "content": content,
        "embedding": embeddings.embed_query(content),
        "metadata": metadata,
    }


def upload_rows(supabase, rows: list[dict], batch_size: int) -> None:
    for start in range(0, len(rows), batch_size):
        batch = rows[start : start + batch_size]
        upload_batch(supabase, batch)


def upload_batch(supabase, batch: list[dict]) -> None:
    # 한 배치(batch) 내의 중복 데이터(동일한 텍스트)를 미리 제거하여 Postgres 에러 방지
    seen_contents = set()
    unique_batch = []
    for row in batch:
        if row["content"] not in seen_contents:
            seen_contents.add(row["content"])
            unique_batch.append(row)
    batch = unique_batch

    conflicts = list(dict.fromkeys([
        SETTINGS.supabase_upsert_conflict,
        "knowledge_base_content_hash_uidx",  # DB의 고유 제약 조건 이름을 명시적으로 추가
        "content_hash",
        "content"
    ]))
    last_error: Exception | None = None
    for conflict in conflicts:
        try:
            supabase.table(SETTINGS.supabase_table).upsert(batch, on_conflict=conflict).execute()
            return
        except Exception as exc:
            last_error = exc
    try:
        supabase.table(SETTINGS.supabase_table).insert(batch).execute()
    except Exception as exc:
        raise RuntimeError(f"Supabase upload failed. Last upsert error: {last_error}") from exc


def clean_text(text: str | None) -> str:
    if not text:
        return ""
    return text.replace("\x00", "").strip()


if __name__ == "__main__":
    main()
