"""App-wide GPU job gate: one model worker / one tool at a time."""

from __future__ import annotations

from typing import Optional

from backend.config import tr
from backend.tools.infer_client import InferClient
from backend.tools.infer_protocol import JobType


_JOB_LABEL_KEYS = {
    JobType.GENERATE.value: "JobGenerate",
    JobType.BG_REMOVE.value: "JobBgRemove",
    JobType.ENHANCE.value: "JobEnhance",
    JobType.LOW_LIGHT.value: "JobLowLight",
    JobType.SUBTITLE.value: "JobSubtitle",
    JobType.LAMA_RETOUCH.value: "JobRetouch",
    JobType.SELECT_SUBJECT.value: "JobSelectObject",
}


def _infer_section():
    return tr["Infer"] if "Infer" in tr else {}


def job_type_label(job_type: Optional[str]) -> str:
    section = _infer_section()
    if not job_type:
        return section.get("JobUnknown", "another tool")
    key = _JOB_LABEL_KEYS.get(str(job_type))
    if key:
        return section.get(key, str(job_type).replace("_", " "))
    return str(job_type).replace("_", " ")


def gpu_busy_message(active_type: Optional[str] = None) -> str:
    section = _infer_section()
    jt = active_type
    if jt is None:
        try:
            jt = InferClient.instance().active_job_type()
        except Exception:
            jt = None
    if jt:
        return section.get(
            "GpuBusy",
            "Another tool is using the GPU ({}). Wait for it to finish or stop it first.",
        ).format(job_type_label(jt))
    return section.get(
        "GpuBusyUnknown",
        "Another tool is using the GPU. Wait for it to finish or stop it first.",
    )


def is_gpu_busy() -> bool:
    try:
        return InferClient.instance().is_busy()
    except Exception:
        return False
