# Cross-Platform Polyglot Hooks for Claude Code

Claude Code plugins need hooks that work on Windows, macOS, and Linux. This document explains the polyglot wrapper technique that makes this possible.

## The Problem

Claude Code runs hook commands through the system's default shell:
- **Windows**: CMD.exe
- **macOS/Linux**: bash or sh

This creates several challenges:

1. **Script execution**: Windows CMD can't execute `.sh` files directly - it tries to open them in a text editor
2. **Path format**: Windows uses backslashes (`C:\path`), Unix uses forward slashes (`/path`)
3. **Environment variables**: `$VAR` syntax doesn't work in CMD
4. **No `bash` in PATH**: Even with Git Bash installed, `bash` isn't in the PATH when CMD runs

## The Solution: Polyglot `.cmd` Wrapper

A polyglot script is valid syntax in multiple languages simultaneously. Our wrapper is valid in both CMD and bash:

```cmd
: << 'CMDBLOCK'
@echo off
"C:\Program Files\Git\bin\bash.exe" -l -c "\"$(cygpath -u \"$CLAUDE_PLUGIN_ROOT\")/hooks/session-start.sh\""
exit /b
CMDBLOCK

# Unix shell runs from here
"${CLAUDE_PLUGIN_ROOT}/hooks/session-start.sh"
```

### How It Works

#### On Windows (CMD.exe)

1. `: << 'CMDBLOCK'` - CMD sees `:` as a label (like `:label`) and ignores `<< 'CMDBLOCK'`
2. `@echo off` - Suppresses command echoing
3. The bash.exe command runs with:
   - `-l` (login shell) to get proper PATH with Unix utilities
   - `cygpath -u` converts Windows path to Unix format (`C:\foo` → `/c/foo`)
4. `exit /b` - Exits the batch script, stopping CMD here
5. Everything after `CMDBLOCK` is never reached by CMD

#### On Unix (bash/sh)

1. `: << 'CMDBLOCK'` - `:` is a no-op, `<< 'CMDBLOCK'` starts a heredoc
2. Everything until `CMDBLOCK` is consumed by the heredoc (ignored)
3. `# Unix shell runs from here` - Comment
4. The script runs directly with the Unix path

## File Structure (this plugin)

This plugin dispatches hooks through a single bash entry point rather than a per-hook `.cmd` wrapper:

```
hooks/
├── hooks.json        # invokes run-hook.sh via bash
├── run-hook.sh       # generic dispatcher: resolves its own dir, execs the named script
└── session-start.sh  # actual hook logic (bash)
```

### hooks.json

```json
{
  "hooks": {
    "SessionStart": [
      {
        "matcher": "startup|resume|clear|compact",
        "hooks": [
          {
            "type": "command",
            "command": "bash \"${CLAUDE_PLUGIN_ROOT:-${ANTIGRAVITY_PLUGIN_ROOT:-.}}/hooks/run-hook.sh\" session-start.sh"
          }
        ]
      }
    ]
  }
}
```

Notes:
- The path is quoted because `${CLAUDE_PLUGIN_ROOT}` may contain spaces on Windows (e.g. `C:\Program Files\...`).
- `${CLAUDE_PLUGIN_ROOT:-${ANTIGRAVITY_PLUGIN_ROOT:-.}}` makes the same file work under both Claude Code and the Antigravity CLI.
- This relies on `bash` being resolvable when the hook runs. The polyglot `.cmd` wrapper described below is the fallback for environments (raw CMD) where `bash` is not on PATH.

## Requirements

### Windows
- **Git for Windows** must be installed (provides `bash.exe` and `cygpath`)
- Default installation path: `C:\Program Files\Git\bin\bash.exe`
- If Git is installed elsewhere, the wrapper needs modification

### Unix (macOS/Linux)
- Standard bash or sh shell
- The `.cmd` file must have execute permission (`chmod +x`)

## Writing Cross-Platform Hook Scripts

Your actual hook logic goes in the `.sh` file. To ensure it works on Windows (via Git Bash):

### Do:
- Use `$(command)` instead of backticks
- Quote all variable expansions: `"$VAR"`
- Use `printf` or here-docs for output
- `sed`/`awk`/`grep` are fine — the hook runs under bash (Git Bash on Windows via the login shell), so the standard Unix toolchain is on PATH

### Example: JSON Escaping with awk

The escape order matters: backslash first, then quote, then control chars. `ORS=""` suppresses awk's trailing newline; the `NR>1` guard re-inserts literal `\n` between input lines:

```bash
escape_for_json() {
    printf '%s' "$1" | awk '
        BEGIN { ORS = "" }
        {
            gsub(/\\/, "\\\\")
            gsub(/"/, "\\\"")
            gsub(/\t/, "\\t")
            gsub(/\r/, "\\r")
            if (NR > 1) printf "\\n"
            printf "%s", $0
        }
    '
}
```

## Reusable Wrapper Pattern

For plugins with multiple hooks, you can create a generic wrapper that takes the script name as an argument:

### run-hook.cmd
```cmd
: << 'CMDBLOCK'
@echo off
set "SCRIPT_DIR=%~dp0"
set "SCRIPT_NAME=%~1"
"C:\Program Files\Git\bin\bash.exe" -l -c "cd \"$(cygpath -u \"%SCRIPT_DIR%\")\" && \"./%SCRIPT_NAME%\""
exit /b
CMDBLOCK

# Unix shell runs from here
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]:-$0}")" && pwd)"
SCRIPT_NAME="$1"
shift
"${SCRIPT_DIR}/${SCRIPT_NAME}" "$@"
```

### hooks.json using the reusable wrapper
```json
{
  "hooks": {
    "SessionStart": [
      {
        "matcher": "startup",
        "hooks": [
          {
            "type": "command",
            "command": "\"${CLAUDE_PLUGIN_ROOT}/hooks/run-hook.cmd\" session-start.sh"
          }
        ]
      }
    ],
    "PreToolUse": [
      {
        "matcher": "Bash",
        "hooks": [
          {
            "type": "command",
            "command": "\"${CLAUDE_PLUGIN_ROOT}/hooks/run-hook.cmd\" validate-bash.sh"
          }
        ]
      }
    ]
  }
}
```

## Troubleshooting

### "bash is not recognized"
CMD can't find bash. The wrapper uses the full path `C:\Program Files\Git\bin\bash.exe`. If Git is installed elsewhere, update the path.

### "cygpath: command not found" or "dirname: command not found"
Bash isn't running as a login shell. Ensure `-l` flag is used.

### Path has weird `\/` in it
`${CLAUDE_PLUGIN_ROOT}` expanded to a Windows path ending with backslash, then `/hooks/...` was appended. Use `cygpath` to convert the entire path.

### Script opens in text editor instead of running
The hooks.json is pointing directly to the `.sh` file. Point to the `.cmd` wrapper instead.

### Works in terminal but not as hook
Claude Code may run hooks differently. Test by simulating the hook environment:
```powershell
$env:CLAUDE_PLUGIN_ROOT = "C:\path\to\plugin"
cmd /c "C:\path\to\plugin\hooks\session-start.cmd"
```

## Related Issues

- [anthropics/claude-code#9758](https://github.com/anthropics/claude-code/issues/9758) - .sh scripts open in editor on Windows
- [anthropics/claude-code#3417](https://github.com/anthropics/claude-code/issues/3417) - Hooks don't work on Windows
- [anthropics/claude-code#6023](https://github.com/anthropics/claude-code/issues/6023) - CLAUDE_PROJECT_DIR not found
