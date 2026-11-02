from ci_scope import scope


def describe_scope() -> None:
    def it_narrows_to_e2e_for_e2e_tests_and_receipts() -> None:
        assert scope(["packages/python/tests/e2e/a_test.py", "packages/python/e2e-attestations/b.json"]) == "e2e"

    def it_narrows_to_integration() -> None:
        assert scope(["packages/python/tests/integration/a_test.py"]) == "integration"

    def it_narrows_to_unit_for_colocated_tests() -> None:
        assert scope(["packages/python/src/botbox/a_test.py"]) == "unit"

    def it_is_full_for_source() -> None:
        assert scope(["packages/python/src/botbox/a.py"]) == "full"

    def it_is_full_for_a_mix_of_kinds() -> None:
        assert scope(["packages/python/tests/e2e/a_test.py", "packages/python/tests/integration/b_test.py"]) == "full"

    def it_is_full_for_workflows() -> None:
        assert scope(["packages/python/tests/e2e/a_test.py", ".github/workflows/python.yml"]) == "full"

    def it_ignores_docs() -> None:
        assert scope(["packages/python/tests/e2e/a_test.py", "docs/changelog.d/x.md"]) == "e2e"
