from __future__ import annotations


class FakeModelLoader:
    def __init__(self, *, failure: BaseException | None = None) -> None:
        self.failure = failure
        self.loaded: list[str] = []
        self.unloaded: list[str] = []

    def load(self, model_id: str) -> object:
        if self.failure:
            raise self.failure
        self.loaded.append(model_id)
        return {"model_id": model_id}

    def unload(self, model_id: str) -> None:
        self.unloaded.append(model_id)
