#!/usr/bin/env python3
import argparse
import requests
import time
import sys

try:
    from termcolor import colored
except ImportError:
    def colored(s, color=None, attrs=None):
        return s


def poll_strategy_job(base_url, project_id, job_id, interval=2, timeout=600, headers=None):
    start = time.time()
    while True:
        elapsed = time.time() - start
        if elapsed > timeout:
            print(colored(f"Timeout waiting for job {job_id}", "red"))
            return 1

        url = f"{base_url.rstrip('/')}/api/strategy/{project_id}/jobs/{job_id}"
        try:
            if headers:
                r = requests.get(url, headers=headers, timeout=10)
            else:
                r = requests.get(url, timeout=10)
            r.raise_for_status()
            j = r.json()
        except Exception as e:
            print(colored(f"[ERROR] polling job: {e}", "red"))
            time.sleep(interval)
            continue

        status = j.get("status")
        phase = j.get("phase") or "?"
        progress = j.get("progress", 0)
        error = j.get("error")
        logs = j.get("logs") or []

        def status_color(st):
            return {
                "queued": "yellow",
                "running": "blue",
                "completed": "green",
                "complete": "green",
                "failed": "red",
                "warning": "magenta",
                "error": "red",
            }.get(st, "white")

        print(colored(f"[{time.strftime('%H:%M:%S')}] status={status}, phase={phase}, progress={progress}%", status_color(status)))

        if logs:
            for l in logs[-8:]:
                if isinstance(l, dict):
                    ts = l.get("ts", "")
                    msg = l.get("msg", "")
                else:
                    ts = ""
                    msg = str(l)
                print(colored(f"  {ts} {msg}", "cyan"))

        if error:
            print(colored(f"[ERROR] {error}", "red", attrs=["bold"]))

        if status in ("completed", "complete"):
            print(colored("Job completed", "green", attrs=["bold"]))
            return 0
        if status in ("failed", "error"):
            print(colored("Job failed", "red", attrs=["bold"]))
            return 1

        time.sleep(interval)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Poll a strategy run job and print console logs")
    parser.add_argument("--base-url", default="http://localhost:8000", help="Base URL of your AnnaSEO backend")
    parser.add_argument("--project-id", required=True, help="Project ID")
    parser.add_argument("--job-id", required=True, help="Strategy job/run ID")
    parser.add_argument("--interval", type=int, default=2, help="Polling interval (seconds)")
    parser.add_argument("--timeout", type=int, default=600, help="Timeout in seconds")
    parser.add_argument("--token", default=None, help="Bearer token for Authorization header (prefixed or not)")
    args = parser.parse_args()

    token = args.token
    if token and not token.lower().startswith("bearer "):
        token = f"Bearer {token}"

    headers = {"Authorization": token} if token else None
    sys.exit(poll_strategy_job(args.base_url, args.project_id, args.job_id, args.interval, args.timeout, headers=headers))
