"""
Windows Task Scheduler setup helpers for the CapCut pipeline.
"""
from __future__ import annotations

import os
import platform
import subprocess
from pathlib import Path

import config


def write_scheduler_setup(base_dir: str, interval_hours: int | None = None) -> dict:
    scheduler_dir = Path(base_dir)
    scheduler_dir.mkdir(parents=True, exist_ok=True)
    run_script = scheduler_dir / "run_capcut_alerts.bat"
    install_script = scheduler_dir / "install_capcut_alerts_task.ps1"

    project_dir = Path(__file__).resolve().parents[1]
    python_exe = project_dir / ".venv" / "Scripts" / "python.exe"
    python_command = str(python_exe if python_exe.exists() else "python")
    hours = interval_hours or config.WINDOWS_TASK_INTERVAL_HOURS

    run_script.write_text(_build_run_script(project_dir, python_command), encoding="utf-8")
    install_script.write_text(_build_install_script(run_script, hours), encoding="utf-8")

    return {
        "run_script": str(run_script),
        "install_script": str(install_script),
        "command_preview": build_schtasks_command(str(run_script), hours),
        "interval_hours": hours,
    }


def install_windows_task(run_script_path: str, interval_hours: int | None = None, task_name: str | None = None) -> dict:
    if platform.system().lower() != "windows":
        return {"ok": False, "detail": "Windows Task Scheduler is only available on Windows."}
    hours = interval_hours or config.WINDOWS_TASK_INTERVAL_HOURS
    command = build_schtasks_command(run_script_path, hours, task_name=task_name)
    try:
        completed = subprocess.run(command, capture_output=True, text=True, check=False, shell=False)
    except Exception as exc:
        return {"ok": False, "detail": str(exc), "command": " ".join(command)}
    ok = completed.returncode == 0
    detail = completed.stdout.strip() or completed.stderr.strip() or f"Return code {completed.returncode}"
    return {"ok": ok, "detail": detail, "command": " ".join(command)}


def build_schtasks_command(run_script_path: str, interval_hours: int, task_name: str | None = None) -> list[str]:
    task = task_name or config.WINDOWS_TASK_NAME
    return [
        "schtasks",
        "/Create",
        "/F",
        "/SC",
        "HOURLY",
        "/MO",
        str(interval_hours),
        "/TN",
        task,
        "/TR",
        run_script_path,
    ]


def _build_run_script(project_dir: Path, python_command: str) -> str:
    return (
        "@echo off\n"
        f"cd /d \"{project_dir}\"\n"
        f"\"{python_command}\" main.py --once\n"
    )


def _build_install_script(run_script: Path, interval_hours: int) -> str:
    quoted_task_name = config.WINDOWS_TASK_NAME.replace("'", "''")
    return f"""$taskName = '{quoted_task_name}'
$taskCommand = '{str(run_script).replace("'", "''")}'
schtasks /Create /F /SC HOURLY /MO {interval_hours} /TN $taskName /TR $taskCommand
"""
