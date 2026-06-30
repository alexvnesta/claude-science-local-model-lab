#!/usr/bin/env python3
"""Run a command as a small detached daemon.

macOS does not ship `setsid` as a normal CLI utility. This helper uses the
standard double-fork pattern, writes the daemon PID before exec, and redirects
stdout/stderr to a log file.
"""

from __future__ import annotations

import argparse
import os
import sys


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cwd", required=True)
    parser.add_argument("--pid-file", required=True)
    parser.add_argument("--log-file", required=True)
    parser.add_argument("command", nargs=argparse.REMAINDER)
    args = parser.parse_args()
    if args.command and args.command[0] == "--":
        args.command = args.command[1:]
    if not args.command:
        parser.error("missing command")
    return args


def fork_or_exit() -> int:
    try:
        return os.fork()
    except OSError as exc:
        print(f"fork failed: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc


def main() -> int:
    args = parse_args()

    pid = fork_or_exit()
    if pid > 0:
        return 0

    os.setsid()

    pid = fork_or_exit()
    if pid > 0:
        os._exit(0)

    os.chdir(args.cwd)
    os.umask(0o022)

    os.makedirs(os.path.dirname(args.pid_file), exist_ok=True)
    os.makedirs(os.path.dirname(args.log_file), exist_ok=True)

    with open(args.pid_file, "w", encoding="utf-8") as pid_file:
        pid_file.write(f"{os.getpid()}\n")

    stdin_fd = os.open(os.devnull, os.O_RDONLY)
    log_fd = os.open(args.log_file, os.O_CREAT | os.O_WRONLY | os.O_TRUNC, 0o644)
    os.dup2(stdin_fd, 0)
    os.dup2(log_fd, 1)
    os.dup2(log_fd, 2)
    os.close(stdin_fd)
    os.close(log_fd)

    os.execvp(args.command[0], args.command)
    return 127


if __name__ == "__main__":
    raise SystemExit(main())
