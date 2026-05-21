-- Run once in the Supabase SQL editor before ingestion.
-- Embedding dimension is 768 for jhgan/ko-sroberta-multitask.

create extension if not exists vector;

create table if not exists public.knowledge_base (
  id bigserial primary key,
  content text not null,
  content_hash text generated always as (md5(content)) stored,
  embedding vector(768) not null,
  metadata jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now()
);

create unique index if not exists knowledge_base_content_hash_uidx
  on public.knowledge_base (content_hash);

create index if not exists knowledge_base_embedding_hnsw_idx
  on public.knowledge_base
  using hnsw (embedding vector_cosine_ops);

create index if not exists knowledge_base_metadata_gin_idx
  on public.knowledge_base
  using gin (metadata);

create or replace function public.match_documents(
  query_embedding vector(768),
  match_count int default 5
)
returns table (
  id bigint,
  content text,
  metadata jsonb,
  similarity float
)
language sql
stable
as $$
  select
    knowledge_base.id,
    knowledge_base.content,
    knowledge_base.metadata,
    1 - (knowledge_base.embedding <=> query_embedding) as similarity
  from public.knowledge_base
  order by knowledge_base.embedding <=> query_embedding
  limit match_count;
$$;
