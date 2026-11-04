"""Foundry validator — checks source modules against the six DFT axioms.

The validator is pure: it operates on file contents (strings) and returns
a list of :class:`~phosphene.imi_wordpress.dft.DftViolation`. It never
touches the filesystem in its pure checks — the CLI wrapper
(:func:`validate_package`) reads files and passes them to the pure
:func:`validate_module`.

@dft
- A1 (pure-io-separation): ``validate_module`` is pure — no I/O.
- A2 (determinism): no time/random/uuid. Same input → same output.
- A6 (check-result): returns ``list[DftViolation]``, not ``bool``.
"""

from __future__ import annotations

import ast
from pathlib import Path

from phosphene.imi_wordpress.dft import (
    A1_PURE_IO_SEPARATION,
    A2_DETERMINISM,
    A4_DFT_DOCS,
    DftViolation,
)

# ── A1: I/O modules banned in pure logic ─────────────────────────

IO_MODULES = frozenset(
    {
        "urllib.request",
        "urllib.error",
        "urllib.parse",
        "http.client",
        "http.server",
        "socket",
        "subprocess",
        "ssl",
        "requests",
        "httpx",
        "aiohttp",
    }
)

# Modules that ARE allowed to import I/O (the I/O wiring layer)
IO_WIRING_MODULES = frozenset(
    {
        "client.py",
        "db_client.py",
        "dryrun.py",
        "fakes.py",
        "testing/wp_test_client.py",
        "test_setup.py",
        "parity_harness.py",  # the harness wires REST + DB
        "pipeline.py",  # the pipeline wires outlets
        "dft.py",  # SystemClock imports datetime/time
        "foundry.py",  # reads files
    }
)


def _is_io_wiring(file_path: str) -> bool:
    """True if this file is an I/O wiring module (allowed to import I/O)."""
    # Check both the basename and the path-relative-to-package
    basename = Path(file_path).name
    if basename in IO_WIRING_MODULES:
        return True
    # Check path suffix (e.g. "testing/wp_test_client.py")
    for io_mod in IO_WIRING_MODULES:
        if file_path.endswith(io_mod):
            return True
    return False


# ── A2: non-deterministic calls banned in pure logic ────────────

NON_DETERMINISTIC_CALLS = frozenset(
    {
        "datetime.now",
        "datetime.datetime.now",
        "datetime.today",
        "datetime.datetime.today",
        "datetime.utcnow",
        "datetime.datetime.utcnow",
        "time.time",
        "time.monotonic",
        "uuid.uuid4",
        "uuid.uuid1",
        "random.random",
        "random.randint",
        "random.choice",
        "random.uniform",
    }
)


def _extract_imports(source: str) -> list[str]:
    """Extract all imported module names from Python source (AST-based)."""
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return []
    imports: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                imports.append(alias.name)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imports.append(node.module)
    return imports


def _extract_call_names(source: str) -> list[str]:
    """Extract all function call qualified names (e.g. ``datetime.now``)."""
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return []
    calls: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            name = _get_attr_name(node.func)
            if name:
                calls.append(name)
    return calls


def _get_attr_name(node: ast.expr) -> str | None:
    """Get the dotted name of an attribute/call (e.g. ``a.b.c``)."""
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        base = _get_attr_name(node.value)
        if base:
            return f"{base}.{node.attr}"
        return node.attr
    return None


def _has_dft_docstring(source: str) -> bool:
    """Check if a module's docstring contains a @dft section."""
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return False
    if not tree.body:
        return False
    first = tree.body[0]
    if not isinstance(first, ast.Expr) or not isinstance(first.value, ast.Constant):
        return False
    docstring = first.value.value
    if not isinstance(docstring, str):
        return False
    return "@dft" in docstring


def validate_module(file_path: str, source: str) -> list[DftViolation]:
    """Validate a single Python source file against the DFT axioms.

    Pure: operates on the source string, returns violations. No I/O.

    Args:
        file_path: Relative path (for violation reporting).
        source: The Python source code string.

    Returns:
        List of DftViolation (empty if compliant).
    """
    violations: list[DftViolation] = []
    basename = Path(file_path).name
    is_io = _is_io_wiring(file_path)

    # A4: dft-docs — every module needs a @dft docstring section
    # (skip __init__.py — they're often empty or just imports)
    if basename != "__init__.py" and not _has_dft_docstring(source):
        violations.append(
            DftViolation(
                axiom=A4_DFT_DOCS,
                file=file_path,
                message="Module docstring missing @dft section — document which axioms apply",
                severity="error",
            )
        )

    # A1: pure-io-separation — logic modules must not import I/O
    if not is_io:
        imports = _extract_imports(source)
        for imp in imports:
            # Check if any banned I/O module is imported (exact or prefix)
            for io_mod in IO_MODULES:
                if imp == io_mod or imp.startswith(io_mod + "."):
                    violations.append(
                        DftViolation(
                            axiom=A1_PURE_IO_SEPARATION,
                            file=file_path,
                            message=f'Logic module imports I/O module "{imp}" — move I/O to a wiring module or behind a Protocol',
                            severity="error",
                        )
                    )

    # A2: determinism — logic modules must not call non-deterministic functions
    # (io wiring modules are allowed to use datetime/time for real I/O timestamps)
    if not is_io:
        calls = _extract_call_names(source)
        for call in calls:
            if call in NON_DETERMINISTIC_CALLS:
                violations.append(
                    DftViolation(
                        axiom=A2_DETERMINISM,
                        file=file_path,
                        message=f'Logic module calls non-deterministic function "{call}" — inject a Clock or IdGenerator',
                        severity="error",
                    )
                )

    return violations


def validate_package(src_dir: Path) -> list[DftViolation]:
    """Validate all Python source files in a package directory.

    This is the I/O wrapper — it reads files and calls :func:`validate_module`.

    Args:
        src_dir: Path to the source directory (e.g. ``src/phosphene/imi_wordpress``).

    Returns:
        List of DftViolation across all files.
    """
    violations: list[DftViolation] = []
    for py_file in sorted(src_dir.rglob("*.py")):
        if "__pycache__" in py_file.parts:
            continue
        rel_path = str(py_file.relative_to(src_dir.parent.parent))  # relative to src/
        source = py_file.read_text(encoding="utf-8")
        violations.extend(validate_module(rel_path, source))
    return violations


def has_errors(violations: list[DftViolation]) -> bool:
    """True if any violation has severity 'error'."""
    return any(v.severity == "error" for v in violations)


def format_violations(violations: list[DftViolation]) -> str:
    """Format violations for CLI output."""
    if not violations:
        return "✓ all six DFT axioms pass."
    lines: list[str] = []
    for v in violations:
        icon = "✗" if v.severity == "error" else "⚠"
        lines.append(f"  {icon} [{v.axiom}] {v.file}: {v.message}")
    errors = sum(1 for v in violations if v.severity == "error")
    warns = sum(1 for v in violations if v.severity == "warn")
    lines.append("")
    lines.append(f"{errors} error(s), {warns} warning(s)")
    return "\n".join(lines)
