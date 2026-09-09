"""Live browser exploration: NL requirement -> LangGraph agent -> Playwright MCP.

App-local (not a workspace package) — only `generation_worker` consumes this
today. Deliberately independent of every crawler/discovery-read path: the
agent (`agent.py`) never queries `Page`/`Component`/`DiscoveryRun`; it only
ever writes fresh ones, after exploring, via `materialize.py`.
"""
