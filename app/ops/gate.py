"""The app-wide reset gate (R74): every message holds it shared, the nightly reset holds it exclusively, so a message
never sees the scheduling tables half-restored. One machine and one worker, so an in-process lock is enough.

A waiting reset blocks new messages from starting, so a steady stream of messages cannot hold it off forever."""

import threading
from contextlib import contextmanager


class ResetGate:
    def __init__(self):
        self._turn = threading.Condition()
        self._readers = 0
        self._writing = False
        self._writers_waiting = 0

    @contextmanager
    def shared(self):
        with self._turn:
            while self._writing or self._writers_waiting:
                self._turn.wait()
            self._readers += 1
        try:
            yield
        finally:
            with self._turn:
                self._readers -= 1
                self._turn.notify_all()

    @contextmanager
    def exclusive(self):
        with self._turn:
            self._writers_waiting += 1
            while self._writing or self._readers:
                self._turn.wait()
            self._writers_waiting -= 1
            self._writing = True
        try:
            yield
        finally:
            with self._turn:
                self._writing = False
                self._turn.notify_all()
