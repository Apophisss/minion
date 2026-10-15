#!/usr/bin/env node
// `npx -y minion-desktop mcp`: starts Minion's MCP server for MCP clients that expect an npx command.
//
// Minion is a Python program, so this launcher runs its `minion` command with the same arguments: from PyPI with
// uvx, else pipx, in the version of this npm package (npm and PyPI releases stay in lockstep), else an installed
// `minion`. Minion gets this process's stdin, stdout and stderr as they are, so MCP over stdio passes straight
// through. The launcher itself never writes to stdout. No dependencies; Node.js 18+ on macOS, Linux and Windows.
//
//   npx -y minion-desktop mcp [--compact] [--no-images]     # or any other `minion` command: --version, doctor...
//   MINION_SPEC=git+https://github.com/apophisss/minion npx -y minion-desktop mcp   # another version, or a fork

import { spawn } from "node:child_process";
import { accessSync, constants as fsConstants, readFileSync, statSync } from "node:fs";
import { homedir, constants as osConstants } from "node:os";
import { delimiter, join } from "node:path";

const windows = process.platform === "win32";
const args = process.argv.slice(2);
const { version } = JSON.parse(readFileSync(new URL("../package.json", import.meta.url), "utf8"));
const spec = process.env.MINION_SPEC || `minion-desktop==${version}`;

// Apps started from the desktop often give servers a short PATH, so also look where uv's installer puts uvx
// (~/.cargo/bin before uv 0.5), and where `uv tool install` and pipx put commands.
const userBin = join(homedir(), ".local", "bin");
const cargoBin = join(homedir(), ".cargo", "bin");

const INSTALL_UV = windows
  ? 'powershell -c "irm https://astral.sh/uv/install.ps1 | iex"'
  : "curl -LsSf https://astral.sh/uv/install.sh | sh";
const INSTALL_MINION = windows
  ? "irm https://raw.githubusercontent.com/apophisss/minion/main/install.ps1 | iex"
  : "curl -fsSL https://raw.githubusercontent.com/apophisss/minion/main/install.sh | sh";

/** The full path of the executable `name`, on PATH or else in the `extra` folders, or null. */
function find(name, extra) {
  const file = windows ? `${name}.exe` : name; // a .cmd or .bat would need a shell
  const path = (process.env.PATH ?? "").split(delimiter).map((dir) => dir.replace(/^"(.*)"$/, "$1"));
  for (const dir of [...path, ...extra]) {
    if (!dir) continue;
    const candidate = join(dir, file);
    try {
      accessSync(candidate, fsConstants.X_OK);
      if (statSync(candidate).isFile()) return candidate;
    } catch {
      // not there, or not executable
    }
  }
  return null;
}

/** [executable, arguments] for the first way of running Minion that this computer offers, or null. */
function command() {
  const uvx = find("uvx", [userBin, cargoBin]);
  if (uvx) return [uvx, ["--from", spec, "minion", ...args]];
  const pipx = find("pipx", [userBin]);
  if (pipx) return [pipx, ["run", "--spec", spec, "minion", ...args]];
  const minion = find("minion", [userBin]);
  if (minion) return [minion, args];
  return null;
}

const found = command();
if (!found) {
  process.stderr.write(
    "minion-desktop: Minion is a Python program, and none of uvx, pipx or an installed minion command was found.\n" +
      `Install uv, which brings its own Python, then try again:\n\n  ${INSTALL_UV}\n\n` +
      `Or install Minion with its one-line installer${windows ? " (in PowerShell)" : ""}, which sets up uv too:\n\n` +
      `  ${INSTALL_MINION}\n\n` +
      "Desktops also need Docker, OrbStack or Podman: https://github.com/apophisss/minion/blob/main/docs/install.md\n",
  );
  process.exitCode = 1;
} else {
  const [file, argv] = found;
  const child = spawn(file, argv, { stdio: "inherit", windowsHide: true });
  child.on("error", (error) => {
    process.stderr.write(`minion-desktop: could not start ${file}: ${error.message}\n`);
    process.exitCode = 1;
  });
  child.on("exit", (code, signal) => process.exit(code ?? 128 + (osConstants.signals[signal] ?? 0)));
  // Stopping the launcher stops Minion. On Windows, Ctrl+C and closing the console reach Minion by themselves,
  // and child.kill() could only end it abruptly, so there the launcher just waits for Minion to finish.
  for (const signal of ["SIGINT", "SIGTERM", "SIGHUP"]) {
    process.on(signal, () => {
      if (!windows) child.kill(signal);
    });
  }
}
