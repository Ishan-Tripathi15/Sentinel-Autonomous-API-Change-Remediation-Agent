from __future__ import annotations

from sentinel.worker_service import install_signal_handlers


def test_signal_handlers_request_stop(monkeypatch) -> None:
    installed = {}

    def fake_signal(signum, handler):
        installed[signum] = handler

    monkeypatch.setattr("sentinel.worker_service.signal", fake_signal)

    class Runtime:
        def __init__(self) -> None:
            self.stopped = False

        def request_stop(self) -> None:
            self.stopped = True

    runtime = Runtime()
    install_signal_handlers(runtime)  # type: ignore[arg-type]

    assert len(installed) == 2
    for handler in installed.values():
        handler(15, None)
    assert runtime.stopped
