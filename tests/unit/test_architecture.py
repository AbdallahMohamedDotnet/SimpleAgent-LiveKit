import ast
from pathlib import Path


def imported_modules(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    modules: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            modules.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            modules.add(node.module)
    return modules


def test_domain_and_application_do_not_import_infrastructure() -> None:
    source_root = Path(__file__).parents[2] / "src" / "interview_app"
    inspected = [
        *source_root.joinpath("domain").rglob("*.py"),
        *source_root.joinpath("application").rglob("*.py"),
    ]
    prohibited = (
        "interview_app.adapters",
        "livekit",
        "sqlite3",
        "aiohttp",
        "openai",
    )

    violations = {
        str(path.relative_to(source_root)): sorted(
            module
            for module in imported_modules(path)
            if module in prohibited or module.startswith(tuple(f"{name}." for name in prohibited))
        )
        for path in inspected
    }
    assert not {path: modules for path, modules in violations.items() if modules}


def test_no_http_server_surface_remains() -> None:
    source_root = Path(__file__).parents[2] / "src" / "interview_app"
    prohibited = ("http.server", "socketserver", "wsgiref", "aiohttp.web")

    offenders = {
        str(path.relative_to(source_root)): sorted(
            module for module in imported_modules(path) if module in prohibited
        )
        for path in source_root.rglob("*.py")
    }
    assert not {path: modules for path, modules in offenders.items() if modules}
    assert not (source_root / "adapters" / "web").exists()
