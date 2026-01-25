# Rotacao de Secrets - Portal PGE-MS

Documento tecnico para rotacao segura de chaves e senhas do sistema.

## 1. Inventario de Secrets

### Secrets Criticos (Rotacao Obrigatoria)

| Secret | Variavel | Impacto | Frequencia Rotacao |
|--------|----------|---------|-------------------|
| JWT Secret Key | `SECRET_KEY` | Alto - Invalida todos os tokens | Anual ou em incidente |
| Admin Password | `ADMIN_PASSWORD` | Alto - Acesso administrativo | Trimestral |
| DB Password | `DATABASE_URL` | Alto - Acesso ao banco | Semestral |

### Secrets de API (Rotacao Recomendada)

| Secret | Variavel | Impacto | Frequencia Rotacao |
|--------|----------|---------|-------------------|
| Gemini API Key | `GEMINI_KEY` | Medio - Afeta IA | Semestral ou em vazamento |
| OpenRouter API Key | `OPENROUTER_API_KEY` | Medio - Afeta IA | Semestral ou em vazamento |
| TJ-MS Credentials | `TJMS_SOAP_USER/PASS` | Medio - Afeta integracao | Conforme politica TJ |

## 2. Procedimentos de Rotacao

### 2.1 SECRET_KEY (JWT)

**IMPACTO**: Todos os usuarios serao deslogados.

**Passo a passo**:

1. Gere nova chave segura:
   ```bash
   python -c "import secrets; print(secrets.token_urlsafe(64))"
   ```

2. Atualize no ambiente de producao:
   ```bash
   # Kubernetes
   kubectl create secret generic portal-secrets \
     --from-literal=SECRET_KEY=<nova_chave> \
     --dry-run=client -o yaml | kubectl apply -f -

   # Docker Compose
   # Edite .env.production e atualize SECRET_KEY
   ```

3. Reinicie os pods/containers:
   ```bash
   kubectl rollout restart deployment/portal-pge
   # ou
   docker-compose restart
   ```

4. Verifique os logs:
   ```bash
   kubectl logs -f deployment/portal-pge --tail=50
   ```

5. Comunique usuarios sobre necessidade de novo login.

### 2.2 ADMIN_PASSWORD

**IMPACTO**: Apenas conta admin afetada.

**Passo a passo**:

1. Gere nova senha forte (min 12 chars, maiusculas, minusculas, numeros, simbolos).

2. Atualize no ambiente:
   ```bash
   kubectl set secret generic portal-secrets \
     --from-literal=ADMIN_PASSWORD=<nova_senha>
   ```

3. Reinicie a aplicacao.

4. Teste login com nova senha.

5. Revogue sessoes antigas (se aplicavel):
   ```bash
   # Via API admin
   curl -X POST https://portal.pge.ms.gov.br/api/admin/revoke-sessions \
     -H "Authorization: Bearer $TOKEN"
   ```

### 2.3 DATABASE_URL

**IMPACTO**: Alto - requer coordenacao com DBA.

**Passo a passo**:

1. Coordene com DBA para criar novo usuario ou alterar senha.

2. Teste conectividade antes de atualizar producao:
   ```bash
   psql "postgresql://novo_usuario:nova_senha@host:5432/db" -c "SELECT 1"
   ```

3. Atualize secrets no ambiente.

4. Reinicie aplicacao com rolling update (zero downtime):
   ```bash
   kubectl rollout restart deployment/portal-pge
   ```

5. Verifique health checks:
   ```bash
   curl https://portal.pge.ms.gov.br/health/detailed
   ```

### 2.4 API Keys Externas (Gemini, OpenRouter)

**IMPACTO**: Medio - funcionalidades de IA afetadas.

**Passo a passo**:

1. Gere nova API key no console do provedor.

2. Teste nova chave localmente:
   ```python
   import google.generativeai as genai
   genai.configure(api_key="nova_chave")
   # Teste simples
   model = genai.GenerativeModel('gemini-pro')
   response = model.generate_content("teste")
   ```

3. Atualize secrets no ambiente.

4. Reinicie aplicacao.

5. Verifique logs de chamadas a IA.

6. Revogue chave antiga no console do provedor.

## 3. Checklist de Rotacao

- [ ] Backup do secret atual (seguro, criptografado)
- [ ] Geracao de novo secret conforme politica
- [ ] Teste do novo secret em ambiente de staging
- [ ] Atualizacao do secret em producao
- [ ] Restart da aplicacao com rolling update
- [ ] Verificacao de health checks
- [ ] Teste de funcionalidades afetadas
- [ ] Revogacao do secret antigo (quando aplicavel)
- [ ] Atualizacao do registro de rotacao
- [ ] Comunicacao a equipe (se necessario)

## 4. Monitoramento Pos-Rotacao

Apos qualquer rotacao de secrets, monitore:

1. **Health Check**: `GET /health/detailed`
2. **Logs de erro**: Buscar por "authentication", "connection", "unauthorized"
3. **Metricas**: Verificar aumento de erros em `/metrics`

```bash
# Verificar saude do sistema
curl -s https://portal.pge.ms.gov.br/health/detailed | jq

# Verificar erros recentes nos logs
kubectl logs deployment/portal-pge --since=10m | grep -i error
```

## 5. Resposta a Incidentes

### Em caso de vazamento de SECRET_KEY:

1. **Rotacao imediata** conforme procedimento 2.1
2. Invalidar todas as sessoes ativas
3. Revisar logs de acesso das ultimas 24h
4. Notificar time de seguranca
5. Documentar incidente

### Em caso de vazamento de credenciais de banco:

1. **Revogar credenciais** junto ao DBA imediatamente
2. Rotacionar senha conforme procedimento 2.3
3. Revisar logs de acesso ao banco
4. Verificar integridade dos dados
5. Documentar incidente

## 6. Registro de Rotacoes

Mantenha registro de todas as rotacoes em local seguro:

| Data | Secret | Responsavel | Motivo | Observacoes |
|------|--------|-------------|--------|-------------|
| 2024-01-15 | SECRET_KEY | admin | Rotacao anual | Sem incidentes |
| 2024-02-01 | GEMINI_KEY | admin | Nova chave | Chave anterior expirou |

## 7. Automacao (Futuro)

Considerar implementacao de:
- HashiCorp Vault para gerenciamento de secrets
- AWS Secrets Manager ou Azure Key Vault
- Rotacao automatica com External Secrets Operator (K8s)

---

**Ultima atualizacao**: Janeiro 2024
**Autor**: LAB/PGE-MS
