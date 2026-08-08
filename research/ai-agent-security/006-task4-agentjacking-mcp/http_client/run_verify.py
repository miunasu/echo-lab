#!/usr/bin/env python3
"""Verify http_client against a local echo server."""

import os
import subprocess
import sys
import time

ROOT = os.path.dirname(os.path.abspath(__file__))
os.chdir(ROOT)
sys.path.insert(0, ROOT)

from http_client import main  # noqa: E402


def run(title, args):
    print(f"\n===== {title} =====", flush=True)
    code = main(args)
    print(f"EXIT={code}", flush=True)
    return title, code


def main_verify():
    server = subprocess.Popen(
        [sys.executable, "local_echo_server.py"],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )
    time.sleep(1.0)

    results = []
    try:
        # Help via subprocess to avoid SystemExit complications in-process
        help_proc = subprocess.run(
            [sys.executable, "http_client.py", "--help"],
            capture_output=True,
            text=True,
        )
        print("===== HELP =====")
        print(help_proc.stdout)
        results.append(("HELP", help_proc.returncode))

        results.append(
            run(
                "GET",
                [
                    "--url",
                    "http://127.0.0.1:18765/api/ping",
                    "--method",
                    "GET",
                    "--headers",
                    '{"User-Agent": "Spore-HTTP-Client/1.0"}',
                ],
            )
        )
        results.append(
            run(
                "POST-body-file",
                [
                    "--url",
                    "http://127.0.0.1:18765/api/items",
                    "--method",
                    "POST",
                    "--headers",
                    '{"Content-Type": "application/json"}',
                    "--body-file",
                    "payload.json",
                ],
            )
        )
        results.append(
            run(
                "PUT-body",
                [
                    "--url",
                    "http://127.0.0.1:18765/api/items/1",
                    "--method",
                    "PUT",
                    "--headers",
                    '{"Content-Type": "application/json", "Authorization": "Bearer test-token"}',
                    "--body",
                    '{"name": "test"}',
                ],
            )
        )
        results.append(
            run(
                "DELETE",
                [
                    "--url",
                    "http://127.0.0.1:18765/api/items/1",
                    "--method",
                    "DELETE",
                ],
            )
        )
        results.append(
            run(
                "POST-inline",
                [
                    "--url",
                    "http://127.0.0.1:18765/echo",
                    "--method",
                    "POST",
                    "--headers",
                    '{"Content-Type": "application/json"}',
                    "--body",
                    '{"key": "value"}',
                ],
            )
        )
    finally:
        server.terminate()
        try:
            server.wait(timeout=3)
        except Exception:
            server.kill()

    print("\n===== SUMMARY =====")
    all_ok = True
    for title, code in results:
        ok = code == 0
        print(f"{title}: {'OK' if ok else 'FAIL'} (exit={code})")
        if not ok:
            all_ok = False
    print("ALL_OK" if all_ok else "SOME_FAILED")
    return 0 if all_ok else 1


if __name__ == "__main__":
    sys.exit(main_verify())