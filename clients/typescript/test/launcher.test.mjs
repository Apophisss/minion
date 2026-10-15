// Offline tests for bin/minion-desktop.mjs, the launcher behind `npx minion-desktop mcp`. Fake uvx, pipx and
// minion commands on a temporary PATH report how they were started, then copy stdin to stdout. HOME is a
// temporary folder too, so that the real ~/.local/bin stays out of the way.
//
//   npm test        (runs this file and client.test.mjs with node --test)

import assert from "node:assert/strict";
import { spawn } from "node:child_process";
import { chmodSync, mkdirSync, mkdtempSync, readFileSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { after, test } from "node:test";
import { fileURLToPath } from "node:url";

const launcher = fileURLToPath(new URL("../bin/minion-desktop.mjs", import.meta.url));
const { version } = JSON.parse(readFileSync(new URL("../package.json", import.meta.url), "utf8"));
// With a timeout, a broken launcher fails a test instead of hanging it.
const options = { skip: process.platform === "win32" && "the fake commands are shell scripts", timeout: 20_000 };

const root = mkdtempSync(join(tmpdir(), "minion-launcher-"));
const running = new Set();
after(() => {
  for (const child of running) child.kill("SIGKILL");
  rmSync(root, { recursive: true, force: true });
});

// The fake command: one JSON line saying how it was started, then stdin copied to stdout. It exits with
// $FAKE_EXIT once stdin ends. On SIGINT, SIGTERM or SIGHUP it says so, then dies of that signal.
const fake = join(root, "fake.mjs");
writeFileSync(
  fake,
  `const [command, ...args] = process.argv.slice(2);
for (const signal of ["SIGINT", "SIGTERM", "SIGHUP"]) {
  process.once(signal, () => process.stdout.write(\`got \${signal}\\n\`, () => process.kill(process.pid, signal)));
}
process.stdout.write(JSON.stringify({ command, args }) + "\\n");
process.stdin.pipe(process.stdout);
process.stdin.on("end", () => (process.exitCode = Number(process.env.FAKE_EXIT ?? 0)));
`,
);

const mkdir = (...parts) => {
  const dir = join(...parts);
  mkdirSync(dir, { recursive: true });
  return dir;
};
let folders = 0;
const folder = () => mkdir(root, String(folders++));
const quote = (text) => `'${text.replaceAll("'", "'\\''")}'`;

/** Puts fake commands into `dir` (as shell scripts that run the fake with their own path) and returns `dir`. */
function fakes(dir, ...names) {
  for (const name of names) {
    writeFileSync(join(dir, name), `#!/bin/sh\nexec ${quote(process.execPath)} ${quote(fake)} "$0" "$@"\n`);
    chmodSync(join(dir, name), 0o755);
  }
  return dir;
}

/** Runs the launcher with only `path` on PATH and `home` as HOME. */
function launch(args, { path, home = folder(), env = {}, input } = {}) {
  const child = spawn(process.execPath, [launcher, ...args], { env: { PATH: path, HOME: home, ...env } });
  running.add(child);
  child.on("exit", () => running.delete(child));
  const result = { stdout: "", stderr: "" };
  child.stdout.setEncoding("utf8").on("data", (chunk) => (result.stdout += chunk));
  child.stderr.setEncoding("utf8").on("data", (chunk) => (result.stderr += chunk));
  if (input !== undefined) child.stdin.end(input);
  const started = new Promise((resolve) => child.stdout.on("data", () => result.stdout.includes("\n") && resolve()));
  const done = new Promise((resolve) => child.on("close", (code, signal) => resolve({ ...result, code, signal })));
  return { child, started, done };
}

/** The first line of the fake's output: { command, args }. */
const call = (stdout) => JSON.parse(stdout.split("\n")[0]);

test("uvx runs this version of minion-desktop, and stdin and stdout pass straight through", options, async () => {
  const path = fakes(folder(), "uvx", "pipx", "minion");
  const message = '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{}}';
  const { code, signal, stdout, stderr } = await launch(["mcp", "--compact"], { path, input: `${message}\n` }).done;
  assert.deepEqual(call(stdout), {
    command: join(path, "uvx"),
    args: ["--from", `minion-desktop==${version}`, "minion", "mcp", "--compact"],
  });
  assert.equal(stdout, `${JSON.stringify(call(stdout))}\n${message}\n`); // nothing from the launcher itself
  assert.equal(stderr, "");
  assert.deepEqual([code, signal], [0, null]);
});

test("the exit code is Minion's", options, async () => {
  const path = fakes(folder(), "uvx");
  const { code } = await launch(["doctor"], { path, input: "", env: { FAKE_EXIT: "3" } }).done;
  assert.equal(code, 3);
});

test("MINION_SPEC picks what uvx runs", options, async () => {
  const path = fakes(folder(), "uvx");
  const env = { MINION_SPEC: "git+https://github.com/apophisss/minion@main" };
  const { stdout } = await launch(["mcp"], { path, input: "", env }).done;
  assert.deepEqual(call(stdout).args, ["--from", "git+https://github.com/apophisss/minion@main", "minion", "mcp"]);
});

test("uvx in ~/.local/bin or ~/.cargo/bin when it isn't on PATH", options, async () => {
  const home = folder();
  const path = fakes(folder(), "pipx");
  const uvx = async () => call((await launch(["mcp"], { path, home, input: "" }).done).stdout).command;
  const cargo = fakes(mkdir(home, ".cargo", "bin"), "uvx");
  assert.equal(await uvx(), join(cargo, "uvx"));
  const local = fakes(mkdir(home, ".local", "bin"), "uvx");
  assert.equal(await uvx(), join(local, "uvx")); // ~/.local/bin comes before ~/.cargo/bin
});

test("pipx when there is no uvx", options, async () => {
  const path = fakes(folder(), "pipx", "minion");
  writeFileSync(join(path, "uvx"), "not a program"); // not executable, so it doesn't count
  const { stdout, code } = await launch(["mcp"], { path, input: "" }).done;
  assert.deepEqual(call(stdout), {
    command: join(path, "pipx"),
    args: ["run", "--spec", `minion-desktop==${version}`, "minion", "mcp"],
  });
  assert.equal(code, 0);
});

test("an installed minion when there is neither uvx nor pipx", options, async () => {
  const path = fakes(folder(), "minion");
  const { stdout } = await launch(["mcp", "--no-images"], { path, input: "" }).done;
  assert.deepEqual(call(stdout), { command: join(path, "minion"), args: ["mcp", "--no-images"] });
});

test("without uvx, pipx or minion: how to install uv or Minion, and exit code 1", options, async () => {
  const { code, stdout, stderr } = await launch(["mcp"], { path: folder(), input: "" }).done;
  assert.equal(code, 1);
  assert.equal(stdout, "");
  assert.match(stderr, /none of uvx, pipx or an installed minion command was found/);
  assert.ok(stderr.includes("curl -LsSf https://astral.sh/uv/install.sh | sh"), stderr);
  assert.ok(stderr.includes("curl -fsSL https://raw.githubusercontent.com/apophisss/minion/main/install.sh | sh"));
});

for (const [signal, code] of [["SIGINT", 130], ["SIGTERM", 143], ["SIGHUP", 129]]) {
  test(`${signal} reaches Minion, and the launcher exits with 128 + the signal's number`, options, async () => {
    const path = fakes(folder(), "uvx");
    const run = launch(["mcp"], { path }); // stdin stays open, as with an MCP client
    await run.started;
    run.child.kill(signal);
    const result = await run.done;
    assert.match(result.stdout, new RegExp(`\\ngot ${signal}\\n$`));
    assert.deepEqual([result.code, result.signal], [code, null]);
  });
}
