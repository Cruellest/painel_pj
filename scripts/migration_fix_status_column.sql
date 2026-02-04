-- Migration: Fix status column size in geracoes_prestacao_contas
-- Issue: 'aguardando_documentos' (21 chars) and 'aguardando_nota_fiscal' (22 chars) exceed VARCHAR(20)
-- Solution: Increase column size to VARCHAR(30)
-- Date: 2026-01-19

-- Execute this in production PostgreSQL database:

ALTER TABLE geracoes_prestacao_contas
ALTER COLUMN status TYPE VARCHAR(30);

-- Verify the change:
-- SELECT column_name, data_type, character_maximum_length
-- FROM information_schema.columns
-- WHERE table_name = 'geracoes_prestacao_contas' AND column_name = 'status';
