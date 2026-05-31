/**
 * E2E smoke test: API + same fetch path the UI uses (CORS).
 * Run with: node scripts/e2e-sandbox-test.mjs
 */
import { writeFileSync, unlinkSync } from "fs";
import { tmpdir } from "os";
import { join } from "path";

const API_BASE = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://127.0.0.1:8000";
const WEB_BASE = process.env.WEB_BASE_URL ?? "http://localhost:3000";

const csv = `Symbol,Shares,CostBasis
MSFT,10,400
NVDA,5,800
ASML,3,700
AVGO,2,1200
`;

const tmpCsv = join(tmpdir(), `sandbox-e2e-${Date.now()}.csv`);
writeFileSync(tmpCsv, csv, "utf8");

let failed = 0;
function pass(msg) {
  console.log(`PASS: ${msg}`);
}
function fail(msg) {
  console.error(`FAIL: ${msg}`);
  failed++;
}

try {
  const health = await fetch(`${API_BASE}/health`);
  if (!health.ok) fail(`health status ${health.status}`);
  else {
    const h = await health.json();
    if (h.status !== "healthy") fail(`health body ${JSON.stringify(h)}`);
    else pass(`GET ${API_BASE}/health`);
  }

  const page = await fetch(WEB_BASE);
  if (!page.ok) fail(`homepage status ${page.status}`);
  else {
    const html = await page.text();
    for (const needle of [
      "Custom Sandbox",
      "Import scenario",
      "Simulated Scenario",
      "theoretical portfolio",
    ]) {
      if (!html.includes(needle)) fail(`homepage missing "${needle}"`);
      else pass(`homepage contains "${needle}"`);
    }
  }

  const { readFileSync } = await import("fs");
  const blob = new Blob([readFileSync(tmpCsv)], { type: "text/csv" });
  const form = new FormData();
  form.append("file", blob, "sandbox-e2e.csv");

  const importRes = await fetch(`${API_BASE}/api/sandbox/import`, {
    method: "POST",
    body: form,
  });
    if (!importRes.ok) {
      fail(`import status ${importRes.status}: ${await importRes.text()}`);
    } else {
      const data = await importRes.json();
      if (data.positions?.length !== 4) {
        fail(`expected 4 positions, got ${data.positions?.length}`);
      } else if (!data.disclaimer?.includes("theoretical")) {
        fail("missing disclaimer in response");
      } else if (!data.persisted) {
        fail("expected persisted=true (set DATABASE_URL)");
      } else if (data.positions[0]?.weight_pct == null) {
        fail("expected weight_pct on positions");
      } else {
        pass(`POST ${API_BASE}/api/sandbox/import → 4 positions`);
        pass(`symbols: ${data.positions.map((p) => p.symbol).join(", ")}`);
        pass(`persisted to portfolio ${data.portfolio_name ?? "?"}`);
      }
    }

  const corsRes = await fetch(`${API_BASE}/api/sandbox/import`, {
    method: "OPTIONS",
    headers: {
      Origin: WEB_BASE,
      "Access-Control-Request-Method": "POST",
    },
  });
  if (corsRes.status !== 200 && corsRes.status !== 204) {
    fail(`CORS preflight status ${corsRes.status}`);
  } else {
    pass(`CORS preflight from ${WEB_BASE} → ${corsRes.status}`);
  }
} catch (e) {
  fail(e.message ?? String(e));
} finally {
  try {
    unlinkSync(tmpCsv);
  } catch {
    /* ignore */
  }
}

if (failed > 0) {
  console.error(`\n${failed} check(s) failed. Is uvicorn on :8000 and npm run dev on :3000?`);
  process.exit(1);
}
console.log("\nAll E2E checks passed.");
