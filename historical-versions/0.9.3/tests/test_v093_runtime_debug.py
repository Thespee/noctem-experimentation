"""Tests for v0.9.3 runtime debug logging behavior."""
import logging

from noctem import main as main_module


def _record(name: str, level: int) -> logging.LogRecord:
    return logging.LogRecord(
        name=name,
        level=level,
        pathname=__file__,
        lineno=1,
        msg="message",
        args=(),
        exc_info=None,
    )


def test_noctem_debug_filter_suppresses_info_and_non_noctem_debug():
    debug_filter = main_module._NoctemDebugFilter()

    assert debug_filter.filter(_record("noctem.agent.workflow", logging.DEBUG)) is True
    assert debug_filter.filter(_record("httpx", logging.DEBUG)) is False
    assert debug_filter.filter(_record("noctem.agent.workflow", logging.INFO)) is False
    assert debug_filter.filter(_record("noctem.agent.workflow", logging.WARNING)) is True


def test_setup_logging_debug_sets_debug_level_and_filter():
    main_module.setup_logging(quiet=False, debug=True)
    root = logging.getLogger()
    assert root.level == logging.DEBUG
    assert any(
        isinstance(active_filter, main_module._NoctemDebugFilter)
        for handler in root.handlers
        for active_filter in handler.filters
    )
