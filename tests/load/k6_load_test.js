/**
 * k6 Load Testing Script - Portal PGE-MS
 *
 * Testa carga e performance dos principais endpoints.
 *
 * INSTALACAO:
 *   - Download k6: https://k6.io/docs/getting-started/installation/
 *   - Windows: choco install k6
 *   - Linux: apt install k6
 *
 * EXECUCAO:
 *   # Teste basico (10 VUs por 30s)
 *   k6 run tests/load/k6_load_test.js
 *
 *   # Com mais carga
 *   k6 run --vus 50 --duration 1m tests/load/k6_load_test.js
 *
 *   # Contra ambiente especifico
 *   k6 run -e BASE_URL=https://portal.pge.ms.gov.br tests/load/k6_load_test.js
 *
 *   # Com output para arquivo JSON
 *   k6 run --out json=results.json tests/load/k6_load_test.js
 *
 * METRICAS IMPORTANTES:
 *   - http_req_duration: Latencia das requests (p95 < 500ms)
 *   - http_req_failed: Taxa de erro (< 1%)
 *   - http_reqs: Requests por segundo
 *
 * Autor: LAB/PGE-MS
 */

import http from "k6/http";
import { check, sleep, group } from "k6";
import { Rate, Trend } from "k6/metrics";

// ============================================
// CONFIGURACAO
// ============================================

// URL base (pode ser sobrescrita via -e BASE_URL=...)
const BASE_URL = __ENV.BASE_URL || "http://localhost:8000";

// Credenciais de teste
const TEST_USER = __ENV.TEST_USER || "admin";
const TEST_PASS = __ENV.TEST_PASS || "admin";

// Metricas customizadas
const errorRate = new Rate("errors");
const loginDuration = new Trend("login_duration");
const healthCheckDuration = new Trend("health_check_duration");

// ============================================
// OPCOES DO TESTE
// ============================================

export const options = {
  // Cenarios de carga
  scenarios: {
    // Cenario 1: Carga constante leve
    constant_load: {
      executor: "constant-vus",
      vus: 10,
      duration: "30s",
      startTime: "0s",
    },
    // Cenario 2: Rampa de carga
    ramp_up: {
      executor: "ramping-vus",
      startVUs: 0,
      stages: [
        { duration: "10s", target: 20 },
        { duration: "20s", target: 20 },
        { duration: "10s", target: 50 },
        { duration: "20s", target: 50 },
        { duration: "10s", target: 0 },
      ],
      startTime: "35s",
    },
  },

  // Thresholds (criterios de sucesso)
  thresholds: {
    // 95% das requests devem completar em < 500ms
    http_req_duration: ["p(95)<500"],
    // Taxa de erro < 1%
    http_req_failed: ["rate<0.01"],
    // Metricas customizadas
    errors: ["rate<0.01"],
    health_check_duration: ["p(95)<100"],
    login_duration: ["p(95)<1000"],
  },
};

// ============================================
// SETUP (executado uma vez no inicio)
// ============================================

export function setup() {
  console.log(`[SETUP] Testando contra: ${BASE_URL}`);

  // Verifica se servidor esta respondendo
  const res = http.get(`${BASE_URL}/health`);
  check(res, {
    "servidor disponivel": (r) => r.status === 200,
  });

  if (res.status !== 200) {
    throw new Error(`Servidor nao disponivel: ${res.status}`);
  }

  return {
    baseUrl: BASE_URL,
    healthyStart: true,
  };
}

// ============================================
// FUNCOES AUXILIARES
// ============================================

function login(user, pass) {
  const formData = {
    username: user,
    password: pass,
  };

  const params = {
    headers: {
      "Content-Type": "application/x-www-form-urlencoded",
    },
  };

  const start = Date.now();
  const res = http.post(`${BASE_URL}/auth/login`, formData, params);
  loginDuration.add(Date.now() - start);

  if (res.status === 200) {
    try {
      const body = JSON.parse(res.body);
      return body.access_token;
    } catch (e) {
      return null;
    }
  }
  return null;
}

function authHeaders(token) {
  return {
    headers: {
      Authorization: `Bearer ${token}`,
    },
  };
}

// ============================================
// TESTES PRINCIPAIS
// ============================================

export default function (data) {
  // Grupo 1: Health Checks (nao requer auth)
  group("Health Checks", function () {
    const start = Date.now();
    const res = http.get(`${BASE_URL}/health`);
    healthCheckDuration.add(Date.now() - start);

    const success = check(res, {
      "health status 200": (r) => r.status === 200,
      "health body valid": (r) => {
        try {
          const body = JSON.parse(r.body);
          return body.status !== undefined;
        } catch (e) {
          return false;
        }
      },
    });

    errorRate.add(!success);
    sleep(0.5);
  });

  // Grupo 2: Health Check Detalhado
  group("Health Detailed", function () {
    const res = http.get(`${BASE_URL}/health/detailed`);

    const success = check(res, {
      "detailed status 200": (r) => r.status === 200,
      "detailed has components": (r) => {
        try {
          const body = JSON.parse(r.body);
          return body.components !== undefined;
        } catch (e) {
          return false;
        }
      },
    });

    errorRate.add(!success);
    sleep(0.5);
  });

  // Grupo 3: Login (teste de autenticacao)
  group("Authentication", function () {
    const token = login(TEST_USER, TEST_PASS);

    const success = check(null, {
      "login successful": () => token !== null,
    });

    errorRate.add(!success);

    // Se login bem sucedido, testa endpoint protegido
    if (token) {
      const res = http.get(`${BASE_URL}/api/users/me`, authHeaders(token));

      check(res, {
        "user me status 200": (r) => r.status === 200,
        "user me has username": (r) => {
          try {
            const body = JSON.parse(r.body);
            return body.username !== undefined;
          } catch (e) {
            return false;
          }
        },
      });
    }

    sleep(1);
  });

  // Grupo 4: Metricas
  group("Metrics", function () {
    const res = http.get(`${BASE_URL}/metrics`);

    const success = check(res, {
      "metrics status 200": (r) => r.status === 200,
      "metrics has content": (r) => r.body.length > 0,
    });

    errorRate.add(!success);
    sleep(0.5);
  });

  // Pausa entre iteracoes
  sleep(Math.random() * 2);
}

// ============================================
// TEARDOWN (executado uma vez no final)
// ============================================

export function teardown(data) {
  console.log("[TEARDOWN] Teste concluido");

  // Verifica se servidor ainda esta saudavel
  const res = http.get(`${BASE_URL}/health`);
  if (res.status !== 200) {
    console.warn(
      "[TEARDOWN] ATENCAO: Servidor pode estar degradado apos teste"
    );
  }
}
