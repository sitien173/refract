from __future__ import annotations

import atexit
import os
import signal
import subprocess
import tempfile
import time
from pathlib import Path

from refract.database import Database
from tests.launchers import install_launcher

SERVER_DIR = Path(__file__).resolve().parents[2]
REPOSITORY_ROOT = SERVER_DIR.parent
BACKEND = SERVER_DIR / "tests" / "fixtures" / "fake_cli" / "e2e_backend.py"
PORT = int(os.environ.get("E2E_PORT", "18765"))


def seed(home: Path) -> None:
    database = Database(home / "refract.db")
    try:
        project = database.upsert_project(
            project_id="e2e-project", root=str(REPOSITORY_ROOT)
        )
        for number in range(101):
            job_id = f"e2e-seed-{number:03d}"
            database.create_job(
                job_id=job_id,
                project_id=project.id,
                workflow="consult",
                profile="e2e",
                prompt=f"Seeded dashboard job {number}",
                execution_plan_json="{}",
                session=f"e2e-seed-{number}",
            )
            with database._connection:
                database._connection.execute(
                    "UPDATE jobs SET state='succeeded', target='e2e', started_at=created_at, finished_at=updated_at WHERE id=?",
                    (job_id,),
                )
            database.results_dir.mkdir(parents=True, exist_ok=True)
            database.result_path(job_id).write_text(
                f"Seeded result {number}", encoding="utf-8"
            )
            database.append_stream(
                job_id,
                [
                    {
                        "seq": 1,
                        "kind": "assistant.text.delta",
                        "data": {"text": f"Seeded output {number}"},
                    }
                ],
            )
    finally:
        database.close()


def write_config(home: Path) -> Path:
    config = home / "config.toml"
    config.write_text(
        f"""[daemon]\nhost = "127.0.0.1"\nport = {PORT}\nmax_jobs = 2\ndefault_profile = "e2e"\nask_timeout_s = 30\n\n[logging]\nlevel = "WARNING"\n\n[[targets]]\nid = "e2e"\nbackend = "claude"\nmodel = "e2e"\n\n[[targets]]\nid = "e2e-next"\nbackend = "claude"\nmodel = "e2e"\n\n[profiles.e2e]\nconsult = {{ targets = ["e2e", "e2e-next"], timeout_s = 30 }}\nimplement = {{ targets = ["e2e", "e2e-next"], timeout_s = 30 }}\nreview = {{ targets = ["e2e", "e2e-next"], timeout_s = 30 }}\nother = {{ targets = ["e2e", "e2e-next"], timeout_s = 30 }}\n""",
        encoding="utf-8",
    )


def main() -> None:
    with tempfile.TemporaryDirectory(prefix="refract-e2e-") as temporary_home:
        home = Path(temporary_home)
        seed(home)
        write_config(home)
        bin_dir = home / "bin"
        bin_dir.mkdir()
        install_launcher(bin_dir, "claude", BACKEND)
        environment = os.environ.copy()
        for key in ("REFRACT_ASK_URL", "REFRACT_ASK_TOKEN", "REFRACT_ASK_TIMEOUT_S"):
            environment.pop(key, None)
        environment["REFRACT_HOME"] = str(home)
        environment["PATH"] = f"{bin_dir}{os.pathsep}{environment.get('PATH', '')}"
        child = subprocess.Popen(
            [
                "refract",
                "serve",
                "--host",
                "127.0.0.1",
                "--port",
                str(PORT),
                "--log-file",
                "-",
            ],
            cwd=SERVER_DIR,
            env=environment,
        )

        def stop(*_args: object) -> None:
            if child.poll() is None:
                child.terminate()
                try:
                    child.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    child.kill()
                    child.wait()

        stop_deadline: list[float] = []

        def request_stop(*_args: object) -> None:
            # Never wait here: the main loop reaps the child and kills it after the deadline.
            if not stop_deadline:
                stop_deadline.append(time.monotonic() + 10)
                child.terminate()

        atexit.register(stop)
        for signum in (signal.SIGTERM, signal.SIGINT):
            signal.signal(signum, request_stop)
        try:
            while True:
                try:
                    return_code = child.wait(timeout=0.5)
                    break
                except subprocess.TimeoutExpired:
                    if stop_deadline and time.monotonic() > stop_deadline[0]:
                        child.kill()
            if return_code:
                raise SystemExit(return_code)
        finally:
            stop()
            atexit.unregister(stop)


if __name__ == "__main__":
    main()
