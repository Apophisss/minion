// Offline tests: every method against a fake server that records the requests (no Minion, no Docker).
//
//   npm test        (builds, then runs this file with node --test)

import assert from "node:assert/strict";
import { createServer } from "node:http";
import { after, before, beforeEach, test } from "node:test";
import { Minion, MinionError } from "../dist/index.js";

const D = "/api/desktops/browser-1";
const info = { name: "browser-1", profile: "browser", state: "running", backend: "fake", size: "1280x800" };
const hello = { version: "0.1.0", protocol: 1, screen: [1280, 800], apps: ["Firefox"] };
const png = Buffer.from([0x89, 0x50, 0x4e, 0x47, 1, 2, 3]);
const actResult = (ok) => ({
  ok,
  summary: ok ? "✓ done\n→ no visible change" : "✗ no element matches 'Nope'",
  steps: [],
  change: { changed: false, fraction: 0 },
  focused: null,
  opened: [],
  closed: [],
  error: ok ? null : "no element matches 'Nope'",
  elapsed: 0.1,
});
const object = (properties, extra = {}) => ({ type: "object", properties, ...extra });
const mcpTools = [
  {
    name: "see",
    description: "Read the screen.",
    inputSchema: object({ desktop: { type: "string" }, ocr: { type: "boolean" } }, { required: ["desktop"] }),
  },
  { name: "screenshot", description: "Look.", inputSchema: object({ desktop: { type: "string" } }) },
  { name: "files", description: "Move files.", inputSchema: object({ path: { type: "string" } }) },
];
const image = { type: "image", data: png.toString("base64"), mimeType: "image/png" };
const screenText = { type: "text", text: "Screen 1280x800." };

let requests = [];
let handoff = null;

function route(method, path, query, body) {
  switch (`${method} ${path}`) {
    case "GET /api/health": return [200, { ok: true, version: "0.1.0", backend: "fake" }];
    case "GET /api/profiles": return [200, [{ name: "browser", apps: ["Firefox"] }]];
    case "GET /api/desktops": return [200, [info]];
    case "POST /api/desktops": return [201, { ...info, name: body.name ?? "browser-1", hello }];
    case `GET ${D}`: return [200, { ...info, hello }];
    case `GET ${D}/info`: return [200, info];
    case `GET ${D}/status`: return [200, { ...info, uptime: 5 }];
    case `GET ${D}/windows`: return [200, [{ id: "0x1", title: "Firefox" }]];
    case `GET ${D}/see`:
      return [200, { text: '@1 button "Save"', elements: [], windows: [], focused: null, ocr: [] }];
    case `GET ${D}/screenshot`: return [200, png, query.get("format") === "jpeg" ? "image/jpeg" : "image/png"];
    case `POST ${D}/act`: return [200, actResult(!JSON.stringify(body.actions).includes("Nope"))];
    case `POST ${D}/open`: return [200, { command: "firefox-esr https://example.com", kind: "url", window: null }];
    case `POST ${D}/run`: return [200, { code: 0, stdout: "42\n", stderr: "", timed_out: false, pid: null }];
    case `POST ${D}/clipboard`: return [200, "text" in body ? { ok: true } : { text: "copied" }];
    case `POST ${D}/freeze`: return [200, { ok: true, state: "paused" }];
    case `POST ${D}/thaw`:
    case `POST ${D}/start`: return [200, { ok: true, state: "running" }];
    case `POST ${D}/stop`: return [200, { ok: true, state: "stopped" }];
    case `POST ${D}/fork`: return [201, { ...info, name: body.name ?? "browser-1-fork-1" }];
    case `POST ${D}/snapshot`: return [200, { tag: body.tag ?? "20261014-120000" }];
    case `POST ${D}/restore`: return [200, { ok: true }];
    case `DELETE ${D}`: return [200, { ok: true }];
    case `GET ${D}/replay`:
      if (query.get("format") === "gif") return [200, Buffer.from("GIF89a"), "image/gif"];
      return [200, "<html>timeline</html>", "text/html; charset=utf-8"];
    case `POST ${D}/handoff`:
      handoff = { message: body.message, created: 1, done: false, note: null, polls: 0 };
      return [200, { ok: true }];
    case `GET ${D}/handoff`:
      if (handoff && ++handoff.polls >= 2) Object.assign(handoff, { done: true, note: "signed in" });
      return [200, handoff];
    case `DELETE ${D}/handoff`:
      handoff = null;
      return [200, { ok: true }];
    case "GET /api/tools":
      return [200, query.get("compact") === "1" ? [{ name: "computer", inputSchema: object({}) }] : mcpTools];
    case "POST /api/tools/call":
      if (body.name === "screenshot") return [200, { content: [image, screenText], isError: false }];
      if (body.name === "files") return [400, { error: "path is required" }];
      return [200, { content: [{ type: "text", text: JSON.stringify(body) }], isError: false }];
    case "GET /slow": return new Promise((resolve) => setTimeout(() => resolve([200, {}]), 400));
    case "GET /teapot": return [418, "I'm a teapot", "text/plain"];
    default: return [404, { error: `no desktop named ${JSON.stringify(path.split("/")[3] ?? path)}` }];
  }
}

const server = createServer(async (req, res) => {
  const url = new URL(req.url, "http://x");
  const chunks = [];
  for await (const chunk of req) chunks.push(chunk);
  const raw = Buffer.concat(chunks).toString();
  const body = raw ? JSON.parse(raw) : {};
  requests.push({ method: req.method, path: url.pathname, query: url.searchParams, headers: req.headers, body, raw });
  const [status, out, type = "application/json"] = await route(req.method, url.pathname, url.searchParams, body);
  const data = Buffer.isBuffer(out) || typeof out === "string" ? out : JSON.stringify(out);
  res.writeHead(status, { "Content-Type": type }).end(data);
});

let minion;
let desk;
const last = () => requests.at(-1);

before(async () => {
  await new Promise((resolve) => server.listen(0, "127.0.0.1", resolve));
  minion = new Minion({ baseUrl: `http://127.0.0.1:${server.address().port}/`, token: "tok" });
  desk = minion.desktop("browser-1");
});
after(() => server.close());
beforeEach(() => {
  requests = [];
});

test("server: health, profiles, desktops, create", async () => {
  assert.equal(minion.baseUrl, `http://127.0.0.1:${server.address().port}`);
  assert.deepEqual(await minion.health(), { ok: true, version: "0.1.0", backend: "fake" });
  assert.equal(last().headers.authorization, "Bearer tok");
  assert.equal(last().headers["x-minion"], "1");
  assert.equal((await minion.profiles())[0].name, "browser");
  assert.equal((await minion.desktops({ stats: true }))[0].name, "browser-1");
  assert.equal(last().query.get("stats"), "1");
  await minion.desktops();
  assert.equal(last().query.has("stats"), false);

  const created = await minion.create({ profile: "office", name: "report", size: [1024, 768] });
  assert.equal(created.name, "report");
  assert.equal(String(created), "report");
  assert.deepEqual(JSON.parse(JSON.stringify(created)), { name: "report" });
  assert.deepEqual(last().body, { profile: "office", name: "report", size: [1024, 768] });
  assert.equal(last().headers["content-type"], "application/json");
  await minion.create();
  assert.deepEqual(last().body, {});
});

test("looking: info, hello, status, windows, see, screenshot", async () => {
  assert.equal((await desk.info()).state, "running");
  assert.deepEqual(await desk.hello(), hello);
  assert.equal(last().path, D);
  assert.equal((await desk.status()).uptime, 5);
  assert.equal((await desk.windows())[0].title, "Firefox");

  assert.match((await desk.see()).text, /Save/);
  assert.equal([...last().query].length, 0);
  await desk.see({ ocr: true, window: "Firefox" });
  assert.deepEqual(Object.fromEntries(last().query), { ocr: "1", window: "Firefox" });

  const shot = await desk.screenshot({ format: "jpeg", maxWidth: 800, marks: true, grid: false });
  assert.ok(shot.data instanceof Uint8Array);
  assert.deepEqual([...shot.data], [...png]);
  assert.equal(shot.mime, "image/jpeg");
  assert.deepEqual(Object.fromEntries(last().query), { format: "jpeg", max_width: "800", marks: "1" });
});

test("acting: act and its helpers", async () => {
  const res = await desk.act({ click: "@3" }, { screenshot: true });
  assert.equal(res.ok, true);
  assert.deepEqual(last().body, { actions: [{ click: "@3" }], screenshot: true, see: false });
  await desk.act(["key ctrl+l", { action: "type", text: "example.com\n" }]);
  assert.deepEqual(last().body.actions, ["key ctrl+l", { action: "type", text: "example.com\n" }]);

  const calls = [
    [
      () => desk.click("@3", { button: "right", count: 2, modifiers: "ctrl" }),
      { action: "click", target: "@3", button: "right", count: 2, modifiers: "ctrl" },
    ],
    [() => desk.click([10, 20]), { action: "click", target: [10, 20] }],
    [() => desk.click(), { action: "click" }],
    [() => desk.type("hello\n"), { action: "type", text: "hello\n" }],
    [() => desk.paste("long text"), { action: "paste", text: "long text" }],
    [() => desk.key("ctrl+s", { repeat: 2 }), { action: "key", keys: "ctrl+s", repeat: 2 }],
    [() => desk.scroll(), { action: "scroll", direction: "down" }],
    [() => desk.scroll("up", 5, "@30"), { action: "scroll", direction: "up", amount: 5, target: "@30" }],
    [() => desk.fill("Email", "ada@example.com"), { action: "fill", target: "Email", text: "ada@example.com" }],
    [() => desk.drag("@4", { x: 5, y: 6 }), { action: "drag", from: "@4", to: { x: 5, y: 6 } }],
    [() => desk.waitFor("Saved", { timeout: 5 }), { action: "wait_for", text: "Saved", timeout: 5 }],
  ];
  for (const [call, action] of calls) {
    await call();
    assert.deepEqual(last().body, { actions: [action], screenshot: false, see: false });
  }
  await desk.click("Save", { see: true });
  assert.equal(last().body.see, true);

  await assert.rejects(desk.click("Nope"), (e) => {
    assert.ok(e instanceof MinionError);
    assert.equal(e.status, 422);
    assert.equal(e.message, "no element matches 'Nope'");
    assert.equal(e.body.ok, false);
    return true;
  });
  assert.equal((await desk.click("Nope", { check: false })).ok, false);
});

test("apps, shell, clipboard and lifecycle", async () => {
  assert.equal((await desk.open("example.com", { wait: 5 })).kind, "url");
  assert.deepEqual(last().body, { target: "example.com", wait: 5 });
  assert.equal((await desk.run("python3 -c 'print(6*7)'", { timeout: 30 })).stdout, "42\n");
  assert.deepEqual(last().body, { command: "python3 -c 'print(6*7)'", timeout: 30 });
  await desk.run(["ls", "-la"], { background: true });
  assert.deepEqual(last().body, { command: ["ls", "-la"], background: true });

  assert.equal(await desk.clipboard(), "copied");
  assert.deepEqual(last().body, {});
  await desk.setClipboard("hi");
  assert.deepEqual(last().body, { text: "hi" });

  for (const [op, state] of [["freeze", "paused"], ["thaw", "running"], ["stop", "stopped"], ["start", "running"]]) {
    assert.deepEqual(await desk[op](), { ok: true, state });
    assert.equal(last().path, `${D}/${op}`);
    assert.equal(last().method, "POST");
  }
  assert.equal((await desk.fork()).name, "browser-1-fork-1");
  assert.equal((await desk.fork("try-b")).name, "try-b");
  assert.equal(await desk.snapshot("before"), "before");
  await desk.restore("before");
  assert.deepEqual(last().body, { tag: "before" });
  assert.equal(await desk.replay(), "<html>timeline</html>");
  assert.equal(Buffer.from(await desk.replayGif()).toString(), "GIF89a");
  await desk.remove();
  assert.equal(last().method, "DELETE");
  assert.equal(last().path, D);
});

test("handoff waits for the human, then clears the request", async () => {
  assert.equal(await desk.handoff("Please sign in", { interval: 0.01 }), "signed in");
  assert.deepEqual(requests.map((r) => r.method), ["POST", "GET", "GET", "DELETE"]);
  assert.deepEqual(requests[0].body, { message: "Please sign in" });
  assert.match(desk.viewUrl(), /\/view\/browser-1\?token=tok$/);
  assert.match(minion.viewUrl(), /:\d+\/\?token=tok$/);
});

test("errors carry the server's message and the HTTP status", async () => {
  await assert.rejects(minion.desktop("nope").info(), {
    name: "MinionError",
    status: 404,
    message: 'no desktop named "nope"',
  });
  await assert.rejects(minion.request("GET", "/teapot"), { status: 418, message: "I'm a teapot" });
  await assert.rejects(
    new Minion({ baseUrl: "http://127.0.0.1:1" }).health(),
    (e) => e instanceof MinionError && e.status === 0 && /cannot reach/.test(e.message),
  );
  const impatient = new Minion({ baseUrl: minion.baseUrl, timeoutMs: 50 });
  await assert.rejects(impatient.request("GET", "/slow"), { status: 0, message: "GET /slow timed out after 50 ms" });
  const controller = new AbortController();
  const aborted = minion.request("GET", "/slow", { signal: controller.signal });
  controller.abort();
  await assert.rejects(aborted, { name: "AbortError" });
});

test("configuration: a URL with ?token=, environment variables", () => {
  const fromUrl = new Minion({ baseUrl: "http://127.0.0.1:4747/?token=abc" });
  assert.equal(fromUrl.baseUrl, "http://127.0.0.1:4747");
  assert.equal(fromUrl.viewUrl("x"), "http://127.0.0.1:4747/view/x?token=abc");
  process.env.MINION_URL = "http://localhost:5000/";
  process.env.MINION_TOKEN = "envtok";
  try {
    const fromEnv = new Minion();
    assert.equal(fromEnv.baseUrl, "http://localhost:5000");
    assert.equal(fromEnv.viewUrl(), "http://localhost:5000/?token=envtok");
  } finally {
    delete process.env.MINION_URL;
    delete process.env.MINION_TOKEN;
  }
  assert.equal(new Minion().baseUrl, "http://127.0.0.1:4747");
  assert.throws(() => new Minion({ baseUrl: "not a url" }), TypeError);
});

test("tools: listTools and callTool", async () => {
  await minion.listTools();
  assert.deepEqual(Object.fromEntries(last().query), { format: "openai" });
  await minion.listTools("mcp", { compact: true });
  assert.deepEqual(Object.fromEntries(last().query), { format: "mcp", compact: "1" });

  const result = await minion.callTool("see", { ocr: true });
  assert.deepEqual(last().body, { name: "see", arguments: { ocr: true } });
  assert.equal(result.isError, false);
  await new Minion({ baseUrl: minion.baseUrl, session: "agent-1" }).callTool("see");
  assert.deepEqual(last().body, { name: "see", arguments: {}, session: "agent-1" });
  await minion.callTool("see", {}, { session: "agent-2" });
  assert.equal(last().body.session, "agent-2");
});

test("tools: toVercelAiTools", async () => {
  const tools = await minion.toVercelAiTools({ session: "s1" });
  assert.deepEqual(Object.keys(tools), ["see", "screenshot", "files"]);
  const see = tools.see;
  assert.equal(see.description, "Read the screen.");
  assert.equal(see.parameters, see.inputSchema);
  assert.equal(see.inputSchema[Symbol.for("vercel.ai.schema")], true);
  assert.equal(see.inputSchema[Symbol.for("vercel.ai.validator")], true);
  assert.ok("validate" in see.inputSchema);
  assert.deepEqual(see.inputSchema.jsonSchema, mcpTools[0].inputSchema);

  await see.execute({ ocr: true }, { toolCallId: "1", messages: [] });
  assert.deepEqual(last().body, { name: "see", arguments: { ocr: true }, session: "s1" });

  // A failed call goes back to the model as an error result instead of throwing.
  const failed = await tools.files.execute({ path: "" }, {});
  assert.deepEqual(failed, { content: [{ type: "text", text: "path is required" }], isError: true });

  // Pinned to one desktop: the argument disappears from the schema and is sent with every call.
  const pinned = await desk.toVercelAiTools({ exclude: ["files"] });
  assert.deepEqual(Object.keys(pinned), ["see", "screenshot"]);
  assert.deepEqual(pinned.see.inputSchema.jsonSchema, object({ ocr: { type: "boolean" } }, { required: [] }));
  await pinned.see.execute({ ocr: false }, {});
  assert.deepEqual(last().body.arguments, { ocr: false, desktop: "browser-1" });
  assert.deepEqual(Object.keys(await minion.toVercelAiTools({ include: ["screenshot"] })), ["screenshot"]);

  // Images reach the model as images, in each AI SDK version's format.
  const shot = await tools.screenshot.execute({}, {});
  const content = (imagePart) => ({ type: "content", value: [imagePart, screenText] });
  const wrapped = { toolCallId: "1", input: {}, output: shot };
  const { data } = image;
  // AI SDK 5 passes the output itself and knows `media` parts.
  assert.deepEqual(tools.screenshot.toModelOutput(shot), content({ type: "media", data, mediaType: "image/png" }));
  // AI SDK 6 passes { toolCallId, input, output } and knows `image-data` parts.
  const imageData = { type: "image-data", data, mediaType: "image/png" };
  assert.deepEqual(tools.screenshot.toModelOutput(wrapped), content(imageData));
  // AI SDK 7 passes `context` to execute() and prefers `file` parts.
  await tools.screenshot.execute({}, { toolCallId: "1", messages: [], context: undefined });
  const file = { type: "file", mediaType: "image/png", data: { type: "data", data } };
  assert.deepEqual(tools.screenshot.toModelOutput(wrapped), content(file));
  // AI SDK 4
  assert.deepEqual(tools.screenshot.experimental_toToolResultContent(shot), [{ ...image }, screenText]);
  assert.deepEqual(tools.files.toModelOutput({ output: failed }), { type: "error-text", value: "path is required" });

  // jsonSchema from the `ai` package can be passed in.
  const custom = await minion.toVercelAiTools({ jsonSchema: (schema) => ({ wrapped: schema }) });
  assert.deepEqual(custom.see.inputSchema, { wrapped: mcpTools[0].inputSchema });
});
