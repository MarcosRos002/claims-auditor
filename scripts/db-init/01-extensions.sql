-- Veritas: enable pgvector on first DB boot. Hybrid RAG also uses Postgres
-- full-text search (built in). Schema/migrations are added in a later phase.
CREATE EXTENSION IF NOT EXISTS vector;
