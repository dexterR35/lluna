from __future__ import annotations


class FakeUpdateClient:
    def __init__(self, result) -> None:
        self.result = result
        self.calls = 0

    def check(self):
        self.calls += 1
        return self.result
