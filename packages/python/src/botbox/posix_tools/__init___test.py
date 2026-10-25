import ast
from pathlib import Path


def describe_package_isolation() -> None:
    def it_imports_no_botbox_modules() -> None:
        root = Path(__file__).parent
        for source in root.rglob("*.py"):
            for node in ast.walk(ast.parse(source.read_text())):
                if isinstance(node, ast.Import):
                    modules = [alias.name for alias in node.names]
                elif isinstance(node, ast.ImportFrom) and node.level == 0:
                    modules = [node.module or ""]
                else:
                    continue
                assert all(module.split(".")[0] != "botbox" for module in modules), (
                    f"{source.relative_to(root)}:{node.lineno} imports botbox"
                )
