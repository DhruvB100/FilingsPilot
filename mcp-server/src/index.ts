#!/usr/bin/env node
// MCP server for FilingsPilot. It doesn't re-implement anything, every tool just calls
// the python API's /tools/* endpoints so the guardrails (sql guard, read only db user) stay in one place.
import { McpServer } from "@modelcontextprotocol/sdk/server/mcp.js";
import { StdioServerTransport } from "@modelcontextprotocol/sdk/server/stdio.js";
import { z } from "zod";

const API_URL = process.env.FILINGSPILOT_API_URL || "http://localhost:8000";

async function callTool(name: string, body: object): Promise<string> {
  const res = await fetch(`${API_URL}/tools/${name}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!res.ok) {
    return `FilingsPilot API error ${res.status}: ${await res.text()}`;
  }
  const data = (await res.json()) as { result: string };
  return data.result;
}

function text(t: string) {
  return { content: [{ type: "text" as const, text: t }] };
}

const server = new McpServer({ name: "filingspilot", version: "0.1.0" });

server.registerTool(
  "search_filings",
  {
    title: "Search annual filings",
    description:
      "Hybrid (keyword + vector) search over the fiscal 2024/2025 annual reports (40-F / 10-K) of 10 Canadian companies: " +
      "CVE, SU, TRP, ENB, CNQ, RY, TD, BMO, CM, SHOP. Returns passages with company, year, document, page and section.",
    inputSchema: {
      query: z.string().describe("what to look for"),
      tickers: z.array(z.string()).optional().describe('e.g. ["CVE", "SU"]'),
      years: z.array(z.number().int()).optional().describe("fiscal years, e.g. [2025]"),
    },
  },
  async (args) => text(await callTool("search_filings", args))
);

server.registerTool(
  "query_financials",
  {
    title: "Query financial data (SQL)",
    description:
      "Run one read-only SELECT on the financials table built from SEC XBRL company facts. " +
      "financials(ticker, metric, fiscal_year, period_end, value, unit, source_tag, form, accession), companies(ticker, name, cik, sector). " +
      "metrics include revenue, net_income, total_assets, operating_cash_flow, capex, eps_diluted, dividends_paid. Values are in full units.",
    inputSchema: {
      sql: z.string().describe("a single SELECT statement"),
    },
  },
  async ({ sql }) => text(await callTool("query_financials", { sql }))
);

server.registerTool(
  "calculate",
  {
    title: "Calculate",
    description: "growth_rate (a=old, b=new, percent), cagr (a=start, b=end, years), ratio (a/b), difference (b-a), percent_of (a as % of b), sum.",
    inputSchema: {
      operation: z.enum(["growth_rate", "cagr", "ratio", "difference", "percent_of", "sum"]),
      a: z.number(),
      b: z.number().optional(),
      years: z.number().optional(),
    },
  },
  async (args) => text(await callTool("calculate", args))
);

server.registerTool(
  "flag_issue",
  {
    title: "Flag an issue in Jira",
    description: "Open a Jira ticket when the report text and the financial numbers contradict each other.",
    inputSchema: {
      summary: z.string(),
      details: z.string().describe("what disagrees and where (sources)"),
      ticker: z.string(),
    },
  },
  async (args) => text(await callTool("flag_issue", args))
);

const transport = new StdioServerTransport();
await server.connect(transport);
// stdout is the MCP channel, so log to stderr only
console.error(`filingspilot MCP server running, API = ${API_URL}`);
