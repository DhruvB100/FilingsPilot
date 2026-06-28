# filingspilot MCP server

Exposes the 4 FilingsPilot tools over MCP (stdio): `search_filings`, `query_financials`, `calculate`, `flag_issue`.
It just forwards to the python API (`/tools/*`), so the API has to be running.

```
npm install
npm run build
```

## Claude Code
The repo has a `.mcp.json`, so opening the project in Claude Code picks it up. Or:
```
claude mcp add filingspilot -e FILINGSPILOT_API_URL=http://localhost:8000 -- node mcp-server/dist/index.js
```

## Claude Desktop
`claude_desktop_config.json`:
```json
{
  "mcpServers": {
    "filingspilot": {
      "command": "node",
      "args": ["C:/path/to/FilingsPilot/mcp-server/dist/index.js"],
      "env": { "FILINGSPILOT_API_URL": "https://<your container app>.azurecontainerapps.io" }
    }
  }
}
```

Then ask something like "use filingspilot to compare Suncor and Cenovus revenue in 2025".
