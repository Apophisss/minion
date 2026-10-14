/**
 * minion-desktop: a zero-dependency TypeScript client for Minion, instant Linux desktops for AI agents.
 *
 * ```ts
 * import { Minion } from "minion-desktop";
 *
 * const minion = new Minion({ token: process.env.MINION_TOKEN }); // the token of `minion serve`
 * const desk = await minion.create({ profile: "browser" });
 * await desk.open("news.ycombinator.com");
 * console.log((await desk.see()).text); // the screen as text: every control has an @id
 * await desk.click("@12");
 * await desk.remove();
 * ```
 *
 * It speaks Minion's HTTP API (`minion serve`, see docs/http-api.md) with the platform's `fetch`,
 * so it needs nothing else: Node.js 18+, or any runtime with a standard `fetch`.
 */

// ---------------------------------------------------------------------------
// What the server returns. Field names are exactly those of the server's JSON.

/** `GET /api/health` */
export interface Health {
  ok: boolean;
  version: string;
  backend: string;
}

/** A desktop profile, from `GET /api/profiles`. */
export interface Profile {
  name: string;
  title: string;
  description: string;
  icon: string;
  /** The profile this one builds on, if any. */
  extends: string | null;
  /** Apps you can launch with `open()`. */
  apps: string[];
  image: string;
  builtin: boolean;
  memory: string;
}

/** `paused` means frozen: 0% CPU until the next call wakes the desktop up. */
export type DesktopState = "running" | "paused" | "stopped" | "created" | "unknown";

/** What the backend knows about a desktop (`desktops()`, `Desktop.info()`). */
export interface DesktopInfo {
  name: string;
  profile: string;
  state: DesktopState;
  backend: string;
  /** For example `"1280x800"`. */
  size: string;
  /** Unix time, in seconds. */
  created: number;
  image: string;
  id: string;
  /** Bytes in use (only with `desktops({ stats: true })`). */
  memory: number | null;
  /** CPU percent (only with `desktops({ stats: true })`). */
  cpu: number | null;
  /** Published desktop ports: desktop port → `"host:port"`. */
  ports: Record<string, string>;
}

/** The in-desktop agent's greeting (`Desktop.hello()`). */
export interface Hello {
  version: string;
  protocol: number;
  display: string;
  /** `[width, height]` in pixels. */
  screen: [number, number];
  name: string;
  profile: string;
  apps: string[];
  features: { a11y: boolean; ocr: boolean; clipboard: boolean };
  /** Seconds since the desktop started. */
  uptime: number;
  /** Seconds since the last action. */
  idle: number;
}

/** `GET /api/desktops/{name}`: the info plus the agent's hello. */
export interface DesktopDetails extends DesktopInfo {
  hello: Hello;
}

/** `Desktop.status()` */
export interface DesktopStatus extends DesktopInfo {
  uptime: number;
  idle: number;
  /** Seconds since someone last looked (a screenshot or the live view). */
  viewed: number;
  /** Bytes in use inside the desktop, when known. */
  memory: number | null;
  /** How many windows are open. */
  windows: number | null;
  recording: { enabled: boolean; steps: number; frames: number; since: number | null; last: number | null };
}

/** A top-level window. */
export interface WindowInfo {
  /** Hex X window id, for example `"0x01a00003"`. */
  id: string;
  title: string;
  /** The window class, for example `"firefox-esr"`. */
  app: string;
  pid: number;
  x: number;
  y: number;
  w: number;
  h: number;
  focused: boolean;
  states: string[];
  minimized: boolean;
}

/** A control from the accessibility tree, as `see()` reports it. */
export interface UiElement {
  /** `"@12"`: use it as an action target. */
  id: string;
  role: string;
  name: string;
  /** Center, in desktop pixels. */
  x: number;
  y: number;
  /** `[x, y, width, height]` */
  box: [number, number, number, number];
  text?: string;
  value?: string;
  states?: string[];
}

/** A line of text found by OCR. Its `id` works as an action target too. */
export interface OcrLine {
  id: string;
  text: string;
  x: number;
  y: number;
  box: [number, number, number, number];
}

/** The screen as text and structure (`Desktop.see()`). */
export interface Observation {
  /** What an agent reads: the windows, then the focused window's controls with their `@ids`. */
  text: string;
  elements: UiElement[];
  windows: WindowInfo[];
  focused: WindowInfo | null;
  ocr: OcrLine[];
  /** `[width, height]` */
  screen: [number, number];
  /** Counts of what changed, when this was a "changes since the last look" observation. */
  changes?: Record<string, unknown> | null;
}

/** One step of an `act()` call. */
export interface ActStep {
  action: string;
  ok: boolean;
  detail: string;
  /** True when an earlier action failed, so this one did not run. */
  skipped?: boolean;
}

/** How much of the screen changed during an `act()` call. */
export interface ScreenChange {
  changed: boolean;
  /** 0 to 1. */
  fraction: number;
  /** `[x, y, width, height]` of the changed area. */
  region?: [number, number, number, number];
}

/** The outcome of `act()` and of the action helpers (`click()`, `type()`, ...). */
export interface ActResult {
  ok: boolean;
  /** A short report for a model: each step, then what changed on screen. */
  summary: string;
  steps: ActStep[];
  change: ScreenChange;
  focused: WindowInfo | null;
  opened: WindowInfo[];
  closed: WindowInfo[];
  error: string | null;
  /** Seconds. */
  elapsed: number;
  /** With `{ screenshot: true }`: the settled screen, base64-encoded. */
  screenshot?: { data: string; mime: string };
  /** With `{ see: true }`: the settled screen as text. */
  see?: Observation;
}

/** `Desktop.open()` */
export interface OpenResult {
  /** The command that was started. */
  command: string;
  kind: "app" | "url" | "file" | "command";
  pid: number;
  /** The window that appeared, if any. */
  window: WindowInfo | null;
  elapsed: number;
  error?: string;
}

/** `Desktop.run()` */
export interface RunResult {
  /** The exit code; `null` for background commands. */
  code: number | null;
  stdout: string;
  stderr: string;
  timed_out: boolean;
  elapsed: number;
  /** Set for background commands. */
  pid: number | null;
}

/** `freeze()`, `thaw()`, `stop()` and `start()` */
export interface StateResult {
  ok: boolean;
  state: DesktopState;
}

/** `Desktop.screenshot()` */
export interface Screenshot {
  data: Uint8Array;
  /** `image/png`, `image/jpeg` or `image/webp`. */
  mime: string;
}

/** A pending hand-off to a human (`GET /api/desktops/{name}/handoff`). */
export interface Handoff {
  message: string;
  created: number;
  done: boolean;
  note: string | null;
}

// ---------------------------------------------------------------------------
// Actions

/**
 * Where to act: an `@id` from `see()` (`"@12"`), visible text (`"Save"`), `"x,y"` pixels,
 * `[x, y]` or `{ x, y }`.
 */
export type Target = string | [number, number] | { x: number; y: number };

export type MouseButton = "left" | "right" | "middle";
export type ScrollDirection = "up" | "down" | "left" | "right";

/** The actions Minion knows, in their object form. */
export type KnownAction =
  | {
      action: "click" | "left_click" | "right_click" | "middle_click" | "double_click" | "triple_click";
      target?: Target;
      button?: MouseButton;
      count?: number;
      /** For example `"ctrl"` or `"ctrl+shift"`. */
      modifiers?: string;
    }
  | { action: "move" | "mouse_move" | "hover"; target: Target }
  | { action: "drag" | "left_click_drag"; from: Target; to: Target; button?: MouseButton; modifiers?: string }
  | { action: "mouse_down" | "mouse_up"; target?: Target; button?: MouseButton }
  | { action: "scroll"; direction?: ScrollDirection; amount?: number; target?: Target; modifiers?: string }
  | { action: "type"; text: string; delay_ms?: number }
  | { action: "paste"; text: string }
  | { action: "fill"; target: Target; text: string }
  | { action: "select"; target: Target; option: string }
  | { action: "key" | "press" | "hotkey"; keys: string; repeat?: number }
  | { action: "hold_key"; keys: string; seconds?: number }
  | { action: "wait" | "sleep"; seconds?: number }
  | { action: "wait_for"; text: string; timeout?: number; gone?: boolean }
  | { action: "focus"; window: string }
  | { action: "open"; target: string; wait?: number };

/**
 * One action for `act()`: an object (`{ action: "click", target: "@3" }`), a shorthand
 * (`{ click: "@3" }`), a string (`"key ctrl+s"`, `"type 'hello'"`) or a Claude computer-use
 * action (`{ action: "left_click", coordinate: [640, 400] }`).
 */
export type Action = KnownAction | string | { [key: string]: unknown };

export interface ActOptions {
  /** Attach a screenshot of the settled screen to the result. */
  screenshot?: boolean;
  /** Attach `see()` of the settled screen to the result. */
  see?: boolean;
  /**
   * Throw a `MinionError` (status 422, with the result as `body`) when an action fails.
   * Default `true`. Pass `false` to get the result and check `ok` yourself.
   */
  check?: boolean;
}

export interface ClickOptions extends ActOptions {
  button?: MouseButton;
  /** 2 for a double click, 3 for a triple click. */
  count?: number;
  /** Keys to hold while clicking, for example `"ctrl"` or `"ctrl+shift"`. */
  modifiers?: string;
}

export interface KeyOptions extends ActOptions {
  /** Press the keys this many times. */
  repeat?: number;
}

export interface WaitForOptions extends ActOptions {
  /** Seconds (default 10). */
  timeout?: number;
  /** Wait for the text to disappear instead. */
  gone?: boolean;
}

export interface SeeOptions {
  /** Also read text with OCR (slower). For canvases, images and apps without an accessibility tree. */
  ocr?: boolean;
  /** Describe this window (title, app or index) instead of the focused one. */
  window?: string;
}

export interface ScreenshotOptions {
  format?: "png" | "jpeg" | "webp";
  /** Scale the image down to at most this many pixels wide. */
  maxWidth?: number;
  /** Draw the `@ids` of clickable elements on the image. */
  marks?: boolean;
  /** Draw a coordinate grid. */
  grid?: boolean;
}

export interface OpenOptions {
  /** Seconds to wait for a window to appear (default 12). */
  wait?: number;
}

export interface RunOptions {
  /** Seconds before the command is killed (default 120). */
  timeout?: number;
  /** Start it and return at once with its `pid`. */
  background?: boolean;
}

export interface HandoffOptions {
  /** Seconds to wait for the human (default 600). */
  timeout?: number;
  /** Seconds between checks (default 1). */
  interval?: number;
  signal?: AbortSignal;
}

export interface CreateOptions {
  /** `browser` (the default), `office`, `dev`, `research`, `data`, `base`, or one of your own. */
  profile?: string;
  /** Default: `<profile>-<n>`. Lowercase letters, digits, `-` and `_`. */
  name?: string;
  /** `"1280x800"` (the default) or `[width, height]`. */
  size?: string | [number, number];
}

// ---------------------------------------------------------------------------
// Tools: the same tools as Minion's MCP server, for any function-calling model

/** `openai` is Chat Completions; `openai-responses` is the Responses API. */
export type ToolFormat = "openai" | "openai-responses" | "anthropic" | "gemini" | "mcp";

/** A JSON Schema (draft 7 or 2020-12). */
export interface JsonSchema {
  type?: string | string[];
  description?: string;
  properties?: Record<string, JsonSchema>;
  required?: string[];
  items?: JsonSchema;
  enum?: unknown[];
  [key: string]: unknown;
}

/** The JSON Schema of a tool's arguments. */
export interface ObjectSchema extends JsonSchema {
  type: "object";
}

/** `listTools("mcp")`: MCP tool definitions. */
export interface McpTool {
  name: string;
  description?: string;
  inputSchema: ObjectSchema;
  annotations?: Record<string, unknown>;
  [key: string]: unknown;
}

/** `listTools("openai")`: OpenAI function tools (`chat.completions.create({ tools })`). */
export interface OpenAITool {
  type: "function";
  function: { name: string; description?: string; parameters: ObjectSchema; strict?: boolean };
}

/** `listTools("openai-responses")`: OpenAI Responses API function tools (`responses.create({ tools })`). */
export interface OpenAIResponsesTool {
  type: "function";
  name: string;
  description?: string;
  parameters: ObjectSchema;
  /** Always `false`: the schemas have optional arguments, which strict mode does not allow. */
  strict: boolean;
}

/** `listTools("anthropic")`: Anthropic tools (`messages.create({ tools })`). */
export interface AnthropicTool {
  name: string;
  description?: string;
  input_schema: ObjectSchema;
}

/** `listTools("gemini")`: Gemini function declarations. */
export interface GeminiFunctionDeclaration {
  name: string;
  description?: string;
  parameters?: JsonSchema;
  parametersJsonSchema?: JsonSchema;
  [key: string]: unknown;
}

/** The definition type `listTools()` returns for each format. */
export interface ToolDefinitions {
  openai: OpenAITool;
  "openai-responses": OpenAIResponsesTool;
  anthropic: AnthropicTool;
  gemini: GeminiFunctionDeclaration;
  mcp: McpTool;
}

export interface TextContent {
  type: "text";
  text: string;
}

export interface ImageContent {
  type: "image";
  /** Base64-encoded image. */
  data: string;
  mimeType: string;
}

export type ToolContent = TextContent | ImageContent;

/** What `callTool()` returns: MCP's tool result shape. */
export interface ToolResult {
  content: ToolContent[];
  /** True when the tool failed; `content` says why, in words meant for the model. */
  isError: boolean;
}

export interface ListToolsOptions {
  /** One `computer` tool that takes CLI-style commands, instead of the full set: fewer tokens. */
  compact?: boolean;
}

export interface CallToolOptions {
  /**
   * The agent's session. Each session has its own "current desktop", so several agents can share
   * a server. Default: the client's `session` option, else the server's default session.
   */
  session?: string;
  signal?: AbortSignal;
}

export interface VercelAiToolsOptions extends ListToolsOptions {
  /** The session for every call (see `CallToolOptions.session`). */
  session?: string;
  /**
   * Send every call to this desktop, for tools that take a `desktop` argument.
   * The argument is then hidden from the model.
   */
  desktop?: string | Desktop;
  /** Only these tools, for example `["see", "act", "screenshot"]`. */
  include?: string[];
  /** Leave these tools out, for example `["files"]`. */
  exclude?: string[];
  /**
   * `jsonSchema` from the `ai` package, to build the schemas with it. Optional: by default the
   * helper builds the same object without importing `ai`.
   */
  jsonSchema?: (schema: any) => unknown;
}

/**
 * A tool for the Vercel AI SDK (`generateText({ tools })`, `streamText`, agents), made without
 * depending on the `ai` package. It works with AI SDK 4 to 7; the `any`s keep it assignable to
 * each version's `ToolSet`.
 */
export interface VercelAiTool {
  description: string;
  /** The JSON Schema of the arguments, wrapped as the AI SDK expects (AI SDK 5 and later). */
  inputSchema: any;
  /** The same schema, under its AI SDK 4 name. */
  parameters: any;
  /** Calls the tool on the Minion server. */
  execute: (input: any, options?: any) => Promise<ToolResult>;
  /** Sends images to the model as images and failures as errors (AI SDK 5 and later). */
  toModelOutput: (options: any) => any;
  /** Sends images to the model as images (AI SDK 4). */
  experimental_toToolResultContent: (
    result: ToolResult,
  ) => Array<{ type: "text"; text: string } | { type: "image"; data: string; mimeType?: string }>;
}

// ---------------------------------------------------------------------------
// Errors

/**
 * Every failure is a `MinionError`. `status` is the HTTP status: 400 (bad request), 401 (wrong
 * token), 404 (unknown desktop or profile), 422 (the action failed), or 0 when there was no
 * response (the server is not running, the network failed, or `timeoutMs` passed).
 * The message is the server's, written so that it can be shown to a model as it is.
 */
export class MinionError extends Error {
  readonly status: number;
  /** The parsed response body; for a failed action, its `ActResult`. */
  readonly body: unknown;

  constructor(message: string, status: number, options: { body?: unknown; cause?: unknown } = {}) {
    super(message, options.cause === undefined ? undefined : { cause: options.cause });
    this.name = "MinionError";
    this.status = status;
    this.body = options.body;
  }
}

// ---------------------------------------------------------------------------
// The client

export interface MinionOptions {
  /**
   * Where `minion serve` listens. Default: `$MINION_URL`, else `http://127.0.0.1:4747`.
   * A URL with `?token=...` (as `minion serve` prints it) works too.
   */
  baseUrl?: string;
  /** The server's token (`minion serve --token ...`). Default: `$MINION_TOKEN`. */
  token?: string;
  /**
   * Abort requests that take longer than this many milliseconds. Default: no limit (creating the
   * first desktop of a profile downloads its image, which can take minutes).
   */
  timeoutMs?: number;
  /** A custom `fetch` (proxies, tests, longer timeouts). Default: `globalThis.fetch`. */
  fetch?: typeof fetch;
  /** Extra headers for every request. */
  headers?: Record<string, string>;
  /** The default session for `callTool()` and `toVercelAiTools()`: give each agent its own. */
  session?: string;
}

export interface RequestOptions {
  /** Query parameters. `undefined`, `null` and `false` are left out; `true` is sent as `1`. */
  query?: Record<string, string | number | boolean | null | undefined>;
  /** Sent as JSON. */
  body?: unknown;
  signal?: AbortSignal;
}

const DEFAULT_BASE_URL = "http://127.0.0.1:4747";

type FetchFunction = (input: string, init: RequestInit) => Promise<Response>;

/** A connection to a Minion server. Cheap to create; it holds no connection open. */
export class Minion {
  /** The server's address, without a trailing slash or token. */
  readonly baseUrl: string;
  /** The default session for tool calls, if any. */
  readonly session: string | undefined;
  readonly #token: string | undefined;
  readonly #fetch: FetchFunction;
  readonly #headers: Record<string, string>;
  readonly #timeoutMs: number | undefined;

  constructor(options: MinionOptions = {}) {
    const raw = options.baseUrl ?? env("MINION_URL") ?? DEFAULT_BASE_URL;
    let url: URL;
    try {
      url = new URL(raw);
    } catch {
      throw new TypeError(`minion-desktop: invalid baseUrl ${JSON.stringify(raw)}`);
    }
    const urlToken = url.searchParams.get("token") ?? undefined;
    url.search = "";
    url.hash = "";
    this.baseUrl = url.href.replace(/\/+$/, "");
    this.#token = options.token ?? urlToken ?? env("MINION_TOKEN");
    const f = options.fetch ?? globalThis.fetch;
    if (typeof f !== "function") {
      throw new TypeError("minion-desktop: fetch() is not available here; use Node.js 18+ or pass options.fetch");
    }
    this.#fetch = (input, init) => f(input, init);
    // X-Minion marks requests as coming from a client, not a web page (the server refuses forged ones).
    this.#headers = { "X-Minion": "1", ...options.headers };
    this.#timeoutMs = options.timeoutMs;
    this.session = options.session;
  }

  // -- server --------------------------------------------------------------

  /** `GET /api/health` */
  health(): Promise<Health> {
    return this.request("GET", "/api/health");
  }

  /** The profiles desktops can be created from. */
  profiles(): Promise<Profile[]> {
    return this.request("GET", "/api/profiles");
  }

  /** All desktops. `stats: true` adds memory and CPU use (slower). */
  desktops(options: { stats?: boolean } = {}): Promise<DesktopInfo[]> {
    return this.request("GET", "/api/desktops", { query: { stats: options.stats } });
  }

  /** Create and start a desktop. The first desktop of a profile downloads its image first. */
  async create(options: CreateOptions = {}): Promise<Desktop> {
    const body = { profile: options.profile, name: options.name, size: options.size };
    const created = await this.request<DesktopDetails>("POST", "/api/desktops", { body });
    return new Desktop(this, created.name);
  }

  /** A handle to an existing desktop. Makes no request. */
  desktop(name: string): Desktop {
    return new Desktop(this, name);
  }

  /**
   * The dashboard's URL, or with a name the live view of that desktop, where a human can watch
   * and take over. It contains the token.
   */
  viewUrl(name?: string): string {
    const path = name === undefined ? "/" : `/view/${encodeURIComponent(name)}`;
    return this.baseUrl + path + (this.#token ? `?token=${encodeURIComponent(this.#token)}` : "");
  }

  // -- tools ---------------------------------------------------------------

  /**
   * Minion's tools (the same as its MCP server's: `desktop`, `see`, `screenshot`, `act`, `open`,
   * `run`, `script`, `files`, `view`) as definitions for a function-calling API. Run them with
   * `callTool()`.
   */
  listTools<F extends ToolFormat = "openai">(
    format: F = "openai" as F,
    options: ListToolsOptions = {},
  ): Promise<Array<ToolDefinitions[F]>> {
    return this.request("GET", "/api/tools", { query: { format, compact: options.compact } });
  }

  /**
   * Run one of Minion's tools, as a model asked for it. Tool failures (a bad target, an unknown
   * desktop) come back as `isError: true` results whose text is meant for the model.
   */
  async callTool(name: string, args: Record<string, unknown> = {}, options: CallToolOptions = {}): Promise<ToolResult> {
    const result = await this.request<Partial<ToolResult> | null>("POST", "/api/tools/call", {
      body: { name, arguments: args, session: options.session ?? this.session },
      signal: options.signal,
    });
    return {
      ...result,
      content: Array.isArray(result?.content) ? result.content : [],
      isError: Boolean(result?.isError),
    };
  }

  /**
   * Minion's tools as Vercel AI SDK tools, without depending on the `ai` package:
   *
   * ```ts
   * const tools = await minion.toVercelAiTools();
   * const { text } = await generateText({ model, tools, stopWhen: stepCountIs(30), prompt });
   * ```
   *
   * Screenshots reach the model as images. A failed call (for example a bad target) is returned
   * to the model as an error result so that it can try something else; a wrong token or an
   * unreachable server throws.
   */
  async toVercelAiTools(options: VercelAiToolsOptions = {}): Promise<Record<string, VercelAiTool>> {
    const pinned = typeof options.desktop === "string" ? options.desktop : options.desktop?.name;
    const wrap = options.jsonSchema ?? aiSdkSchema;
    // AI SDK 7 passes `context` to execute(); earlier versions do not. It decides how images are sent.
    const sdk: { v7?: boolean } = {};
    const session = options.session ?? this.session;
    const tools: Record<string, VercelAiTool> = {};
    for (const raw of await this.listTools("mcp", { compact: options.compact })) {
      const def = normalizeTool(raw);
      const wanted = !options.include || options.include.includes(def.name);
      if (!def.name || !wanted || options.exclude?.includes(def.name)) continue;
      const properties = def.inputSchema.properties;
      const pin = pinned !== undefined && isRecord(properties) && "desktop" in properties;
      const schema = wrap(pin ? withoutProperty(def.inputSchema, "desktop") : def.inputSchema);
      tools[def.name] = {
        description: def.description,
        inputSchema: schema,
        parameters: schema,
        execute: async (input: unknown, execOptions?: unknown): Promise<ToolResult> => {
          let signal: AbortSignal | undefined;
          if (isRecord(execOptions)) {
            sdk.v7 = "context" in execOptions;
            signal = (execOptions["abortSignal"] as AbortSignal | undefined) ?? undefined;
          }
          const args: Record<string, unknown> = isRecord(input) ? { ...input } : {};
          if (pin) args["desktop"] = pinned;
          try {
            return await this.callTool(def.name, args, { session, signal });
          } catch (error) {
            // A rejected call goes back to the model; a wrong token or a dead server is the developer's problem.
            const status = error instanceof MinionError ? error.status : 0;
            if (status >= 400 && status < 500 && status !== 401 && status !== 403) {
              return { content: [{ type: "text", text: (error as MinionError).message }], isError: true };
            }
            throw error;
          }
        },
        toModelOutput: (arg: unknown) => toModelOutput(arg, sdk.v7 === true),
        experimental_toToolResultContent: (result: ToolResult) => {
          const parts = (result?.content ?? []).map((part) =>
            part.type === "image"
              ? { type: "image" as const, data: part.data, mimeType: part.mimeType }
              : { type: "text" as const, text: part.type === "text" ? part.text : JSON.stringify(part) },
          );
          return parts.length ? parts : [{ type: "text" as const, text: "(no output)" }];
        },
      };
    }
    return tools;
  }

  // -- raw access ----------------------------------------------------------

  /** Call any endpoint and get its JSON (or text) back. Throws `MinionError` unless the status is 2xx. */
  async request<T = unknown>(method: string, path: string, options: RequestOptions = {}): Promise<T> {
    const res = await this.requestRaw(method, path, options);
    const text = await readBody(res, (r) => r.text());
    if (!text) return null as T;
    if (!(res.headers.get("content-type") ?? "").includes("json")) return text as T;
    try {
      return JSON.parse(text) as T;
    } catch (error) {
      throw new MinionError(`${method} ${path} returned invalid JSON`, res.status, { body: text, cause: error });
    }
  }

  /** Like `request()`, but returns the `Response` (for images and other binary data). */
  async requestRaw(method: string, path: string, options: RequestOptions = {}): Promise<Response> {
    const url = new URL(this.baseUrl + (path.startsWith("/") ? path : `/${path}`));
    for (const [key, value] of Object.entries(options.query ?? {})) {
      if (value === undefined || value === null || value === false) continue;
      url.searchParams.set(key, value === true ? "1" : String(value));
    }
    const headers: Record<string, string> = { ...this.#headers };
    if (this.#token) headers["Authorization"] = `Bearer ${this.#token}`;
    const init: RequestInit = { method, headers };
    if (options.body !== undefined) {
      headers["Content-Type"] = "application/json";
      init.body = JSON.stringify(options.body);
    }
    const signal = withTimeout(options.signal, this.#timeoutMs);
    if (signal) init.signal = signal;
    let res: Response;
    try {
      res = await this.#fetch(url.href, init);
    } catch (error) {
      if (options.signal?.aborted) throw error; // the caller aborted: keep their AbortError
      throw transportError(error, `${method} ${url.pathname}`, this.baseUrl, this.#timeoutMs);
    }
    if (!res.ok) throw await httpError(res);
    return res;
  }
}

/** A handle to one desktop. Cheap: it is just a name and a client. */
export class Desktop {
  readonly minion: Minion;
  readonly name: string;

  constructor(minion: Minion, name: string) {
    this.minion = minion;
    this.name = name;
  }

  // -- looking -------------------------------------------------------------

  /** What the backend knows about the desktop. Does not wake a frozen desktop. */
  info(): Promise<DesktopInfo> {
    return this.#get("info");
  }

  /** The in-desktop agent's greeting: screen size, apps, features. */
  async hello(): Promise<Hello> {
    return (await this.#get<DesktopDetails>()).hello;
  }

  /** Uptime, idle time, memory, windows and the flight recorder's state. */
  status(): Promise<DesktopStatus> {
    return this.#get("status");
  }

  /** The open windows. */
  windows(): Promise<WindowInfo[]> {
    return this.#get("windows");
  }

  /** The screen as text: windows, then the focused window's controls with `@ids` to act on. */
  see(options: SeeOptions = {}): Promise<Observation> {
    return this.#get("see", { ocr: options.ocr, window: options.window });
  }

  /** A screenshot. Pixels in a full-size screenshot are desktop coordinates. */
  async screenshot(options: ScreenshotOptions = {}): Promise<Screenshot> {
    const res = await this.minion.requestRaw("GET", this.#path("screenshot"), {
      query: { format: options.format, max_width: options.maxWidth, marks: options.marks, grid: options.grid },
    });
    return { data: await readBody(res, bytes), mime: res.headers.get("content-type") ?? "image/png" };
  }

  // -- acting --------------------------------------------------------------

  /**
   * Run actions in order. It stops at the first failure, waits for the screen to settle and
   * reports what changed. Throws a `MinionError` (status 422) when an action fails, unless
   * `check: false`.
   */
  async act(actions: Action | Action[], options: ActOptions = {}): Promise<ActResult> {
    const result = await this.#post<ActResult>("act", {
      actions: Array.isArray(actions) ? actions : [actions],
      screenshot: options.screenshot ?? false,
      see: options.see ?? false,
    });
    if (options.check !== false && !result.ok) {
      throw new MinionError(result.error ?? result.summary, 422, { body: result });
    }
    return result;
  }

  /** Click an `@id`, text, `"x,y"` or `[x, y]`. Without a target, click where the mouse is. */
  click(target?: Target | null, options: ClickOptions = {}): Promise<ActResult> {
    const { button, count, modifiers, ...act } = options;
    return this.act({ action: "click", target: target ?? undefined, button, count, modifiers }, act);
  }

  /** Type text into the focused control. `\n` presses Return and `\t` presses Tab. */
  type(text: string, options: ActOptions = {}): Promise<ActResult> {
    return this.act({ action: "type", text }, options);
  }

  /** Paste text through the clipboard (fast for long text). */
  paste(text: string, options: ActOptions = {}): Promise<ActResult> {
    return this.act({ action: "paste", text }, options);
  }

  /** Press keys: `"Return"`, `"ctrl+s"`, `"alt+Left"`, `"ctrl+shift+t"`. */
  key(keys: string, options: KeyOptions = {}): Promise<ActResult> {
    const { repeat, ...act } = options;
    return this.act({ action: "key", keys, repeat }, act);
  }

  /** Scroll (by default down 3 notches), over a target if given. */
  scroll(
    direction: ScrollDirection = "down",
    amount?: number,
    target?: Target,
    options: ActOptions = {},
  ): Promise<ActResult> {
    return this.act({ action: "scroll", direction, amount, target }, options);
  }

  /** Replace the text of a field, found by `@id` or by its label. */
  fill(target: Target, text: string, options: ActOptions = {}): Promise<ActResult> {
    return this.act({ action: "fill", target, text }, options);
  }

  /** Pick an option of a dropdown (a `<select>`, a combo box) by its visible text. */
  select(target: Target, option: string, options: ActOptions = {}): Promise<ActResult> {
    return this.act({ action: "select", target, option }, options);
  }

  /** Drag from one target to another. */
  drag(from: Target, to: Target, options: ActOptions = {}): Promise<ActResult> {
    return this.act({ action: "drag", from, to }, options);
  }

  /** Wait until text appears on screen (or disappears, with `gone: true`). */
  waitFor(text: string, options: WaitForOptions = {}): Promise<ActResult> {
    const { timeout, gone, ...act } = options;
    return this.act({ action: "wait_for", text, timeout, gone }, act);
  }

  // -- apps, shell, clipboard ----------------------------------------------

  /**
   * Launch a profile app (`"writer"`, `"calc"`), a URL, a file in the desktop or a command, and
   * wait for its window.
   */
  open(target: string, options: OpenOptions = {}): Promise<OpenResult> {
    return this.#post("open", { target, wait: options.wait });
  }

  /** Run a shell command in the desktop (`sudo` works). */
  run(command: string | string[], options: RunOptions = {}): Promise<RunResult> {
    return this.#post("run", { command, timeout: options.timeout, background: options.background });
  }

  /** The clipboard's text. */
  async clipboard(): Promise<string> {
    return (await this.#post<{ text: string }>("clipboard", {})).text;
  }

  async setClipboard(text: string): Promise<void> {
    await this.#post("clipboard", { text });
  }

  // -- lifecycle -----------------------------------------------------------

  /** Pause every process (0% CPU). Any later call wakes the desktop up. */
  freeze(): Promise<StateResult> {
    return this.#post("freeze");
  }

  thaw(): Promise<StateResult> {
    return this.#post("thaw");
  }

  stop(): Promise<StateResult> {
    return this.#post("stop");
  }

  start(): Promise<StateResult> {
    return this.#post("start");
  }

  /** Copy this desktop's disk state into a new desktop (its apps start fresh). */
  async fork(name?: string): Promise<Desktop> {
    const info = await this.#post<DesktopInfo>("fork", { name });
    return new Desktop(this.minion, info.name);
  }

  /** Save the disk state. Returns the tag. */
  async snapshot(tag?: string): Promise<string> {
    return (await this.#post<{ tag: string }>("snapshot", { tag })).tag;
  }

  /** Go back to a snapshot (apps start fresh). */
  async restore(tag: string): Promise<void> {
    await this.#post("restore", { tag });
  }

  /** Delete the desktop. */
  async remove(): Promise<void> {
    await this.minion.request("DELETE", this.#path());
  }

  // -- humans and the flight recorder ---------------------------------------

  /** The flight recorder as an HTML page: every action with a thumbnail. */
  replay(): Promise<string> {
    return this.minion.request("GET", this.#path("replay"));
  }

  /** The flight recorder as an animated GIF. */
  async replayGif(): Promise<Uint8Array> {
    const res = await this.minion.requestRaw("GET", this.#path("replay"), { query: { format: "gif" } });
    return readBody(res, bytes);
  }

  /** The live view, where a human can watch and take over. It contains the token. */
  viewUrl(): string {
    return this.minion.viewUrl(this.name);
  }

  /**
   * Ask the human watching the live view (`viewUrl()`) to take over, for a login or a CAPTCHA,
   * and wait until they press Done. Returns their note, or `null` if the time ran out.
   */
  async handoff(message: string, options: HandoffOptions = {}): Promise<string | null> {
    const path = this.#path("handoff");
    const { signal } = options;
    await this.minion.request("POST", path, { body: { message }, signal });
    const deadline = Date.now() + (options.timeout ?? 600) * 1000;
    try {
      while (Date.now() < deadline) {
        const pending = await this.minion.request<Handoff | null>("GET", path, { signal });
        if (pending?.done) return pending.note ?? "";
        await sleep(Math.min((options.interval ?? 1) * 1000, Math.max(0, deadline - Date.now())), signal);
      }
      return null;
    } finally {
      await this.minion.request("DELETE", path).catch(() => undefined);
    }
  }

  /** `minion.toVercelAiTools()` with every call sent to this desktop. */
  toVercelAiTools(options: Omit<VercelAiToolsOptions, "desktop"> = {}): Promise<Record<string, VercelAiTool>> {
    return this.minion.toVercelAiTools({ ...options, desktop: this });
  }

  toString(): string {
    return this.name;
  }

  toJSON(): { name: string } {
    return { name: this.name };
  }

  #path(op?: string): string {
    return `/api/desktops/${encodeURIComponent(this.name)}${op ? `/${op}` : ""}`;
  }

  #get<T>(op?: string, query?: RequestOptions["query"]): Promise<T> {
    return this.minion.request<T>("GET", this.#path(op), { query });
  }

  #post<T>(op: string, body: unknown = {}): Promise<T> {
    return this.minion.request<T>("POST", this.#path(op), { body });
  }
}

// ---------------------------------------------------------------------------
// Helpers

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function env(name: string): string | undefined {
  try {
    const value = (globalThis as { process?: { env?: Record<string, string | undefined> } }).process?.env?.[name];
    return value || undefined;
  } catch {
    return undefined; // e.g. Deno without --allow-env
  }
}

function bytes(res: Response): Promise<Uint8Array> {
  return res.arrayBuffer().then((buffer) => new Uint8Array(buffer));
}

async function readBody<T>(res: Response, read: (res: Response) => Promise<T>): Promise<T> {
  try {
    return await read(res);
  } catch (error) {
    throw new MinionError(`the response was cut off (${describe(error)})`, 0, { cause: error });
  }
}

async function httpError(res: Response): Promise<MinionError> {
  let text = "";
  try {
    text = await res.text();
  } catch {
    // keep the status alone
  }
  let body: unknown = text || undefined;
  let message = "";
  try {
    body = JSON.parse(text);
    if (isRecord(body) && typeof body["error"] === "string") message = body["error"];
  } catch {
    // not JSON
  }
  if (!message) message = text.trim().slice(0, 500) || `HTTP ${res.status} ${res.statusText}`.trim();
  return new MinionError(message, res.status, { body });
}

/** The most useful words about a fetch failure: undici puts the reason (ECONNREFUSED, ...) in `cause`. */
function describe(error: unknown): string {
  const cause = isRecord(error) ? error["cause"] : undefined;
  if (isRecord(cause)) {
    if (typeof cause["code"] === "string") return cause["code"];
    if (typeof cause["message"] === "string" && cause["message"]) return cause["message"];
  }
  return error instanceof Error ? error.message : String(error);
}

function transportError(error: unknown, what: string, baseUrl: string, timeoutMs: number | undefined): MinionError {
  if (isRecord(error) && error["name"] === "TimeoutError") {
    return new MinionError(`${what} timed out after ${timeoutMs} ms`, 0, { cause: error });
  }
  const detail = describe(error);
  if (detail === "UND_ERR_HEADERS_TIMEOUT" || detail === "UND_ERR_BODY_TIMEOUT") {
    return new MinionError(
      `${what}: no answer within fetch's time limit (${detail}). Node's fetch gives up after 5 minutes; ` +
        "pass a fetch with a longer timeout (options.fetch) for slow calls.",
      0,
      { cause: error },
    );
  }
  return new MinionError(`cannot reach the Minion server at ${baseUrl} (${detail}). Is \`minion serve\` running?`, 0, {
    cause: error,
  });
}

function withTimeout(signal: AbortSignal | undefined, timeoutMs: number | undefined): AbortSignal | undefined {
  if (!timeoutMs || timeoutMs <= 0) return signal;
  const timeout = AbortSignal.timeout(timeoutMs);
  if (!signal) return timeout;
  if (typeof AbortSignal.any === "function") return AbortSignal.any([signal, timeout]);
  const controller = new AbortController(); // Node.js 18 has no AbortSignal.any()
  for (const s of [signal, timeout]) {
    if (s.aborted) controller.abort(s.reason);
    else s.addEventListener("abort", () => controller.abort(s.reason), { once: true });
  }
  return controller.signal;
}

function sleep(ms: number, signal?: AbortSignal): Promise<void> {
  return new Promise((resolve, reject) => {
    if (signal?.aborted) return reject(signal.reason);
    const onAbort = () => {
      clearTimeout(timer);
      reject(signal?.reason);
    };
    const timer = setTimeout(() => {
      signal?.removeEventListener("abort", onAbort);
      resolve();
    }, ms);
    signal?.addEventListener("abort", onAbort, { once: true });
  });
}

/** Name, description and argument schema from a tool definition in any of the formats. */
function normalizeTool(raw: unknown): { name: string; description: string; inputSchema: JsonSchema } {
  const outer = isRecord(raw) ? raw : {};
  const def = isRecord(outer["function"]) ? outer["function"] : outer; // OpenAI nests it
  const schema = def["inputSchema"] ?? def["input_schema"] ?? def["parameters"] ?? def["parametersJsonSchema"];
  return {
    name: typeof def["name"] === "string" ? def["name"] : "",
    description: typeof def["description"] === "string" ? def["description"] : "",
    inputSchema: isRecord(schema) ? (schema as JsonSchema) : { type: "object", properties: {} },
  };
}

function withoutProperty(schema: JsonSchema, key: string): JsonSchema {
  const properties = { ...schema.properties };
  delete properties[key];
  const out: JsonSchema = { ...schema, properties };
  if (Array.isArray(schema.required)) out.required = schema.required.filter((name) => name !== key);
  return out;
}

/**
 * The object `jsonSchema()` from the `ai` package returns. AI SDK 4 to 7 recognize it by these
 * registered symbols, so no import is needed. Without `validate`, the SDK passes the model's
 * arguments through and the Minion server checks them.
 */
function aiSdkSchema(schema: JsonSchema): unknown {
  return {
    [Symbol.for("vercel.ai.schema")]: true,
    [Symbol.for("vercel.ai.validator")]: true,
    _type: undefined,
    jsonSchema: schema,
    validate: undefined,
  };
}

function isToolResult(value: unknown): value is ToolResult {
  return isRecord(value) && Array.isArray(value["content"]);
}

/**
 * A ToolResult in the shape the AI SDK sends to the model. AI SDK 5 calls it with the result and
 * knows `media` parts; AI SDK 6 calls it with `{ output }` and knows `image-data`; AI SDK 7 also
 * calls it with `{ output }` and prefers `file` parts.
 */
function toModelOutput(arg: unknown, v7: boolean): unknown {
  const v5 = isToolResult(arg);
  const result = v5 ? arg : isRecord(arg) ? arg["output"] : undefined;
  if (!isToolResult(result)) return { type: "json", value: result ?? null };
  const text = result.content.flatMap((part) => (part.type === "text" ? [part.text] : [])).join("\n");
  if (result.isError) return { type: "error-text", value: text || "The tool call failed." };
  if (!result.content.length) return { type: "text", value: "(no output)" };
  return {
    type: "content",
    value: result.content.map((part) => {
      if (part.type === "image") {
        if (v5) return { type: "media", data: part.data, mediaType: part.mimeType };
        if (v7) return { type: "file", mediaType: part.mimeType, data: { type: "data", data: part.data } };
        return { type: "image-data", data: part.data, mediaType: part.mimeType };
      }
      return { type: "text", text: part.type === "text" ? part.text : JSON.stringify(part) };
    }),
  };
}
