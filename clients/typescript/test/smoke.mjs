// Integration smoke test against a running `minion serve`. It creates no desktops.
//
//   minion serve --port 4810 --token tstok --idle-freeze 0 --quiet &
//   npm run build
//   MINION_URL=http://127.0.0.1:4810 MINION_TOKEN=tstok node test/smoke.mjs

import assert from "node:assert/strict";
import { Minion, MinionError } from "../dist/index.js";

const minion = new Minion(); // reads MINION_URL and MINION_TOKEN
const ok = (what) => console.log(`ok   ${what}`);
console.log(`Minion server: ${minion.baseUrl}`);

// -- the server ---------------------------------------------------------------
const health = await minion.health();
assert.equal(health.ok, true);
assert.equal(typeof health.version, "string");
ok(`health(): Minion ${health.version}, ${health.backend} backend`);

const profiles = await minion.profiles();
assert.ok(Array.isArray(profiles) && profiles.length > 0, "profiles() returns a non-empty array");
for (const p of profiles) {
  assert.equal(typeof p.name, "string");
  assert.ok(Array.isArray(p.apps));
}
assert.ok(profiles.some((p) => p.name === "browser"), "the browser profile exists");
ok(`profiles(): ${profiles.map((p) => p.name).join(", ")}`);

const desktops = await minion.desktops();
assert.ok(Array.isArray(desktops));
for (const d of desktops) {
  assert.equal(typeof d.name, "string");
  assert.equal(typeof d.state, "string");
}
ok(`desktops(): ${desktops.length} (${desktops.map((d) => `${d.name}: ${d.state}`).join(", ") || "none"})`);

// -- errors carry the server's message and the HTTP status ----------------------
await assert.rejects(
  new Minion({ baseUrl: minion.baseUrl, token: "wrong-token" }).health(),
  (e) => e instanceof MinionError && e.status === 401 && /unauthorized/i.test(e.message),
);
ok("a wrong token throws MinionError 401");

await assert.rejects(
  minion.desktop("no-such-desktop-ts-smoke").info(),
  (e) => e instanceof MinionError && e.status === 404 && /no-such-desktop-ts-smoke/.test(e.message),
);
ok("an unknown desktop throws MinionError 404");

await assert.rejects(
  new Minion({ baseUrl: "http://127.0.0.1:1" }).health(),
  (e) => e instanceof MinionError && e.status === 0 && /cannot reach/.test(e.message),
);
ok("an unreachable server throws MinionError 0");

// -- universal tools: GET /api/tools and POST /api/tools/call (may not exist yet) --
let openaiTools;
try {
  openaiTools = await minion.listTools();
} catch (e) {
  if (!(e instanceof MinionError && e.status === 404)) throw e;
  console.log(`skip tools: this server has no /api/tools yet (404: ${e.message})`);
}

if (openaiTools) {
  assert.ok(Array.isArray(openaiTools) && openaiTools.length > 0);
  const names = openaiTools.map((t) => t.function.name);
  for (const t of openaiTools) {
    assert.equal(t.type, "function");
    assert.equal(t.function.parameters.type, "object");
  }
  ok(`listTools(): ${names.join(", ")}`);

  const nameOf = {
    "openai-responses": (t) => t.name,
    anthropic: (t) => (assert.equal(t.input_schema.type, "object"), t.name),
    gemini: (t) => t.name,
    mcp: (t) => (assert.equal(t.inputSchema.type, "object"), t.name),
  };
  for (const [format, name] of Object.entries(nameOf)) {
    const defs = await minion.listTools(format);
    assert.deepEqual(defs.map(name), names, `listTools("${format}") has the same tools`);
    ok(`listTools("${format}"): ${defs.length} tools`);
  }
  const compact = await minion.listTools("mcp", { compact: true });
  assert.ok(compact.length >= 1 && compact.length < names.length);
  ok(`listTools("mcp", { compact: true }): ${compact.map((t) => t.name).join(", ")}`);

  const aiTools = await minion.toVercelAiTools();
  assert.deepEqual(Object.keys(aiTools), names);
  for (const [name, tool] of Object.entries(aiTools)) {
    assert.equal(typeof tool.description, "string", `${name} has a description`);
    assert.equal(typeof tool.execute, "function");
    assert.equal(tool.inputSchema, tool.parameters);
    assert.equal(tool.inputSchema[Symbol.for("vercel.ai.schema")], true);
    assert.equal(tool.inputSchema.jsonSchema.type, "object");
  }
  ok(`toVercelAiTools(): ${Object.keys(aiTools).length} tools`);

  const pinned = await minion.toVercelAiTools({ desktop: "some-desktop", exclude: ["files"] });
  assert.ok(!("files" in pinned));
  for (const tool of Object.values(pinned)) assert.ok(!("desktop" in (tool.inputSchema.jsonSchema.properties ?? {})));
  ok("toVercelAiTools({ desktop, exclude }) hides the desktop argument");

  // Read-only calls only: other tools would act on whatever desktop is current.
  const profilesResult = await minion.callTool("desktop", { action: "profiles" });
  assert.equal(profilesResult.isError, false);
  assert.ok(profilesResult.content.some((c) => c.type === "text" && c.text.includes("browser")));
  ok('callTool("desktop", { action: "profiles" })');

  const listResult = await minion.callTool("desktop", { action: "list" }, { session: "ts-smoke" });
  assert.equal(listResult.isError, false);
  ok(`callTool("desktop", { action: "list" }, { session }): ${listResult.content[0]?.text.split("\n")[0]}`);

  const viaAiSdk = await aiTools.desktop.execute({ action: "profiles" }, { toolCallId: "t1", messages: [] });
  assert.equal(viaAiSdk.isError, false);
  const output = aiTools.desktop.toModelOutput({ toolCallId: "t1", input: {}, output: viaAiSdk });
  assert.equal(output.type, "content");
  ok("a Vercel AI SDK tool executes and converts its output");

  const unknown = await minion.callTool("no_such_tool", {});
  assert.equal(unknown.isError, true);
  ok(`an unknown tool is an error result: ${unknown.content[0]?.text}`);
}

console.log("smoke test passed");
