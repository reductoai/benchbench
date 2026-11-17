// Runs one Parse Judge provider parse or judge call. Copied into a pinned parsejudge checkout at
// packages/core/.benchbench/ by the Python harness so that it uses the exact upstream adapters and judge.
// Usage: node parsejudge-bridge.ts <request.json>  -> prints one JSON result line.
import { createHash } from "node:crypto";
import { readFileSync } from "node:fs";
import { Effect, Option } from "effect";
import { FetchHttpClient } from "effect/http";
import { findPreset, JUDGE_VERSION, judgePage, PRESETS, PROVIDERS } from "../src/index.ts";
import type { ParseOutput } from "../src/provider.ts";
import { JUDGE_VERSION as PNG_VERSION, judgePage as judgePagePng } from "../src/judge.benchbench-png.ts";

type ParseRequest = {
  op: "parse";
  presetId: string;
  imageUrl: string;
  imagePath: string;
  timeoutSec?: number;
  pollSec?: number;
};
type JudgeRequest = {
  op: "judge";
  pageId: string;
  imagePath: string;
  markdownByPreset: Record<string, string>;
  models: string[];
  reasoningEffort: "low" | "medium" | "high";
  baseUrl?: string;
  // "png" (default): compare-v4 without the PDF link-layer URL clause. "upstream": compare-v4 as published.
  promptVariant?: "png" | "upstream";
  // Gemini per-image media resolution, sent through the native API (see geminiNative).
  geminiMediaResolution?: string;
};

type PresetsRequest = { op: "presets" };

// BenchBench presets that turn on each vendor's documented formula output (2026-11-08). New ids, so parses
// from the pinned presets (no formula output) stay under their old ids and are never mixed with these.
const base = (id: string) => {
  const preset = PRESETS.find((p) => p.id === id);
  if (preset === undefined) throw new Error(`pinned preset ${id} missing`);
  return preset;
};
const azure = base("azure_layout_high_res");
const extend = base("extend_performance_agentic");
const EXTRA_PRESETS = [
  {
    ...azure,
    id: "azure_layout_high_res_formulas",
    label: "Azure Document Intelligence Layout (high-res, formulas)",
    mode: "Layout, high resolution, formulas add-on",
    config: { ...azure.config, features: ["ocrHighResolution", "formulas"] },
    listPriceUsdPerPage: 0.022,
  },
  {
    ...extend,
    id: "extend_performance_agentic_formulas",
    label: "Extend Performance (agentic, formulas)",
    mode: "Performance v2.0.0, agentic, formulas",
    config: {
      ...extend.config,
      engineVersion: "2.0.0",
      blockOptions: { ...(extend.config.blockOptions as Record<string, unknown>), formulas: { enabled: true } },
    },
  },
] as typeof PRESETS;
const ALL_PRESETS = [...PRESETS, ...EXTRA_PRESETS];
const presetById = (id: string) => findPreset(id) ?? EXTRA_PRESETS.find((p) => p.id === id);

const request = JSON.parse(readFileSync(process.argv[2] ?? "", "utf8")) as ParseRequest | JudgeRequest | PresetsRequest;

const credentialsFor = (keys: ReadonlyArray<string>) =>
  Object.fromEntries(keys.map((key) => [key, process.env[key] ?? ""]));

const parse = (req: ParseRequest) =>
  Effect.gen(function* () {
    const found = presetById(req.presetId);
    if (found === undefined) return yield* Effect.fail(new Error(`unknown preset ${req.presetId}`));
    const preset = found.id === "datalab_accurate"
      ? { ...found, config: { ...found.config, disable_image_extraction: false, disable_image_captions: false } }
      : found;
    const adapter = PROVIDERS[preset.provider];
    const credentials = credentialsFor(adapter.credentialKeys);
    const page = {
      imageUrl: req.imageUrl,
      image: Effect.sync(() => new Uint8Array(readFileSync(req.imagePath))),
    };
    const started = Date.now();
    const submission = yield* adapter.submit(page, preset.config, credentials);
    let output = submission._tag === "Done" ? submission.output : undefined;
    const deadline = started + (req.timeoutSec ?? 900) * 1000;
    let pollRetries = 0;
    while (output === undefined) {
      if (submission._tag !== "Pending" || adapter.poll === undefined) {
        return yield* Effect.fail(new Error("provider returned a pending job without a poll function"));
      }
      if (Date.now() > deadline) return yield* Effect.fail(new Error(`timeout after ${req.timeoutSec ?? 900}s`));
      yield* Effect.sleep(`${req.pollSec ?? 2} seconds`);
      // A retryable poll error (a 429 on the status endpoint) must not abandon a job the vendor is still running.
      const polled = yield* adapter.poll(submission.job, credentials).pipe(
        Effect.map(Option.some),
        Effect.catch((error) =>
          (error as { retryable?: boolean }).retryable && pollRetries < 30
            ? Effect.succeed(Option.none<Option.Option<ParseOutput>>())
            : Effect.fail(error),
        ),
      );
      if (Option.isNone(polled)) {
        pollRetries += 1;
        yield* Effect.sleep(`${Math.min(60, 2 ** pollRetries)} seconds`);
        continue;
      }
      if (Option.isSome(polled.value)) output = polled.value.value;
    }
    return {
      ok: true,
      presetId: preset.id,
      provider: preset.provider,
      config: preset.config,
      listPriceUsdPerPage: preset.listPriceUsdPerPage,
      markdown: output.markdown,
      raw: output.raw,
      reportedCost: output.reportedCost ?? null,
      warning: output.warning ?? null,
      latencyMs: Date.now() - started,
    };
  });

type Exchange = { url: string; method: string; request: unknown; status: number; response: string };

/** Records every HTTP call the judge makes (request body with base64 images replaced by sha256 and size;
 * the Authorization header is never kept) so the raw model output is saved next to each verdict. */
const recordFetch = (exchanges: Array<Exchange>) => {
  const inner = globalThis.fetch;
  // Wraps the fetch that FetchHttpClient uses; outside Effect on purpose so the pinned judge is unchanged.
  // @effect-diagnostics-next-line asyncFunction:off
  globalThis.fetch = (async (input: RequestInfo | URL, init?: RequestInit) => {
    // @effect-diagnostics-next-line globalFetch:off
    const res = await inner(input, init);
    const text = await res.clone().text();
    const body = typeof init?.body === "string" ? init.body : init?.body instanceof Uint8Array ? new TextDecoder().decode(init.body) : "";
    let request: unknown = body;
    try {
      const ref = (b64: string) => {
        const buf = Buffer.from(b64, "base64");
        return { sha256: createHash("sha256").update(buf).digest("hex"), bytes: buf.length };
      };
      request = JSON.parse(body, (k, v) =>
        typeof v !== "string"
          ? v
          : v.startsWith("data:image/")
            ? ref(v.split(",")[1] ?? "")
            : k === "data" && v.length > 256
              ? ref(v)
              : v,
      );
    } catch {}
    const url = input instanceof Request ? input.url : String(input);
    exchanges.push({ url, method: init?.method ?? "GET", request, status: res.status, response: text });
    return res;
  }) as typeof fetch;
};

type NativeAnswer = {
  modelVersion?: string;
  candidates?: Array<{ finishReason?: string; content?: { parts?: Array<{ text?: string; thought?: boolean }> } }>;
  usageMetadata?: {
    promptTokenCount?: number;
    candidatesTokenCount?: number;
    thoughtsTokenCount?: number;
    totalTokenCount?: number;
    promptTokensDetails?: unknown;
  };
};

/** Sends Gemini judge calls to the native generateContent API, the only Gemini API that takes a per-image
 * media resolution (the OpenAI-compatible endpoint ignores `detail`), and returns the answer as a chat
 * completion so the pinned judge is unchanged. Installed over recordFetch, so the native call is recorded. */
const geminiNative = (level: string) => {
  const inner = globalThis.fetch;
  // @effect-diagnostics-next-line asyncFunction:off
  globalThis.fetch = (async (input: RequestInfo | URL, init?: RequestInit) => {
    const url = input instanceof Request ? input.url : String(input);
    if (!url.startsWith("https://generativelanguage.googleapis.com/") || !url.endsWith("/openai/chat/completions")) {
      return inner(input, init);
    }
    const raw = typeof init?.body === "string" ? init.body : new TextDecoder().decode(init?.body as Uint8Array);
    const chat = JSON.parse(raw) as {
      model: string;
      reasoning_effort?: string;
      response_format?: { json_schema?: { schema?: unknown } };
      messages: Array<{ content: string | Array<{ type: string; text?: string; image_url?: { url: string } }> }>;
    };
    const parts = chat.messages.flatMap((m) =>
      typeof m.content === "string"
        ? [{ text: m.content }]
        : m.content.map((c) => {
            if (c.type !== "image_url") return { text: c.text ?? "" };
            const [head = "", data = ""] = (c.image_url?.url ?? "").split(",");
            const mimeType = head.slice("data:".length, head.indexOf(";"));
            return { inlineData: { mimeType, data }, mediaResolution: { level } };
          }),
    );
    const native = {
      contents: [{ role: "user", parts }],
      generationConfig: {
        responseMimeType: "application/json",
        responseJsonSchema: chat.response_format?.json_schema?.schema,
        ...(chat.reasoning_effort ? { thinkingConfig: { thinkingLevel: chat.reasoning_effort } } : {}),
      },
    };
    const key = (new Headers(init?.headers).get("authorization") ?? "").replace(/^Bearer /i, "");
    const res = await inner(`https://generativelanguage.googleapis.com/v1beta/models/${chat.model}:generateContent`, {
      method: "POST",
      headers: { "content-type": "application/json", "x-goog-api-key": key },
      body: JSON.stringify(native),
      signal: init?.signal ?? null,
    });
    const text = await res.text();
    const json = { "content-type": "application/json" };
    if (res.status !== 200) return new Response(text, { status: res.status, headers: json });
    const out = JSON.parse(text) as NativeAnswer;
    const cand = out.candidates?.[0];
    const content = (cand?.content?.parts ?? [])
      .filter((p) => !p.thought && typeof p.text === "string")
      .map((p) => p.text)
      .join("");
    const u = out.usageMetadata ?? {};
    const completion = {
      model: out.modelVersion ?? chat.model,
      choices: [{ finish_reason: cand?.finishReason ?? null, message: { content } }],
      usage: {
        prompt_tokens: u.promptTokenCount ?? 0,
        completion_tokens: (u.candidatesTokenCount ?? 0) + (u.thoughtsTokenCount ?? 0),
        total_tokens: u.totalTokenCount ?? 0,
        completion_tokens_details: { reasoning_tokens: u.thoughtsTokenCount ?? 0 },
        prompt_tokens_details: u.promptTokensDetails,
        media_resolution: level,
      },
    };
    return new Response(JSON.stringify(completion), { status: 200, headers: json });
  }) as typeof fetch;
};

/** Anthropic's OpenAI-compatible endpoint rejects minimum/maximum on integer schema fields, so they are
 * dropped from the request schema; the judge still decodes and checks the 1-10 range on the answer. */
const anthropicCompat = () => {
  const inner = globalThis.fetch;
  // @effect-diagnostics-next-line asyncFunction:off
  globalThis.fetch = (async (input: RequestInfo | URL, init?: RequestInit) => {
    const url = input instanceof Request ? input.url : String(input);
    if (!url.startsWith("https://api.anthropic.com/") || !init?.body) return inner(input, init);
    const raw = typeof init.body === "string" ? init.body : new TextDecoder().decode(init.body as Uint8Array);
    const body = JSON.parse(raw, (k, v) => (k === "minimum" || k === "maximum" ? undefined : v));
    return inner(input, { ...init, body: JSON.stringify(body) });
  }) as typeof fetch;
};

const judge = (req: JudgeRequest) =>
  Effect.gen(function* () {
    const exchanges: Array<Exchange> = [];
    recordFetch(exchanges);
    if (req.geminiMediaResolution) geminiNative(req.geminiMediaResolution);
    anthropicCompat();
    const usage: Array<{ model: string; usage: unknown }> = [];
    const token = process.env.JUDGE_API_KEY ?? process.env.OPENAI_API_KEY ?? "";
    const started = Date.now();
    const upstream = req.promptVariant === "upstream";
    const verdicts = yield* (upstream ? judgePage : judgePagePng)(
      {
        token: Effect.succeed(token),
        models: req.models,
        reasoningEffort: req.reasoningEffort,
        baseUrl: req.baseUrl ?? "https://api.openai.com/v1",
        onUsage: (model, u) => Effect.sync(() => void usage.push({ model, usage: u })),
      },
      { pageId: req.pageId, imagePng: new Uint8Array(readFileSync(req.imagePath)), markdownByPreset: req.markdownByPreset },
    );
    return {
      ok: true,
      judgeVersion: upstream ? JUDGE_VERSION : PNG_VERSION,
      verdicts,
      usage,
      exchanges,
      latencyMs: Date.now() - started,
    };
  });

const program = (
  request.op === "presets"
    ? Effect.succeed({ ok: true, presets: ALL_PRESETS })
    : request.op === "parse"
      ? parse(request)
      : judge(request)
) as Effect.Effect<unknown, unknown, never>;

Effect.runPromise(program.pipe(Effect.provide(FetchHttpClient.layer) as never)).then(
  (result) => process.stdout.write(`${JSON.stringify(result)}\n`),
  (error: unknown) => {
    const e = error as { message?: string; retryable?: boolean; _tag?: string };
    process.stdout.write(
      `${JSON.stringify({ ok: false, error: e?.message ?? String(error), retryable: e?.retryable ?? false, tag: e?._tag ?? null })}\n`,
    );
    process.exitCode = 1;
  },
);
