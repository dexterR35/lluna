"""RuntimeAdapter wrappers over the built-in ai/runtimes modules.

Each built-in runtime (Real-ESRGAN, MIRNet, LaMa, select-object, native
BiRefNet, the diffusion generate stack) already manages its own lazy-loaded,
process-global singleton and a `release_*()` teardown function - that
internal state is not touched here. These adapters exist only to give
`backend.models.manager.ModelManager` the same `load/run/unload/estimate`
shape it already has for manifest-backed models (`backend.models.adapters`),
so one LRU cache and one eviction policy can see every resident model,
built-in or custom, instead of two blind-to-each-other mechanisms.
"""

from __future__ import annotations

from typing import Any

from backend.models.adapters import CancelEvent, Progress, RuntimeAdapter


class _BuiltinAdapter(RuntimeAdapter):
    """`load()` is a marker only - the wrapped module lazy-loads on first
    `run()` and caches until its own release function runs. `unload()`
    triggers that release so ModelManager's eviction reaches it generically.
    """

    def load(self, record: Any = None, *, dtype: str | None = None) -> Any:
        del record, dtype
        return self.id

    def unload(self, loaded: Any) -> None:
        del loaded
        self._release()

    def _release(self) -> None:
        raise NotImplementedError

    def health_check(self, loaded: Any) -> bool:
        return True


class RealesrganAdapter(_BuiltinAdapter):
    id = "builtin:realesrgan"
    supported_tasks = ("enhance",)

    def run(self, loaded: Any, inputs: dict[str, Any], *, progress: Progress = None, cancel_event: CancelEvent = None) -> Any:
        from backend.ai.runtimes.realesrgan import enhance_rgba

        return enhance_rgba(
            inputs["image"],
            inputs["mode"],
            progress=progress,
            cancel_event=cancel_event,
            options=inputs.get("options"),
        )

    def estimate(self, record: Any = None, **kwargs: Any):
        from backend.tools.shared.memory import pick_enhance_tile

        return pick_enhance_tile(
            int(kwargs["h"]), int(kwargs["w"]), int(kwargs["scale"]), int(kwargs["max_long_edge"])
        )

    def _release(self) -> None:
        from backend.ai.runtimes.realesrgan import release_enhance_models

        release_enhance_models(blocking=True, timeout=5.0)


class MirnetAdapter(_BuiltinAdapter):
    id = "builtin:mirnet"
    supported_tasks = ("low-light",)

    def run(self, loaded: Any, inputs: dict[str, Any], *, progress: Progress = None, cancel_event: CancelEvent = None) -> Any:
        from backend.ai.runtimes.mirnet import enhance_rgb

        return enhance_rgb(inputs["image"], inputs["mode"], progress=progress, cancel_event=cancel_event)

    def _release(self) -> None:
        from backend.ai.runtimes.mirnet import release_low_light_models

        release_low_light_models(blocking=True, timeout=5.0)


class LamaAdapter(_BuiltinAdapter):
    id = "builtin:lama"
    supported_tasks = ("retouch",)

    def run(self, loaded: Any, inputs: dict[str, Any], *, progress: Progress = None, cancel_event: CancelEvent = None) -> Any:
        from backend.ai.runtimes.inpaint import get_retouch_lama

        lama = get_retouch_lama(inputs.get("model_path"))
        return lama.inpaint(inputs["rgb"], inputs["mask"])

    def estimate(self, record: Any = None, **kwargs: Any):
        from backend.tools.shared.memory import preflight_lama

        return preflight_lama(int(kwargs["h"]), int(kwargs["w"]))

    def _release(self) -> None:
        from backend.ai.runtimes.inpaint import release_retouch_lama

        release_retouch_lama()


class VideoInpaintAdapter(_BuiltinAdapter):
    """STTN/ProPainter dispatch stays in `backend.inpaint.*`; this adapter only
    tracks occupancy so ModelManager's eviction can release it generically."""

    id = "builtin:video_inpaint"
    supported_tasks = ("video-inpaint",)

    def run(self, loaded: Any, inputs: dict[str, Any], *, progress: Progress = None, cancel_event: CancelEvent = None) -> Any:
        raise NotImplementedError(
            "Video inpaint runs through backend.inpaint.* directly; this adapter "
            "only owns cache occupancy and release."
        )

    def _release(self) -> None:
        from backend.ai.runtimes.inpaint import release_video_inpaint_models

        release_video_inpaint_models()



class BirefnetNativeAdapter(_BuiltinAdapter):
    id = "builtin:birefnet"
    supported_tasks = ("remove-background",)

    def run(self, loaded: Any, inputs: dict[str, Any], *, progress: Progress = None, cancel_event: CancelEvent = None) -> Any:
        from backend.ai.runtimes.birefnet import process_image, process_video

        params = {k: v for k, v in inputs.items() if k not in {"media_type", "progress", "cancel_event"}}
        if inputs.get("media_type") == "video":
            return process_video(progress=progress, cancel_event=cancel_event, **params)
        return process_image(**params)

    def estimate(self, record: Any = None, **kwargs: Any):
        from backend.tools.shared.memory import preflight_birefnet

        return preflight_birefnet(int(kwargs["resolution"]), precision=kwargs.get("precision", "auto"))

    def _release(self) -> None:
        from backend.ai.runtimes.birefnet import release_models

        release_models()


class DiffusionGenerateAdapter(_BuiltinAdapter):
    id = "builtin:generate"
    supported_tasks = ("generate",)

    def run(self, loaded: Any, inputs: dict[str, Any], *, progress: Progress = None, cancel_event: CancelEvent = None) -> Any:
        from backend.ai.runtimes.diffusion import generate_image

        params = dict(inputs)
        prompt = params.pop("prompt")
        mode = params.pop("mode")
        return generate_image(prompt, mode, progress=progress, cancel_event=cancel_event, **params)

    def estimate(self, record: Any = None, **kwargs: Any):
        from backend.tools.shared.memory import preflight_minimum

        return preflight_minimum(
            str(kwargs.get("mode", "generate")),
            float(kwargs.get("minimum_vram_mb") or 0),
            hint=kwargs.get("hint", ""),
            allow_cpu_offload=bool(kwargs.get("allow_cpu_offload", False)),
        )

    def _release(self) -> None:
        from backend.ai.runtimes.diffusion import release_generate_models

        release_generate_models(blocking=True, timeout=5.0)


BUILTIN_ADAPTERS: dict[str, RuntimeAdapter] = {
    adapter.id: adapter
    for adapter in (
        RealesrganAdapter(),
        MirnetAdapter(),
        LamaAdapter(),
        VideoInpaintAdapter(),
        BirefnetNativeAdapter(),
        DiffusionGenerateAdapter(),
    )
}
