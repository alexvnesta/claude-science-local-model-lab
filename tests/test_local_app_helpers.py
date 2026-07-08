#!/usr/bin/env python3
"""Tests for local Claude Science helper defaults."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def load_script(name: str, relative_path: str):
    spec = importlib.util.spec_from_file_location(name, ROOT / relative_path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_submit_helper_reads_local_app_env_defaults(monkeypatch) -> None:
    submit = load_script("submit_local_request", "scripts/submit-local-request.py")
    monkeypatch.setenv("CLAUDE_SCIENCE_LOCAL_DATA_DIR", "/tmp/claude-science-data")
    monkeypatch.setenv("CLAUDE_SCIENCE_LOCAL_CONFIG", "/tmp/claude-science.toml")
    monkeypatch.setenv("CLAUDE_SCIENCE_LOCAL_PORT", "19999")
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "submit-local-request.py",
            "--project-id",
            "proj_test",
            "hello",
        ],
    )

    args = submit.parse_args()

    assert args.data_dir == "/tmp/claude-science-data"
    assert args.config == "/tmp/claude-science.toml"
    assert args.app_port == "19999"


def test_resolve_helper_reads_local_app_env_defaults(monkeypatch) -> None:
    resolve = load_script("resolve_input_request", "scripts/resolve-input-request.py")
    monkeypatch.setenv("CLAUDE_SCIENCE_LOCAL_DATA_DIR", "/tmp/claude-science-data")
    monkeypatch.setenv("CLAUDE_SCIENCE_LOCAL_CONFIG", "/tmp/claude-science.toml")
    monkeypatch.setenv("CLAUDE_SCIENCE_LOCAL_PORT", "19999")
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "resolve-input-request.py",
            "--frame-id",
            "frame_test",
            "--request-id",
            "req_test",
            "--tool-id",
            "tool_test",
        ],
    )

    args = resolve.parse_args()

    assert args.data_dir == "/tmp/claude-science-data"
    assert args.config == "/tmp/claude-science.toml"
    assert args.app_port == "19999"
