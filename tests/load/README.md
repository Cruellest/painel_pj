# Load Testing - Portal PGE-MS

Testes de carga usando k6.

## Instalacao do k6

```bash
# Windows (via Chocolatey)
choco install k6

# Linux (Debian/Ubuntu)
sudo gpg --no-default-keyring --keyring /usr/share/keyrings/k6-archive-keyring.gpg --keyserver hkp://keyserver.ubuntu.com:80 --recv-keys C5AD17C747E3415A3642D57D77C6C491D6AC1D69
echo "deb [signed-by=/usr/share/keyrings/k6-archive-keyring.gpg] https://dl.k6.io/deb stable main" | sudo tee /etc/apt/sources.list.d/k6.list
sudo apt-get update
sudo apt-get install k6

# macOS
brew install k6
```

## Execucao

### Teste Basico

```bash
# Teste padrao (10 VUs, 30s)
k6 run tests/load/k6_load_test.js

# Contra servidor local
k6 run -e BASE_URL=http://localhost:8000 tests/load/k6_load_test.js

# Contra producao (CUIDADO!)
k6 run -e BASE_URL=https://portal.pge.ms.gov.br tests/load/k6_load_test.js
```

### Variar Carga

```bash
# 50 usuarios simultaneos por 2 minutos
k6 run --vus 50 --duration 2m tests/load/k6_load_test.js

# 100 usuarios por 5 minutos
k6 run --vus 100 --duration 5m tests/load/k6_load_test.js
```

### Salvar Resultados

```bash
# JSON
k6 run --out json=results.json tests/load/k6_load_test.js

# CSV
k6 run --out csv=results.csv tests/load/k6_load_test.js

# Enviar para InfluxDB (se configurado)
k6 run --out influxdb=http://localhost:8086/k6 tests/load/k6_load_test.js
```

## Metricas Importantes

| Metrica | Descricao | Threshold |
|---------|-----------|-----------|
| `http_req_duration` | Latencia das requests | p95 < 500ms |
| `http_req_failed` | Taxa de erro | < 1% |
| `http_reqs` | Requests por segundo | - |
| `vus` | Usuarios virtuais ativos | - |

## Thresholds Configurados

```javascript
thresholds: {
  // 95% das requests devem completar em < 500ms
  http_req_duration: ["p(95)<500"],
  // Taxa de erro < 1%
  http_req_failed: ["rate<0.01"],
}
```

## Cenarios de Teste

### 1. Carga Constante

10 usuarios virtuais por 30 segundos.

### 2. Rampa de Carga

```
0 -> 20 VUs (10s)
20 VUs (20s)
20 -> 50 VUs (10s)
50 VUs (20s)
50 -> 0 VUs (10s)
```

## Interpretando Resultados

### Exemplo de Output

```
running (1m10.0s), 00/50 VUs, 1234 complete and 0 interrupted iterations
ramp_up ✓ [==============================] 0/50 VUs  1m10s

     ✓ health status 200
     ✓ health body valid
     ✓ login successful
     ✓ metrics status 200

     checks.........................: 100.00% ✓ 4936 ✗ 0
     data_received..................: 2.5 MB  36 kB/s
     data_sent......................: 156 kB  2.2 kB/s
     http_req_duration..............: avg=45.23ms p(95)=123.45ms
     http_reqs......................: 1234    17.6/s
     vus............................: 0       min=0   max=50
```

### O que verificar

1. **checks**: Todas as verificacoes devem passar (100%)
2. **http_req_duration p(95)**: Deve ser < 500ms
3. **http_req_failed**: Deve ser < 1%
4. **http_reqs/s**: Taxa de throughput

## Troubleshooting

### Muitos erros de conexao

- Verificar se servidor suporta a carga
- Aumentar limites de conexao do servidor
- Verificar rate limiting

### Latencia alta

- Verificar recursos do servidor (CPU, memoria)
- Verificar queries do banco de dados
- Verificar servicos externos (APIs)

### Teste nao inicia

- Verificar se k6 esta instalado
- Verificar se URL base esta acessivel
- Verificar credenciais de teste

---

**Autor**: LAB/PGE-MS
