import pytest

from tro_frontier.trace import TraceState


def test_trace_order_is_enforced() -> None:
    trace = TraceState()
    assert trace.stage == "target"
    with pytest.raises(ValueError):
        trace.advance("assemble")
    for stage in ("rip", "assemble", "contain", "exit"):
        trace.advance(stage)
    assert trace.may_complete()
