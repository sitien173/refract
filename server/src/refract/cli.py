"""CLI entrypoint for refract."""

from __future__ import annotations

import argparse
import ipaddress
import json
import os
import shutil
import sys
from collections.abc import Callable, Sequence
from datetime import datetime
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from refract.config import DEFAULT_ASK_TIMEOUT_S, DaemonConfig, load_config
from refract.logging_setup import configure as configure_logging, get_logger, resolve_config


log = get_logger("cli")


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="refract")
    commands = parser.add_subparsers(dest="command")
    serve = commands.add_parser("serve", help="Run the local MCP daemon")
    serve.add_argument("--host", default=None)
    serve.add_argument(
        "--allow-remote",
        action="store_true",
        help="Allow binding a non-loopback host; the MCP endpoint has no authentication",
    )
    serve.add_argument("--port", type=int, default=None)
    serve.add_argument(
        "--log-level",
        choices=("DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"),
        default=None,
        help="Override the configured application log level",
    )
    serve.add_argument(
        "--log-file",
        default=None,
        help="Override the log path; use '-' to disable file logging",
    )
    commands.add_parser("doctor", help="Inspect daemon prerequisites")
    commands.add_parser("status", help="Report whether the daemon is running")
    for name in ("stop", "restart"):
        command = commands.add_parser(name, help=f"{name.capitalize()} the local daemon")
        command.add_argument("--force", action="store_true", help="Stop even when jobs are running")
    ask = commands.add_parser("ask", help="Ask the coordinator during a worker job")
    ask.add_argument("question")
    update = commands.add_parser("update", help="Check for or apply Refract updates")
    update.add_argument("--check", action="store_true", help="Check for updates without changing anything")
    update.add_argument("--force", action="store_true", help="Ignore the 24 hour check throttle")
    for name, verb in (("install", "Install"), ("uninstall", "Remove")):
        sub = commands.add_parser(name, help=f"{verb} the Refract plugin for coding-agent hosts")
        sub.add_argument(
            "-p",
            "--host",
            dest="hosts",
            action="append",
            required=True,
            metavar="HOST",
            help="claude, codex, agy, agy-ide, pi, or all; comma-separated or repeated",
        )
        sub.add_argument("--scope", choices=("user", "project", "local"), default="user")
        sub.add_argument(
            "--dry-run", action="store_true", help="Print the host commands without running them"
        )
        if name == "install":
            sub.add_argument(
                "--source", default=None, help="Plugin path or URL; default is the GitHub repository"
            )
    stats = commands.add_parser("stats", help="Show local usage analytics")
    stats.add_argument("--days", type=int, choices=(1, 7, 30, 365), default=7)
    stats.add_argument("--json", action="store_true", help="Print the API response as JSON")
    commands.add_parser("telemetry", help="Show the telemetry decision and the next batch")
    return parser


def _ask(question: str) -> int:
    url = os.environ.get("REFRACT_ASK_URL")
    token = os.environ.get("REFRACT_ASK_TOKEN")
    if not url or not token:
        sys.stderr.write("refract ask requires REFRACT_ASK_URL and REFRACT_ASK_TOKEN.\n")
        return 1
    if not question.strip():
        sys.stderr.write("Question must not be empty.\n")
        return 1
    try:
        timeout_s = int(os.environ.get("REFRACT_ASK_TIMEOUT_S", DEFAULT_ASK_TIMEOUT_S)) + 10
        request = Request(
            url,
            data=json.dumps({"token": token, "question": question}).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urlopen(request, timeout=timeout_s) as response:
            answer = json.load(response)["answer"]
        if not isinstance(answer, str):
            raise TypeError("Invalid answer")
    except HTTPError as exc:
        sys.stderr.write(f"Coordinator rejected the question: HTTP {exc.code}.\n")
        return 1
    except (OSError, URLError):
        sys.stderr.write("Coordinator connection failed.\n")
        return 1
    except (ValueError, KeyError, TypeError):
        sys.stderr.write("Coordinator response or ask environment is invalid.\n")
        return 1
    sys.stdout.write(answer + "\n")
    return 0


def _doctor(config: DaemonConfig | None = None) -> int:
    if config is None:
        try:
            config = load_config()
        except ValueError as exc:
            sys.stderr.write(f"Configuration error: {exc}\n")
            return 1
    configure_logging(config.logging)
    logging_config = resolve_config(config.logging)
    writable_path = config.home
    while not writable_path.exists() and writable_path != writable_path.parent:
        writable_path = writable_path.parent
    home_writable = writable_path.is_dir() and os.access(writable_path, os.W_OK)
    targets = {
        target.id: {
            "backend": target.backend,
            "executable": shutil.which(target.backend) or "",
        }
        for target in config.targets
    }
    payload = {
        "home": config.home.as_posix(),
        "home_writable": home_writable,
        "logging": {
            "level": logging_config.level,
            "file": logging_config.file.as_posix() if logging_config.file else "",
        },
        "targets": targets,
    }
    sys.stdout.write(json.dumps(payload, indent=2) + "\n")
    log.info(
        "Prerequisite check completed",
        extra={
            "event": "doctor.completed",
            "target_count": len(config.targets),
        },
    )
    return 0 if home_writable and all(target["executable"] for target in targets.values()) else 1


def _stop_daemon(
    force: bool, out: Callable[[str], object], *, quiet_missing: bool = False
) -> bool:
    from refract import daemon_control

    info = daemon_control.read_daemon_file()
    if info is None:
        host, port = daemon_control.configured_endpoint()
        if daemon_control.port_open(host, port):
            out("Cannot stop the Refract daemon automatically. Stop it manually.")
            return False
        if not quiet_missing:
            out("Refract daemon is not running.")
        return True

    token, host, port, _pid = info
    raw = daemon_control.post_shutdown(
        token, host, port, daemon_control.SHUTDOWN_POST_TIMEOUT_S, force=force
    )
    if isinstance(raw, bool):
        if not quiet_missing:
            out("Refract daemon is not running.")
        return True
    if isinstance(raw, daemon_control.ShutdownFailure):
        if raw.kind == "http":
            out(f"Failed: the daemon rejected shutdown (HTTP {raw.code}).")
        elif raw.kind == "timeout":
            out("Failed: the shutdown request timed out.")
        else:
            out("Failed: cannot reach the daemon.")
        return False
    reply = daemon_control.shutdown_reply(raw)
    if reply is None:
        out("Failed: the daemon sent an unreadable shutdown reply.")
        return False
    stopping, running, queued = reply
    if not stopping:
        out(f"Refused: {running} running, {queued} queued job(s).")
        return False
    wait_s = daemon_control.FORCED_STOP_WAIT_S if force else daemon_control.STOP_WAIT_S
    if not daemon_control.wait_for_stop(host, port, wait_s, daemon_control.POLL_S):
        out("Failed: the daemon may still be stopping.")
        return False
    if force:
        out(f"Stopped the Refract daemon. Forced stop: {running} running, {queued} queued job(s).")
    else:
        out("Stopped the Refract daemon.")
    return True


def _stop(args: argparse.Namespace) -> int:
    return 0 if _stop_daemon(args.force, print) else 1


def _restart(args: argparse.Namespace) -> int:
    from refract import daemon_control

    if not _stop_daemon(args.force, print, quiet_missing=True):
        return 1
    try:
        daemon_control.spawn_serve()
    except OSError:
        print("Failed: could not start the Refract daemon.")
        return 1
    host, port = daemon_control.configured_endpoint()
    if not daemon_control.wait_until_answers(
        host, port, daemon_control.START_WAIT_S, daemon_control.POLL_S
    ):
        print("Failed: the Refract daemon did not start in time.")
        return 1
    print("Started the Refract daemon.")
    return 0


def _status() -> int:
    try:
        config = load_config()
    except ValueError as exc:
        sys.stderr.write(f"Configuration error: {exc}\n")
        return 1
    url = f"http://{config.host}:{config.port}"
    # Any HTTP reply means the port is served; only a failed connection means stopped.
    try:
        with urlopen(f"{url}/mcp", timeout=2):
            running = True
    except HTTPError:
        running = True
    except (OSError, URLError):
        running = False
    pid = None
    if running:
        from refract.daemon_control import read_daemon_file

        try:
            daemon_info = read_daemon_file()
        except (OSError, ValueError):
            daemon_info = None
        if daemon_info is not None:
            _token, host, port, file_pid = daemon_info
            if host == config.host and port == config.port:
                pid = file_pid
    sys.stdout.write(json.dumps({"running": running, "url": url, "pid": pid}) + "\n")
    return 0 if running else 1


def _stats(args: argparse.Namespace) -> int:
    try:
        config = load_config()
    except ValueError as exc:
        sys.stderr.write(f"Configuration error: {exc}\n")
        return 1
    offset = datetime.now().astimezone().utcoffset()
    tz_offset_minutes = int(offset.total_seconds() // 60) if offset is not None else 0
    url = (f"http://{config.host}:{config.port}/dashboard/api/stats?days={args.days}"
           f"&tz_offset_minutes={tz_offset_minutes}")
    try:
        with urlopen(url, timeout=2) as response:
            raw_body = response.read()
    except HTTPError as exc:
        try:
            api_error = json.loads(exc.read()).get("error", exc.reason)
        except (ValueError, AttributeError):
            api_error = exc.reason
        sys.stderr.write(f"Refract stats request failed: HTTP {exc.code}: {api_error}\n")
        return 1
    except OSError:
        sys.stderr.write("Refract daemon is not running.\n")
        return 1
    if args.json:
        sys.stdout.buffer.write(raw_body)
    else:
        try:
            payload = json.loads(raw_body)
        except ValueError:
            sys.stderr.write("Refract stats response contains invalid JSON.\n")
            return 1
        try:
            work = payload["work_delegated"]
            saves = payload["failover_saves"]
            tokens = payload["tokens"]["by_model"]
            cost = payload["estimated_cost"]
            lines = (
                f"Work delegated ({args.days} days): {sum(work['by_state'].values())} jobs; "
                f"{work['worker_hours']:.2f} worker hours; "
                f"{work['success_rate']:.1%} success rate\n",
                f"Failover saves: {sum(saves[key] for key in ('skipped_targets', 'retries', 'retries_after_failure'))}\n",
                f"Tokens by model: {len(tokens)} models\n",
                f"Estimated cost: {cost['total']:.2f} {payload['currency']}\n",
            )
        except (KeyError, TypeError, AttributeError, ValueError):
            sys.stderr.write("Refract stats response has an unexpected shape.\n")
            return 1
        sys.stdout.write("".join(lines))
    return 0


def _telemetry() -> int:
    try:
        config = load_config()
    except ValueError as exc:
        sys.stderr.write(f"Configuration error: {exc}\n")
        return 1
    try:
        with urlopen(f"http://{config.host}:{config.port}/dashboard/api/telemetry", timeout=2) as response:
            payload = json.loads(response.read())
    except HTTPError as exc:
        try:
            api_error = json.loads(exc.read()).get("error", exc.reason)
        except (ValueError, AttributeError):
            api_error = exc.reason
        sys.stderr.write(f"Refract telemetry request failed: HTTP {exc.code}: {api_error}\n")
        return 1
    except OSError:
        sys.stderr.write("Refract daemon is not running.\n")
        return 1
    except ValueError:
        sys.stderr.write("Refract telemetry response contains invalid JSON.\n")
        return 1
    sys.stdout.write(f"enabled: {'on' if payload['enabled'] else 'off'}\n")
    sys.stdout.write(f"source: {payload['source']}\n")
    sys.stdout.write(f"endpoint: {payload['endpoint']}\n")
    sys.stdout.write(f"install_id: {payload['install_id'] or 'none'}\n")
    sys.stdout.write(f"queued: {payload['queued']}\n")
    sys.stdout.write(f"last_send_at: {payload['last_send_at'] or 'never'}\n")
    sys.stdout.write(f"last_error: {payload['last_error'] or 'none'}\n")
    if payload["next_batch"] is None:
        sys.stdout.write("next_batch: none\n")
    else:
        sys.stdout.write(f"next_batch:\n{json.dumps(payload['next_batch'], indent=2)}\n")
    return 0


def _update(args: argparse.Namespace) -> int:
    from refract.updater import run_check, run_update

    return run_check(force=args.force) if args.check else run_update()


def _install(args: argparse.Namespace) -> int:
    from refract.installer import run

    return run(
        args.command,
        args.hosts,
        scope=args.scope,
        source=getattr(args, "source", None),
        dry_run=args.dry_run,
    )


def _logging_overrides(args: argparse.Namespace) -> dict[str, str]:
    overrides = {
        "REFRACT_LOG_LEVEL": getattr(args, "log_level", None),
        "REFRACT_LOG_FILE": getattr(args, "log_file", None),
    }
    return {name: str(value) for name, value in overrides.items() if value is not None}


def _is_loopback_bind(host: str) -> bool:
    if host.lower() == "localhost":
        return True
    try:
        return ipaddress.ip_address(host.strip("[]")).is_loopback
    except ValueError:
        return False


def main(argv: Sequence[str] | None = None) -> None:
    """Run the daemon or inspect local prerequisites."""
    args = _parser().parse_args(argv)
    if args.command == "ask":
        raise SystemExit(_ask(args.question))
    if args.command == "doctor":
        raise SystemExit(_doctor())
    if args.command == "status":
        raise SystemExit(_status())
    if args.command == "stop":
        raise SystemExit(_stop(args))
    if args.command == "restart":
        raise SystemExit(_restart(args))
    if args.command == "update":
        raise SystemExit(_update(args))
    if args.command in {"install", "uninstall"}:
        raise SystemExit(_install(args))
    if args.command == "stats":
        raise SystemExit(_stats(args))
    if args.command == "telemetry":
        raise SystemExit(_telemetry())
    if args.command not in {None, "serve"}:
        raise SystemExit(2)

    logging_overrides = _logging_overrides(args)
    try:
        config = load_config()
    except ValueError as exc:
        sys.stderr.write(f"Configuration error: {exc}\n")
        raise SystemExit(1) from exc
    # Resolve transport settings locally; MCPServer has no mutable transport config.
    host = args.host if getattr(args, "host", None) is not None else config.host
    port = args.port if getattr(args, "port", None) is not None else config.port
    if not _is_loopback_bind(host) and not getattr(args, "allow_remote", False):
        sys.stderr.write(
            f"Refusing to bind non-loopback host {host!r}: the MCP endpoint has no authentication. "
            "Pass --allow-remote to bind it anyway.\n"
        )
        raise SystemExit(2)

    # Import after configuration so startup uses the final settings.
    from refract import server

    log.info(
        "Launching HTTP transport",
        extra={"event": "cli.serve", "host": host, "port": port},
    )
    try:
        import uvicorn

        application = server.create_application(config, host=host, port=port, logging_overrides=logging_overrides)
        daemon = uvicorn.Server(uvicorn.Config(application, host=host, port=port, timeout_graceful_shutdown=5))
        # The shutdown endpoint asks this server to exit once the runtime is idle.
        application.state.refract_dashboard.request_exit = lambda: setattr(daemon, "should_exit", True)
        daemon.run()
        # Server.run, unlike uvicorn.run, does not signal a failed startup.
        if not daemon.started:
            raise SystemExit(3)
    except KeyboardInterrupt:
        log.info("Shutdown requested", extra={"event": "cli.interrupted"})
    except Exception:
        log.exception("Daemon terminated unexpectedly", extra={"event": "cli.failed"})
        raise


__all__ = ["main"]
