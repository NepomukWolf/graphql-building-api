import os
import shutil
import logging
from typing import Dict, Any
import ifcopenshell
import json
from pathlib import Path

from graphql_building_api.config import GeometryConfig
from graphql_building_graphql_building_api.ifc.geometry import GeometryHandler
from graphql_building_graphql_building_api.ifc.geometry_formats import GEOMETRY_FORMATS, normalize_geometry_format
from graphql_building_graphql_building_api.ifc.geometry_service import GeometryRequest, geometry_service

logger = logging.getLogger(__name__)


def generate_geometry(
    ifc_path: str, formats: list[str] | None = None, pretty: bool = False
) -> Dict[str, Any] | str:
    """Generate geometry files from an IFC file for a quick local showcase.

    Steps (for local prototype):
    - create folder `graphql_building_api/static/models/<model_name>` (model_name is the IFC filename without ext)
    - copy the original IFC file into that folder
    - create `elements` subfolder
    - open the IFC model and iterate products; for each product that yields geometry:
        - create `elements/<GlobalId>/`
        - export one file per requested Trimesh-backed format as `geometry<extension>`

    Returns a summary dict with paths and counts.
    """
    if not os.path.isfile(ifc_path):
        raise FileNotFoundError(f"IFC file not found: {ifc_path}")

    # determine project root (assume util/ is at repo root)
    repo_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
    model_name = os.path.splitext(os.path.basename(ifc_path))[0]
    dest_model_dir = os.path.join(repo_root, "api", "static", "models", model_name)
    elements_dir = os.path.join(dest_model_dir, "elements")

    os.makedirs(elements_dir, exist_ok=True)

    # copy IFC into the model folder
    copied_ifc_path = os.path.join(dest_model_dir, os.path.basename(ifc_path))
    try:
        shutil.copy2(ifc_path, copied_ifc_path)
    except Exception as e:
        logger.warning("Failed to copy IFC file to destination: %s", e)

    # open model
    model = ifcopenshell.open(ifc_path)

    if GeometryHandler is None:
        raise RuntimeError(
            "GeometryHandler is not available. Ensure graphql_building_api.ifc.geometry can be "
            "imported and its dependencies (ifcopenshell.geom, trimesh) are installed."
        )

    requested_formats = [
        normalize_geometry_format(format_name)
        for format_name in (formats or ["OBJ", "GLB"])
    ]
    written = 0
    skipped = 0
    written_by_format = {format_name: 0 for format_name in requested_formats}

    # iterate over potential products and attempt geometry extraction
    products = model.by_type("IfcProduct")
    for product in products:
        # skip spatial structure elements that usually don't have mesh geometry
        if product is None:
            continue

        # we rely on GeometryHandler to raise if no geometry is present
        try:
            gh = GeometryHandler(product)
        except Exception:
            skipped += 1
            continue

        guid = getattr(product, "GlobalId", None) or getattr(product, "globalid", None)
        if not guid:
            # fallback to numeric id
            guid = str(product.id())

        try:
            element_dir = os.path.join(elements_dir, guid)
            os.makedirs(element_dir, exist_ok=True)

            for format_name in requested_formats:
                format_spec = GEOMETRY_FORMATS[format_name]
                output_path = os.path.join(
                    element_dir, f"geometry{format_spec.extension}"
                )

                if format_spec.provider_hint in {"gltf", "wkt"}:
                    request = GeometryRequest(
                        entity=product,
                        guid=guid,
                        format_name=format_name,
                        elements_dir=Path(elements_dir),
                        geometry_base_url="",
                        source="MODEL",
                        config=GeometryConfig(),
                    )
                    artifact = geometry_service.generate(request)
                    if artifact is None:
                        logger.warning("Failed to generate format: %s", format_name)
                        continue
                    with open(output_path, "wb") as f:
                        f.write(artifact.data)
                    written_by_format[format_name] += 1
                    continue

                if not format_spec.trimesh_file_type:
                    logger.warning(
                        "Skipping non-Trimesh format for generation: %s", format_name
                    )
                    continue

                output = gh.export(
                    format_spec.trimesh_file_type,
                    **(format_spec.trimesh_export_kwargs or {}),
                )
                if isinstance(output, str):
                    output = output.encode("utf-8")

                if format_name == "OBJ":
                    mtl_name = "geometry.mtl"
                    prefix = f"mtllib {mtl_name}\n".encode("utf-8")
                    output = prefix + output

                    mtl_content = (
                        f"# minimal material for {guid}\n"
                        f"newmtl material_{guid}\n"
                        "Kd 0.8 0.8 0.8\n"
                    )
                    mtl_path = os.path.join(element_dir, mtl_name)
                    with open(mtl_path, "w", encoding="utf-8") as f:
                        f.write(mtl_content)

                with open(output_path, "wb") as f:
                    f.write(output)
                written_by_format[format_name] += 1

            written += 1
        except Exception as e:
            logger.exception("Failed to write geometry for %s: %s", guid, e)
            skipped += 1

    summary = {
        "model_name": model_name,
        "model_folder": dest_model_dir,
        "copied_ifc": copied_ifc_path if os.path.exists(copied_ifc_path) else None,
        "elements_written": written,
        "elements_skipped": skipped,
        "formats": requested_formats,
        "written_by_format": written_by_format,
    }

    if pretty:
        try:
            return json.dumps(summary, indent=2)
        except Exception:
            # fallback to str
            return str(summary)

    return summary


def main():
    import argparse

    p = argparse.ArgumentParser()
    p.add_argument("ifc", help="Path to IFC file")
    p.add_argument(
        "--formats",
        nargs="+",
        default=["OBJ", "GLB"],
        help="Geometry formats to generate. Defaults to OBJ GLB.",
    )
    args = p.parse_args()
    print(generate_geometry(args.ifc, formats=args.formats, pretty=True))


if __name__ == "__main__":
    main()
