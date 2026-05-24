# Validation Report: openmcp Unified Server

## Success Criteria Checks

1. PASS - `openmcp` installs and CLI entry is declared.
- Command: `uv pip install -e ./openmcp`
- Observed output: `Installed 1 package ... openmcp==0.1.0`
- Command: `./.venv/Scripts/python.exe -c "import tomllib, pathlib; data=tomllib.loads(pathlib.Path('openmcp/pyproject.toml').read_text()); print(data['project']['scripts']['openmcp'])"`
- Observed output: `openmcp.cli:main`

2. PASS - `run(backend="agy"|"codex", ...)` dispatch wiring is present.
- Command: `./.venv/Scripts/python.exe -c "import inspect, openmcp.server as s; src=inspect.getsource(s.run); print('AgyParams' in src and 'CodexParams' in src and 'run_with_retry' in src)"`
- Observed output: `True`

3. PASS - Simulated transient error retries and recovers (`attempts==2`).
- Command: `./.venv/Scripts/python.exe <temp criterion-3 script>`
- Observed output: `criterion3-result 2 True`

4. PASS - Fatal flow returns immediately (`attempts==1`).
- Command: `./.venv/Scripts/python.exe <temp criterion-4 script>`
- Observed output: `criterion4-result 1 False`

5. PASS - SESSION_ID from attempt 1 is forwarded to attempt 2.
- Command: `./.venv/Scripts/python.exe <temp criterion-3 script>`
- Observed output: `criterion5-calls ['', 'sess-1']`

## Test Suite Evidence
- Command: `./.venv/Scripts/python.exe -m pytest openmcp/tests -x`
- Observed output: `6 passed`
