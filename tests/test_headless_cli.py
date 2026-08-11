"""Templates, node migrations, and the headless CLI."""

from __future__ import annotations

import json

import pytest
from PIL import Image

from backend.artifacts.store import ArtifactStore, DesktopGrantStore
from backend.cli import build_parser, main
from backend.graph.executor import RunManager
from backend.graph.migrations import (
    MIGRATIONS,
    MigrationError,
    migrate_node,
    migrate_workflow,
    needs_migration,
    register,
)
from backend.graph.schema import WorkflowDocument
from backend.graph.templates import all_templates, get_template
from backend.graph.validation import validate_workflow

# --- templates ---------------------------------------------------------------


def test_every_template_is_a_valid_workflow():
    """A template that references a renamed node must fail here, not in the app."""
    for template in all_templates():
        document = WorkflowDocument.model_validate(template.document)
        result = validate_workflow(document)
        issues = result[0] if isinstance(result, tuple) else result
        errors = [issue for issue in issues if getattr(issue, "severity", "") == "error"]
        assert errors == [], f"{template.id}: {[issue.message for issue in errors]}"


def test_templates_have_stable_unique_ids():
    ids = [template.id for template in all_templates()]

    assert len(ids) == len(set(ids))
    assert "cutout-transparent" in ids


def test_templates_are_connected_end_to_end():
    """Every node past the first must receive an input, or the template is a stub."""
    for template in all_templates():
        document = WorkflowDocument.model_validate(template.document)
        fed = {edge.target_node_id for edge in document.edges}
        sources = {edge.source_node_id for edge in document.edges}
        for node in document.nodes[1:]:
            assert node.id in fed, f"{template.id}: {node.id} receives nothing"
        assert document.nodes[0].id in sources, f"{template.id}: first node feeds nothing"


def test_templates_leave_the_users_file_unset():
    """Templates supply the shape of the work, never someone else's file path."""
    for template in all_templates():
        for node in template.document["nodes"]:
            assert not node["parameters"].get("pathGrantId")


def test_unknown_template_is_reported():
    with pytest.raises(KeyError):
        get_template("does-not-exist")


# --- migrations --------------------------------------------------------------


@pytest.fixture
def migration(monkeypatch):
    """Register a throwaway migration without polluting the real registry."""
    monkeypatch.setattr("backend.graph.migrations.MIGRATIONS", dict(MIGRATIONS))
    return register


def test_a_node_at_the_current_version_is_left_alone():
    document = {
        "nodes": [
            {"id": "a", "schemaId": "lluna.input.image", "schemaVersion": 1, "parameters": {}}
        ]
    }

    migrated, applied = migrate_workflow(document)

    assert applied == []
    assert migrated["nodes"][0]["schemaVersion"] == 1
    assert needs_migration(document) is False


def test_an_old_node_without_a_migration_says_so():
    """The failure names the node and both versions, so it is actionable."""
    node = {"id": "a", "schemaId": "lluna.input.image", "schemaVersion": 1, "parameters": {}}

    with pytest.raises(MigrationError, match="no migration exists"):
        migrate_node(node, target=3)


def test_a_node_from_a_newer_build_is_refused():
    node = {"id": "a", "schemaId": "lluna.input.image", "schemaVersion": 9, "parameters": {}}

    with pytest.raises(MigrationError, match="newer than this build"):
        migrate_node(node, target=1)


def test_migrations_chain_across_versions(migration):
    """A node saved two versions back walks forward one step at a time."""
    seen = []

    @migration("test.node", 1)
    def _one(node):
        seen.append(1)
        # Copy first, then rename: a dict spread is evaluated before the pop,
        # so the one-liner form would leave the old key behind.
        parameters = dict(node["parameters"])
        parameters["renamed"] = parameters.pop("old")
        return {**node, "parameters": parameters}

    @migration("test.node", 2)
    def _two(node):
        seen.append(2)
        return {**node, "parameters": {**node["parameters"], "extra": True}}

    node = {"id": "a", "schemaId": "test.node", "schemaVersion": 1, "parameters": {"old": 5}}
    migrated, applied = migrate_node(node, target=3)

    assert seen == [1, 2]
    assert migrated["schemaVersion"] == 3
    assert migrated["parameters"] == {"renamed": 5, "extra": True}
    assert applied == ["test.node v1->v2", "test.node v2->v3"]


def test_unknown_node_types_pass_through_untouched():
    """Validation reports these far better than a migration error could."""
    document = {"nodes": [{"id": "a", "schemaId": "some.plugin.node", "schemaVersion": 4}]}

    migrated, applied = migrate_workflow(document)

    assert applied == []
    assert migrated["nodes"][0]["schemaVersion"] == 4


def test_a_registry_refuses_two_migrations_for_the_same_step(migration):
    @migration("test.dup", 1)
    def _first(node):
        return node

    with pytest.raises(ValueError, match="already exists"):

        @migration("test.dup", 1)
        def _second(node):
            return node


def test_malformed_documents_are_rejected_clearly():
    with pytest.raises(MigrationError, match="not a list"):
        migrate_workflow({"nodes": "everything"})
    with pytest.raises(MigrationError, match="not an object"):
        migrate_workflow({"nodes": ["a node"]})


# --- CLI ---------------------------------------------------------------------


def test_parser_requires_a_workflow_or_a_template():
    with pytest.raises(SystemExit):
        build_parser().parse_args(["run"])


def test_templates_command_lists_every_template(capsys):
    assert main(["templates"]) == 0

    printed = capsys.readouterr().out
    for template in all_templates():
        assert template.id in printed


def test_templates_command_can_emit_json(capsys):
    assert main(["templates", "--json"]) == 0

    payload = json.loads(capsys.readouterr().out)
    assert {item["id"] for item in payload} == {item.id for item in all_templates()}


def test_a_missing_workflow_file_fails_before_starting_a_run(capsys):
    with pytest.raises(SystemExit, match="Could not read"):
        main(["run", "/nonexistent/graph.lluna.json"])


def test_an_unknown_template_lists_the_real_ones():
    with pytest.raises(SystemExit, match="Available:"):
        main(["run", "--template", "nope"])


def test_invalid_json_is_reported_with_the_path(tmp_path):
    broken = tmp_path / "broken.lluna.json"
    broken.write_text("{not json", encoding="utf-8")

    with pytest.raises(SystemExit, match="not valid JSON"):
        main(["run", str(broken)])


def test_run_executes_a_workflow_and_writes_artifacts(tmp_path, monkeypatch, capsys):
    """The whole point of the CLI: a file in, a file out, an exit code."""
    monkeypatch.setenv("LLUNA_FAKE_WORKER", "1")
    source = tmp_path / "input.png"
    Image.new("RGBA", (4, 3), (10, 20, 30, 255)).save(source)
    ArtifactStore._instance = ArtifactStore(tmp_path / "artifacts")
    DesktopGrantStore._instance = None
    grant = DesktopGrantStore.instance().issue(source)
    RunManager._instance = None

    workflow = {
        "format": "lluna-workflow",
        "version": 1,
        "name": "cli run",
        "nodes": [
            {
                "id": "load",
                "schemaId": "lluna.input.image",
                "position": {"x": 0, "y": 0},
                "parameters": {"pathGrantId": grant.grant_id},
            },
            {
                "id": "preview",
                "schemaId": "lluna.output.preview_image",
                "position": {"x": 320, "y": 0},
                "parameters": {},
            },
        ],
        "edges": [
            {
                "sourceNodeId": "load",
                "sourcePortId": "image",
                "targetNodeId": "preview",
                "targetPortId": "image",
            }
        ],
    }
    path = tmp_path / "graph.lluna.json"
    path.write_text(json.dumps(workflow), encoding="utf-8")
    out = tmp_path / "results"

    code = main(["run", str(path), "--out", str(out), "--timeout", "30"])

    printed = capsys.readouterr()
    assert code == 0, printed.err
    exported = list(out.iterdir())
    assert exported, "no artifacts were exported"
    # An artifact carried through several nodes is listed repeatedly by the run;
    # it must still be reported and written once.
    assert printed.out.count("wrote ") == len(exported)
