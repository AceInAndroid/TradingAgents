import { execFile } from "node:child_process";
import { access } from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";

const PLUGIN_ID = "tradingagents-bailian";
const TOOL_NAME = "run_tradingagents";
const PRESETS = ["balanced", "fast", "coder", "glm", "kimi"] as const;
const ANALYSTS = ["market", "social", "news", "fundamentals"] as const;
const DEFAULT_TIMEOUT_MS = 10 * 60 * 1000;

const pluginRoot = path.dirname(fileURLToPath(import.meta.url));
const defaultRepoPath = path.resolve(pluginRoot, "../../..");

type PluginConfig = {
  repoPath?: string;
  pythonPath?: string;
  defaultPreset?: (typeof PRESETS)[number];
  defaultAnalysts?: (typeof ANALYSTS)[number][];
  timeoutMs?: number;
};

type ToolParams = {
  ticker: string;
  analysis_date?: string;
  preset?: (typeof PRESETS)[number];
  analysts?: (typeof ANALYSTS)[number][];
  recur_limit?: number;
  debate_rounds?: number;
  risk_rounds?: number;
};

function getPluginConfig(api: any): PluginConfig {
  return api?.config?.plugins?.entries?.[PLUGIN_ID]?.config ?? {};
}

function resolveRepoPath(cfg: PluginConfig): string {
  return cfg.repoPath || defaultRepoPath;
}

function resolvePythonPath(cfg: PluginConfig, repoPath: string): string {
  return cfg.pythonPath || path.join(repoPath, ".venv", "bin", "python");
}

async function assertExecutablePaths(repoPath: string, pythonPath: string): Promise<void> {
  await access(repoPath);
  await access(path.join(repoPath, "run_bailian.py"));
  await access(pythonPath);
}

function buildArgs(params: ToolParams, cfg: PluginConfig): string[] {
  const args = ["run_bailian.py", "--json"];
  const preset = params.preset || cfg.defaultPreset || "balanced";
  const analysts = params.analysts || cfg.defaultAnalysts || ["market", "social", "news", "fundamentals"];

  args.push("--preset", preset);
  args.push("--ticker", params.ticker);

  if (params.analysis_date) {
    args.push("--date", params.analysis_date);
  }
  if (analysts.length > 0) {
    args.push("--analysts", analysts.join(","));
  }
  if (typeof params.recur_limit === "number") {
    args.push("--recur-limit", String(params.recur_limit));
  }
  if (typeof params.debate_rounds === "number") {
    args.push("--debate-rounds", String(params.debate_rounds));
  }
  if (typeof params.risk_rounds === "number") {
    args.push("--risk-rounds", String(params.risk_rounds));
  }

  return args;
}

function execFileJson(
  command: string,
  args: string[],
  options: { cwd: string; timeoutMs: number; env: NodeJS.ProcessEnv },
): Promise<{ stdout: string; stderr: string; exitCode: number | null }> {
  return new Promise((resolve, reject) => {
    const child = execFile(
      command,
      args,
      {
        cwd: options.cwd,
        env: options.env,
        timeout: options.timeoutMs,
        maxBuffer: 10 * 1024 * 1024,
      },
      (error, stdout, stderr) => {
        if (error && typeof (error as NodeJS.ErrnoException).code === "string") {
          reject(error);
          return;
        }

        const exitCode =
          typeof (error as NodeJS.ErrnoException | null)?.code === "number"
            ? Number((error as NodeJS.ErrnoException).code)
            : 0;

        resolve({ stdout, stderr, exitCode });
      },
    );

    child.on("error", reject);
  });
}

function parsePayload(stdout: string, stderr: string): any {
  const trimmed = stdout.trim();
  if (!trimmed) {
    throw new Error(stderr.trim() || "TradingAgents returned empty output.");
  }

  try {
    return JSON.parse(trimmed);
  } catch {
    throw new Error(`TradingAgents returned non-JSON output: ${trimmed.slice(0, 500)}`);
  }
}

export default {
  id: PLUGIN_ID,
  name: "TradingAgents Bailian",
  description: "Runs the local TradingAgents workflow and returns JSON analysis.",
  register(api: any) {
    api.registerTool(
      {
        name: TOOL_NAME,
        description:
          "Run the local TradingAgents repository for a ticker and date, returning structured JSON with rating, summary, decision, and report paths.",
        parameters: {
          type: "object",
          additionalProperties: false,
          properties: {
            ticker: { type: "string", minLength: 1 },
            analysis_date: { type: "string", description: "Analysis date in YYYY-MM-DD format." },
            preset: { type: "string", enum: [...PRESETS] },
            analysts: {
              type: "array",
              items: { type: "string", enum: [...ANALYSTS] },
            },
            recur_limit: { type: "integer", minimum: 1 },
            debate_rounds: { type: "integer", minimum: 1 },
            risk_rounds: { type: "integer", minimum: 1 }
          },
          required: ["ticker"]
        },
        async execute(_id: string, params: ToolParams) {
          const cfg = getPluginConfig(api);
          const repoPath = resolveRepoPath(cfg);
          const pythonPath = resolvePythonPath(cfg, repoPath);
          await assertExecutablePaths(repoPath, pythonPath);

          const args = buildArgs(params, cfg);
          const { stdout, stderr } = await execFileJson(pythonPath, args, {
            cwd: repoPath,
            timeoutMs: cfg.timeoutMs || DEFAULT_TIMEOUT_MS,
            env: process.env,
          });

          const payload = parsePayload(stdout, stderr);
          return {
            content: [
              {
                type: "text",
                text: JSON.stringify(payload, null, 2),
              },
            ],
          };
        },
      },
      { optional: true },
    );
  },
};
