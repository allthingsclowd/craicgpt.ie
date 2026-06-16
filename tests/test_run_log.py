"""Durable per-run log: the cli tees logging to <log_dir>/run-<UTC-date>.log so a
transient failure (e.g. the 2026-06-16 feed collapse) is inspectable on the host."""

from __future__ import annotations

import datetime as dt
import logging

from content_pipeline.agent import cli
from content_pipeline.content_config import content_cfg


def test_attach_run_logfile_writes_dated_log(tmp_path, monkeypatch):
    monkeypatch.setattr(content_cfg, "log_dir", str(tmp_path))
    path = cli._attach_run_logfile(now=dt.datetime(2026, 6, 16, tzinfo=dt.timezone.utc))
    try:
        assert path is not None
        assert path.name == "run-2026-06-16.log"
        logging.getLogger("content_pipeline.feeds").warning("3/3 feeds returned NO items: ['x']")
        for h in logging.getLogger().handlers:
            h.flush()
        body = path.read_text()
        assert "feeds returned NO items" in body
    finally:
        for h in list(logging.getLogger().handlers):
            if isinstance(h, logging.FileHandler) and str(path) == getattr(h, "baseFilename", ""):
                logging.getLogger().removeHandler(h)
                h.close()


def test_attach_run_logfile_is_best_effort(monkeypatch):
    # An unwritable log dir must NOT break the run — returns None, no raise.
    monkeypatch.setattr(content_cfg, "log_dir", "/proc/cannot/create/here")
    assert cli._attach_run_logfile() is None
