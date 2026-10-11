"""Tests for the changelog-fragment enforcement gate."""

from ci.check_changelog import (
    added_fragments,
    changed_packages,
    code_touched,
    has_skip_trailer,
    malformed_fragments,
)


def test_skip_trailer_detected():
    assert has_skip_trailer("feat: thing\n\nskip-changelog: internal refactor")


def test_skip_trailer_is_case_insensitive():
    assert has_skip_trailer("Skip-Changelog: yes")


def test_skip_trailer_absent():
    assert not has_skip_trailer("feat: add a public method\n\nbody text")


def test_skip_trailer_must_start_a_line():
    assert not has_skip_trailer("see skip-changelog: in the docs")


def test_changed_packages_unique_and_sorted():
    changed = [
        "packages/python/foo.py",
        "packages/node/src/bar.ts",
        "packages/python/baz.py",
        "README.md",
        "packages",  # too short to name a package
    ]
    assert changed_packages(changed) == ["node", "python"]


def test_changed_packages_none_outside_packages():
    assert (
        changed_packages(["README.md", "docs/x.md", ".github/workflows/ci.yml"]) == []
    )


def test_code_touched_true_for_source():
    assert code_touched(["packages/python/core.py"], "python")


def test_code_touched_false_for_pointer_stubs():
    assert not code_touched(["packages/python/CHANGELOG.md"], "python")
    assert not code_touched(["packages/python/MIGRATIONS.md"], "python")


def test_code_touched_false_for_dot_test_sources():
    assert not code_touched(["packages/node/src/bar.test.ts"], "node")
    assert not code_touched(["packages/node/src/bar.spec.tsx"], "node")


def test_code_touched_false_for_test_directories():
    assert not code_touched(["packages/python/tests/conftest.py"], "python")
    assert not code_touched(["packages/node/__tests__/x.ts"], "node")


def test_code_touched_ignores_other_packages():
    assert not code_touched(["packages/node/src/bar.ts"], "python")


def test_underscore_python_test_counts_as_code():
    # NB: faithful to the original workflow regex, which exempts dot-style
    # `foo.test.py` but NOT underscore-style `foo_test.py` (this repo's actual
    # Python colocation convention). Flagged to the maintainer as a pre-existing
    # quirk; preserved here so the extraction is behavior-identical.
    assert code_touched(["packages/python/core_test.py"], "python")


def test_added_fragment_in_changelog_d_counts():
    added = ["docs/changelog.d/2026-07-10-node-fix-cascade-ordering.md"]
    assert added_fragments(added, "node") == added


def test_added_fragment_in_migrations_d_counts():
    added = ["docs/migrations.d/2026-07-12-python-rename-config-key.md"]
    assert added_fragments(added, "python") == added


def test_added_fragment_for_other_package_does_not_count():
    added = ["docs/changelog.d/2026-07-10-node-fix-cascade-ordering.md"]
    assert added_fragments(added, "python") == []


def test_added_fragment_requires_slug_after_package():
    # A bare `<date>-<pkg>.md` names no change; the slug is mandatory.
    assert added_fragments(["docs/changelog.d/2026-07-10-node.md"], "node") == []


def test_added_fragment_ignores_paths_outside_fragment_dirs():
    added = [
        "docs/2026-07-10-node-fix.md",
        "docs/changelog.d/nested/2026-07-10-node-fix.md",
    ]
    assert added_fragments(added, "node") == []


def test_malformed_fragments_flags_bad_names():
    changed = [
        "docs/changelog.d/Node-fix.md",  # no date, uppercase
        "docs/migrations.d/2026-07-10-node-fix.txt",  # wrong extension
    ]
    assert malformed_fragments(changed) == changed


def test_malformed_fragments_allows_wellformed_and_readme():
    changed = [
        "docs/changelog.d/2026-07-10-node-fix-cascade-ordering.md",
        "docs/changelog.d/README.md",
        "docs/migrations.d/README.md",
    ]
    assert malformed_fragments(changed) == []


def test_malformed_fragments_ignores_files_outside_fragment_dirs():
    assert malformed_fragments(["docs/migrations.md", "README.md"]) == []
