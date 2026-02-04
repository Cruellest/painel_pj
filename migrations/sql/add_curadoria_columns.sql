-- ============================================================
-- MIGRAÇÃO: Adicionar colunas de curadoria em geracoes_pecas
-- Data: 2026-02-02
-- Executar em PRODUÇÃO antes do deploy
-- ============================================================

-- Adiciona coluna modo_ativacao_agente2 (se não existir)
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'geracoes_pecas' AND column_name = 'modo_ativacao_agente2'
    ) THEN
        ALTER TABLE geracoes_pecas ADD COLUMN modo_ativacao_agente2 VARCHAR(30);
        RAISE NOTICE 'Coluna modo_ativacao_agente2 adicionada';
    ELSE
        RAISE NOTICE 'Coluna modo_ativacao_agente2 já existe';
    END IF;
END $$;

-- Adiciona coluna modulos_ativados_det (se não existir)
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'geracoes_pecas' AND column_name = 'modulos_ativados_det'
    ) THEN
        ALTER TABLE geracoes_pecas ADD COLUMN modulos_ativados_det INTEGER;
        RAISE NOTICE 'Coluna modulos_ativados_det adicionada';
    ELSE
        RAISE NOTICE 'Coluna modulos_ativados_det já existe';
    END IF;
END $$;

-- Adiciona coluna modulos_ativados_llm (se não existir)
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'geracoes_pecas' AND column_name = 'modulos_ativados_llm'
    ) THEN
        ALTER TABLE geracoes_pecas ADD COLUMN modulos_ativados_llm INTEGER;
        RAISE NOTICE 'Coluna modulos_ativados_llm adicionada';
    ELSE
        RAISE NOTICE 'Coluna modulos_ativados_llm já existe';
    END IF;
END $$;

-- Adiciona coluna curadoria_metadata (se não existir)
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'geracoes_pecas' AND column_name = 'curadoria_metadata'
    ) THEN
        ALTER TABLE geracoes_pecas ADD COLUMN curadoria_metadata JSONB;
        RAISE NOTICE 'Coluna curadoria_metadata adicionada';
    ELSE
        RAISE NOTICE 'Coluna curadoria_metadata já existe';
    END IF;
END $$;

-- Cria índice para busca por modo de ativação (se não existir)
CREATE INDEX IF NOT EXISTS ix_geracoes_pecas_modo_ativacao ON geracoes_pecas(modo_ativacao_agente2);

-- Verifica resultado
SELECT column_name, data_type
FROM information_schema.columns
WHERE table_name = 'geracoes_pecas'
AND column_name IN ('modo_ativacao_agente2', 'modulos_ativados_det', 'modulos_ativados_llm', 'curadoria_metadata')
ORDER BY column_name;
