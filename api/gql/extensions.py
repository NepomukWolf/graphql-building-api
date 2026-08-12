from __future__ import annotations

import importlib.util
from pathlib import Path
from types import ModuleType
from typing import Any, Collection


def load_extensions(
    base_dir: Path,
    disabled: Collection[str] = (),
) -> tuple[list[str], list[Any]]:
    """Load GraphQL schema fragments and optional Ariadne bindables.

    An extension is any direct child directory containing a `schema.graphql`
    file. If a sibling `resolvers.py` exists, it may export `all_types`.

    Args:
        base_dir: Directory containing the extension directories.
        disabled: Extension directory names that should not be loaded.

    Returns:
        A tuple containing:
        - Schema definitions read from the extensions `schema.graphql`.
        - Ariadne bindables exported through each extensions `all_types`.
    """
    if not base_dir.is_dir():
        return [], []

    schemas: list[str] = []
    bindables: list[Any] = []

    disabled_names = set(disabled)
    for extension_dir in sorted(path for path in base_dir.iterdir() if path.is_dir()):
        if extension_dir.name in disabled_names:
            continue
        schema_path = extension_dir / "schema.graphql"
        if not schema_path.is_file():
            continue

        schemas.append(schema_path.read_text(encoding="utf-8"))
        bindables.extend(_load_extension_bindables(extension_dir))

    return schemas, bindables


def _load_extension_bindables(extension_dir: Path) -> list[Any]:
    resolver_path = extension_dir / "resolvers.py"
    if not resolver_path.is_file():
        return []

    module = _load_module(extension_dir.name, resolver_path)
    extension_types = getattr(module, "all_types", [])
    if extension_types is None:
        return []
    if not isinstance(extension_types, (list, tuple)):
        raise TypeError(
            f"Extension {extension_dir.name!r} resolvers.py must export all_types as a list or tuple."
        )
    return list(extension_types)


def _load_module(extension_name: str, resolver_path: Path) -> ModuleType:
    module_name = f"api.extensions.{_module_safe_name(extension_name)}.resolvers"
    spec = importlib.util.spec_from_file_location(module_name, resolver_path)
    if spec is None or spec.loader is None:
        raise ImportError(f"Could not load extension resolver module: {resolver_path}")

    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _module_safe_name(extension_name: str) -> str:
    return "".join(
        char if char.isalnum() or char == "_" else "_" for char in extension_name
    )
