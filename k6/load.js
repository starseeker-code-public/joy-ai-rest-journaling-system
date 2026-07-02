// k6 load test: register once, then hammer journal create/list.
// Usage: k6 run k6/load.js --env BASE_URL=http://localhost:8080
import http from 'k6/http';
import { check, sleep } from 'k6';

const BASE = __ENV.BASE_URL || 'http://localhost:8080';

export const options = {
  stages: [
    { duration: '30s', target: 20 },
    { duration: '1m', target: 20 },
    { duration: '30s', target: 0 },
  ],
  thresholds: {
    // Performance budgets from the README
    'http_req_duration{name:create}': ['p(95)<200'],
    'http_req_duration{name:list}': ['p(95)<300'],
    http_req_failed: ['rate<0.01'],
  },
};

export function setup() {
  const email = `k6-${Date.now()}@load.test`;
  const password = 'k6-load-test-pass';
  const creds = JSON.stringify({ email, password });
  const params = { headers: { 'Content-Type': 'application/json' } };
  http.post(`${BASE}/auth/register`, creds, params);
  const login = http.post(`${BASE}/auth/login`, creds, params);
  return { token: login.json('token') };
}

export default function (data) {
  const params = {
    headers: {
      'Content-Type': 'application/json',
      Authorization: `Bearer ${data.token}`,
    },
  };

  const created = http.post(
    `${BASE}/api/journals`,
    JSON.stringify({ title: `Load ${__VU}-${__ITER}`, content: 'k6 says hi', mood: 5 }),
    { ...params, tags: { name: 'create' } },
  );
  check(created, { 'create 201': (r) => r.status === 201 });

  const listed = http.get(`${BASE}/api/journals`, { ...params, tags: { name: 'list' } });
  check(listed, { 'list 200': (r) => r.status === 200 });

  sleep(1);
}
