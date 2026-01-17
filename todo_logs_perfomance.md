Claude, estou enfrentando **lentidão recorrente no sistema em produção**, principalmente no **painel administrativo**.  
Em diversos momentos, ao clicar em botões (salvar, atualizar JSON, carregar telas), o sistema demora para responder, fica carregando ou aparenta travar sem feedback claro.

Quero que você **instrumente o sistema com logs leves de performance**, focados em identificar **onde está a latência**, **somente quando eu ativar pelo front-end** e **apenas para o usuário admin**.

---

## Objetivo
- Diagnosticar gargalos reais de performance em produção
- Medir tempo de resposta por camada (rota, controller, service, BD, filesystem)
- Permitir que eu **ative/desative os logs pelo front**
- Registrar **exclusivamente ações do usuário admin**
- Depois da coleta, eu te darei acesso ao BD/logs para análise

---

## Requisitos gerais dos logs
- Logs **curtos, objetivos e estruturados**
- Cada log deve conter:
  - timestamp
  - usuário (apenas admin)
  - rota / ação
  - camada (middleware, controller, service, repository, DB, IO)
  - tempo gasto (ms)
- Não logar payloads grandes
- Não logar JSONs completos
- Nada de stacktrace salvo automaticamente
- Impacto mínimo de performance

---

## Ativação pelo Front-end (obrigatório)
- Criar um **toggle no painel admin**:
  - “Ativar logs de performance”
- O toggle deve:
  - Persistir estado (ex.: BD ou cache)
  - Ativar logs **somente para o usuário admin logado**
  - Poder ser desligado a qualquer momento
- Quando desligado:
  - Nenhum log de performance deve ser coletado

---

## Escopo de coleta
- Somente requisições originadas do **usuário admin**
- Somente enquanto o toggle estiver ativo
- Medir:
  - tempo total da request
  - tempo por etapa crítica:
    - entrada no middleware
    - controller
    - service
    - acesso ao BD
    - operações de filesystem
- Não medir usuários comuns

---

## Armazenamento dos logs
- Criar pasta dedicada: `/logs/performance`
- Persistir logs também no **BD de produção**
  - Tabela sugerida: `performance_logs`
- Campos mínimos:
  - id
  - created_at
  - admin_user_id
  - route
  - action
  - layer
  - duration_ms
- Garantir indexação por:
  - data
  - rota
  - admin_user_id
- Implementar limite/rotação:
  - Ex.: últimos X registros ou janela de X horas

---

## Script de diagnóstico ativo
- Criar um script que:
  - Simule navegação no painel admin
  - Acesse rotas críticas:
    - dashboard admin
    - categorias
    - perguntas/variáveis
    - gerar/atualizar JSON
  - Registre tempos usando o mesmo sistema de logs
- O script deve:
  - Respeitar o toggle de ativação
  - Poder rodar enquanto eu uso o sistema
  - Ser acionável manualmente

---

## TODO LIST (obrigatório)

### Front-end
- [ ] Criar toggle “Logs de performance (admin)”
- [ ] Persistir estado do toggle
- [ ] Garantir visibilidade clara de quando está ativo
- [ ] Garantir que apenas admin veja/controle

### Backend – Controle
- [ ] Verificar se usuário é admin
- [ ] Verificar se toggle está ativo
- [ ] Curto-circuitar qualquer log se não atender aos dois critérios

### Backend – Instrumentação
- [ ] Middleware de timing por request
- [ ] Instrumentar controllers do painel admin
- [ ] Instrumentar serviços críticos
- [ ] Instrumentar acessos ao BD
- [ ] Instrumentar IO/FS quando aplicável
- [ ] Medir e registrar duração em ms por camada

### Logs
- [ ] Criar pasta `/logs/performance`
- [ ] Criar tabela `performance_logs`
- [ ] Garantir logs pequenos e padronizados
- [ ] Implementar rotação/limite de volume

### Script de diagnóstico
- [ ] Criar script de navegação simulada (admin)
- [ ] Medir tempos por rota
- [ ] Persistir logs usando o mesmo pipeline
- [ ] Permitir execução manual

### Análise
- [ ] Documentar acesso aos logs no BD
- [ ] Preparar ambiente para análise posterior
- [ ] Após coleta, identificar gargalos reais antes de otimizar

---

## Diretriz final
Não otimizar no escuro.  
Primeiro **medir, logar e provar**.  
Só depois disso partir para cache, indexação ou refactor.

Implemente seguindo exatamente esta checklist.
