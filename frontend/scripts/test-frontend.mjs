/**
 * End-to-end check of the frontend's data path.
 *
 * Every request below carries `Origin: http://localhost:3000`, which is exactly
 * what the browser sends. If CORS were misconfigured this test would fail the
 * same way the real page does, instead of passing in a way the demo does not.
 *
 * Start both servers first, then:
 *
 *     node scripts/test-frontend.mjs
 *     node scripts/test-frontend.mjs --no-agent   # skip the Gemini call
 */

import { execFileSync } from "node:child_process";
import { createRequire } from "node:module";
import { fileURLToPath } from "node:url";
import path from "node:path";
import fs from "node:fs";

const HERE = path.dirname(fileURLToPath(import.meta.url));
const ROOT = path.resolve(HERE, "..");
const API = "http://127.0.0.1:8000";
const PAGE = "http://127.0.0.1:3000";
const ORIGIN = "http://localhost:3000";

let passed = 0;
const failed = [];

function check(name, condition, detail = "") {
  if (condition) {
    passed += 1;
    console.log(`  PASS  ${name}${detail ? `  ${detail}` : ""}`);
  } else {
    failed.push(name);
    console.log(`  FAIL  ${name}  ${detail}`);
  }
}

async function api(pathname, init = {}) {
  const response = await fetch(`${API}${pathname}`, {
    ...init,
    headers: { "Content-Type": "application/json", Origin: ORIGIN, ...(init.headers ?? {}) },
  });
  return { response, body: await response.json() };
}

/** Compile lib/budget.ts and load it, so the test exercises what ships. */
function loadBudgetParser() {
  const outDir = path.join(ROOT, ".test-build");
  // Invoke the tsc entry point through node directly: spawning `npx.cmd` fails
  // with EINVAL on Windows under Node 20+ unless a shell is used, and a shell
  // is a worse dependency than a path.
  //
  // --skipLibCheck is required, not cosmetic: compiling a single file outside a
  // tsconfig makes tsc walk up every parent node_modules/@types, and a stray
  // one in the user's Documents folder holds type definitions that do not
  // compile. They have nothing to do with this project.
  execFileSync(
    process.execPath,
    [path.join(ROOT, "node_modules", "typescript", "bin", "tsc"),
     "lib/budget.ts", "--outDir", ".test-build",
     "--module", "commonjs", "--target", "es2022", "--skipLibCheck"],
    { cwd: ROOT, stdio: "pipe" },
  );
  const require = createRequire(import.meta.url);
  const { parseBudget } = require(path.join(outDir, "budget.js"));
  fs.rmSync(outDir, { recursive: true, force: true });
  return parseBudget;
}

/* ------------------------------------------------- 1. budget parser (unit) */

function testBudgetParser() {
  console.log("\nlib/budget.ts - parseBudget");

  const parseBudget = loadBudgetParser();

  const cases = [
    ["I have $500,000 for Central LA. Where should I invest?", 500000],
    ["What would $1,200,000 buy me?", 1200000],
    ["budget is 750k", 750000],
    ["We have $1.2 million available", 1200000],
    ["Show me the top 10 zones", null],
    ["Give me the top 10 riskiest tracts with $500,000", 500000],
    ["Why does night heat matter?", null],
    ["2000000 dollars", 2000000],
  ];

  for (const [text, expected] of cases) {
    const actual = parseBudget(text);
    check(`parseBudget(${JSON.stringify(text)})`, actual === expected,
          `got ${actual}, expected ${expected}`);
  }
}

/* -------------------------------------------------------- 2. the page HTML */

async function testPage() {
  console.log("\nGET / (Next.js)");
  const response = await fetch(PAGE);
  const html = await response.text();
  check("page returns 200", response.ok, `HTTP ${response.status}`);
  check("header rendered", html.includes("HeatGov AI"));
  check("action plan empty state rendered",
        html.includes("No plan yet. Ask HeatGov AI for one!"));
  check("both tabs rendered", html.includes(">Chat<") && html.includes(">Action Plan<"));
  check("layer toggle icons rendered", (html.match(/<svg/g) ?? []).length >= 4,
        `${(html.match(/<svg/g) ?? []).length} inline svg icons`);
  check("body keeps the fixed light palette", html.includes("bg-slate-100"));

  // Our own stylesheet must not flip the palette with the operating system:
  // the map colours have to mean the same thing on every demo machine. The
  // maplibre-gl chunk and the Next.js error page both carry their own
  // prefers-color-scheme rules, which is why this checks our chunk alone.
  const appStylesheet = [...html.matchAll(/href="([^"]*\.css[^"]*)"/g)]
    .map((match) => match[1])
    .find((href) => !href.includes("maplibre"));
  check("app stylesheet found", Boolean(appStylesheet), String(appStylesheet));
  if (appStylesheet) {
    const css = await (await fetch(`${PAGE}${appStylesheet}`)).text();
    check("no dark-mode override in our CSS", !css.includes("prefers-color-scheme"));
  }
}

/* ------------------------------------------------------ 3. health + badge */

async function testHealth() {
  console.log("\nGET /api/health");
  const { response, body } = await api("/api/health");
  check("health 200", response.ok, `HTTP ${response.status}`);
  check("CORS header present",
        response.headers.get("access-control-allow-origin") === ORIGIN,
        `${response.headers.get("access-control-allow-origin")}`);
  check("badge has both R2 values",
        typeof body.model_a_r2 === "number" && typeof body.model_b_r2 === "number",
        `A=${body.model_a_r2} B=${body.model_b_r2}`);
  return body;
}

/* ------------------------------------------------- 4. every map layer */

async function testLayers() {
  const layers = ["tcm_peak_22h", "tcm_peak_15h", "exceedance", "persistence"];
  for (const layer of layers) {
    console.log(`\nGET /api/heatmap/${layer}`);
    const started = Date.now();
    const { response, body } = await api(`/api/heatmap/${layer}`);
    const seconds = (Date.now() - started) / 1000;
    check(`${layer} 200`, response.ok, `HTTP ${response.status}`);

    const stats = body.metadata?.stats;
    check(`${layer} carries stats`, Boolean(stats), JSON.stringify(stats));
    // A flat p5 == p95 would collapse the colour ramp into one shade.
    check(`${layer} ramp has range`, stats && stats.p95 > stats.p5,
          stats ? `${stats.p5} -> ${stats.p95} ${body.metadata.unit}` : "");

    const column = body.metadata.value_column;
    const usable = body.features.filter(
      (feature) => feature.properties?.[column] !== null &&
                   feature.properties?.[column] !== undefined,
    );
    check(`${layer} tiles renderable`, usable.length > 8000,
          `${usable.length.toLocaleString()} of ${body.features.length.toLocaleString()}, ${seconds.toFixed(1)}s`);
  }
}

/* ---------------------------------------------- 5. pins and the click path */

async function testZonesAndPredict() {
  console.log("\nGET /api/zones/ranked?top_n=10  (map pins)");
  const { response, body } = await api("/api/zones/ranked?top_n=10");
  check("zones 200", response.ok, `HTTP ${response.status}`);
  check("ten pins", body.zones.length === 10, `${body.zones.length}`);
  check("every pin has coordinates",
        body.zones.every((zone) => Number.isFinite(zone.lat) && Number.isFinite(zone.lon)));
  for (const [index, zone] of body.zones.slice(0, 3).entries()) {
    console.log(`        #${index + 1}  ${zone.tract_fips}  risk ${zone.risk_score}  (${zone.lat}, ${zone.lon})`);
  }

  const first = body.zones[0];
  console.log(`\nPOST /api/predict  (clicking pin #1, tract ${first.tract_fips})`);
  const { response: predictResponse, body: prediction } = await api("/api/predict", {
    method: "POST",
    body: JSON.stringify({ tract_fips: first.tract_fips }),
  });
  check("predict 200", predictResponse.ok, `HTTP ${predictResponse.status}`);
  check("detail card has all three scores",
        [prediction.risk_score_b, prediction.risk_score_a,
         prediction.official_calenviroscreen_score].every((value) => typeof value === "number"),
        `B=${prediction.risk_score_b} A=${prediction.risk_score_a} CES=${prediction.official_calenviroscreen_score}`);
  check("three SHAP drivers", prediction.top_shap_features.length === 3);
  for (const driver of prediction.top_shap_features) {
    console.log(`          ${driver.impact_points >= 0 ? "+" : ""}${driver.impact_points}  ${driver.explanation}`);
  }
}

/* -------------------------------------------------- 6. the demo scenario */

async function testScenario(skipAgent) {
  const question = "I have $500,000 for Central LA. Where should I invest?";
  console.log(`\nDemo scenario: ${JSON.stringify(question)}`);

  const budget = loadBudgetParser()(question);
  check("chat detects the budget", budget === 500000, `$${budget}`);

  if (!skipAgent) {
    console.log("\nPOST /api/agent/chat");
    const started = Date.now();
    const { response, body } = await api("/api/agent/chat", {
      method: "POST",
      body: JSON.stringify({ message: question, session_id: "frontend-test" }),
    });
    const seconds = (Date.now() - started) / 1000;
    check("agent 200", response.ok, `HTTP ${response.status}`);
    if (response.ok) {
      const tools = body.tool_calls.map((call) => call.tool);
      console.log(`        [${seconds.toFixed(1)}s, ${body.rounds} rounds, ${body.model}]`);
      console.log(`        tools: ${JSON.stringify(tools)}`);
      check("agent called tools", tools.length > 0);
      check("reply triggers the plan panel", /budget|plan|invest|fund/i.test(body.reply));
      check("agent does not say sensors", !/sensor/i.test(body.reply));
      console.log("\n        --- agent reply ---");
      for (const line of body.reply.split("\n")) console.log(`        ${line}`);
      console.log("        --- end reply ---");
    }
  }

  console.log("\nPOST /api/optimize  (auto-fired by the chat panel)");
  const { response, body } = await api("/api/optimize", {
    method: "POST",
    body: JSON.stringify({ budget_usd: budget, top_n: 10 }),
  });
  check("optimize 200", response.ok, `HTTP ${response.status}`);
  check("plan fits the budget", body.total_cost_usd <= budget,
        `$${body.total_cost_usd.toLocaleString()} of $${budget.toLocaleString()}`);
  check("no summed-degrees field", !("total_expected_reduction_c" in body));
  check("footer numbers present",
        typeof body.zones_funded === "number" && typeof body.coverage_score === "number",
        `${body.zones_funded}/${body.zones_considered} funded, ${body.coverage_score}% coverage`);
  for (const [index, item] of body.plan.entries()) {
    console.log(`          ${index + 1}. ${item.tract_fips}  ${item.intervention.padEnd(10)} ` +
                `$${item.cost_usd.toLocaleString().padStart(9)}  -${item.expected_reduction_c}C`);
  }
}

/* ------------------------------------------------------------------ main */

const skipAgent = process.argv.includes("--no-agent");

try {
  testBudgetParser();
  await testPage();
  await testHealth();
  await testLayers();
  await testZonesAndPredict();
  await testScenario(skipAgent);
} catch (exception) {
  console.error(`\nUNEXPECTED: ${exception.stack ?? exception}`);
  failed.push("unexpected exception");
}

console.log(`\n${"=".repeat(74)}`);
console.log(`RESULT: ${passed} passed, ${failed.length} failed`);
for (const name of failed) console.log(`  FAILED: ${name}`);
console.log("=".repeat(74));
process.exit(failed.length ? 1 : 0);
