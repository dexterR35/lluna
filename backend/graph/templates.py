"""Ready-made workflows, so a new graph does not start from an empty canvas.

A template is an ordinary workflow document — the same shape saved to
``*.lluna.json`` — not a special kind of object. Dropping one on the canvas gives
the user a working chain they can run immediately and then edit, which is a much
better first five minutes than wiring five nodes correctly by hand.

Templates are built from the node registry rather than stored as files so they
cannot drift: a test compiles every one of them, so a template that references a
renamed node or a port that no longer exists fails the build instead of failing
in the user's hands.

Input nodes are deliberately left unconfigured. A template supplies the *shape*
of the work; the file to operate on is always the user's own.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class WorkflowTemplate:
    id: str
    name: str
    description: str
    category: str
    document: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "category": self.category,
            "document": self.document,
        }


def _node(node_id: str, schema_id: str, x: float, y: float, **parameters) -> dict[str, Any]:
    return {
        "id": node_id,
        "schemaId": schema_id,
        "position": {"x": x, "y": y},
        "parameters": parameters,
    }


def _edge(source: str, source_port: str, target: str, target_port: str) -> dict[str, Any]:
    return {
        "sourceNodeId": source,
        "sourcePortId": source_port,
        "targetNodeId": target,
        "targetPortId": target_port,
    }


def _document(name: str, nodes: list[dict], edges: list[dict]) -> dict[str, Any]:
    return {"format": "lluna-workflow", "version": 1, "name": name, "nodes": nodes, "edges": edges}


# Laid out left to right at a fixed spacing so a dropped template is readable
# without the user rearranging it first.
_STEP = 320.0


def _chain(name: str, steps: list[tuple[str, str, str]]) -> dict[str, Any]:
    """Build a straight-line workflow from (node id, schema id, port) triples.

    ``port`` is the output port each step hands to the next; the target port is
    resolved from the next node's first input.
    """
    from backend.graph.registry import NODE_REGISTRY

    nodes = [
        _node(node_id, schema_id, index * _STEP, 0.0)
        for index, (node_id, schema_id, _port) in enumerate(steps)
    ]
    edges = []
    for index in range(len(steps) - 1):
        _source_id, _source_schema, source_port = steps[index]
        target_id, target_schema, _ = steps[index + 1]
        target_inputs = NODE_REGISTRY[target_schema].inputs
        target_port = next(
            (port.id for port in target_inputs if port.required),
            target_inputs[0].id if target_inputs else "image",
        )
        edges.append(_edge(steps[index][0], source_port, target_id, target_port))
    return _document(name, nodes, edges)


def all_templates() -> tuple[WorkflowTemplate, ...]:
    """Every bundled template, in the order they should be offered."""
    return (
        WorkflowTemplate(
            "remove-text-image",
            "Remove text from an image",
            "Detects burned-in text or a watermark and paints it out.",
            "Clean up",
            _chain(
                "Remove text from an image",
                [
                    ("load", "lluna.input.image", "image"),
                    ("clean", "lluna.image.remove_text", "image"),
                    ("save", "lluna.output.save_image", "image"),
                ],
            ),
        ),
        WorkflowTemplate(
            "remove-subtitles-video",
            "Remove subtitles from a video",
            "Finds subtitles frame by frame and inpaints them away.",
            "Clean up",
            _chain(
                "Remove subtitles from a video",
                [
                    ("load", "lluna.input.video", "video"),
                    ("clean", "lluna.video.remove_text", "video"),
                    ("save", "lluna.output.save_video", "video"),
                ],
            ),
        ),
        WorkflowTemplate(
            "cutout-transparent",
            "Cut out a transparent subject",
            "Removes the background and saves a transparent PNG.",
            "Cut out",
            _chain(
                "Cut out a transparent subject",
                [
                    ("load", "lluna.input.image", "image"),
                    ("cutout", "lluna.image.remove_background", "image"),
                    ("save", "lluna.output.save_image", "image"),
                ],
            ),
        ),
        WorkflowTemplate(
            "upscale-image",
            "Upscale an image",
            "Enlarges an image and restores detail.",
            "Restore",
            _chain(
                "Upscale an image",
                [
                    ("load", "lluna.input.image", "image"),
                    ("upscale", "lluna.image.upscale", "image"),
                    ("save", "lluna.output.save_image", "image"),
                ],
            ),
        ),
        WorkflowTemplate(
            "fix-low-light",
            "Fix a low-light photo",
            "Brightens a dark photo without washing out colour.",
            "Restore",
            _chain(
                "Fix a low-light photo",
                [
                    ("load", "lluna.input.image", "image"),
                    ("fix", "lluna.image.low_light", "image"),
                    ("save", "lluna.output.save_image", "image"),
                ],
            ),
        ),
        WorkflowTemplate(
            "generate-and-upscale",
            "Generate, then upscale",
            "Writes a prompt, generates an image, and enlarges the result.",
            "Create",
            _chain(
                "Generate, then upscale",
                [
                    ("prompt", "lluna.input.prompt", "prompt"),
                    ("generate", "lluna.generate.image", "image"),
                    ("upscale", "lluna.image.upscale", "image"),
                    ("save", "lluna.output.save_image", "image"),
                ],
            ),
        ),
        WorkflowTemplate(
            "describe-then-generate",
            "Describe an image, then generate a new one",
            "Captions an image with a vision model and feeds that into generation.",
            "Create",
            _chain(
                "Describe an image, then generate a new one",
                [
                    ("load", "lluna.input.image", "image"),
                    ("describe", "lluna.input.describe_image", "prompt"),
                    ("generate", "lluna.generate.image", "image"),
                    ("save", "lluna.output.save_image", "image"),
                ],
            ),
        ),
    )


def get_template(template_id: str) -> WorkflowTemplate:
    for template in all_templates():
        if template.id == template_id:
            return template
    raise KeyError(template_id)
