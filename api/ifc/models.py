from __future__ import annotations

from pathlib import Path

import ifcopenshell


class IfcModelStore:
    def __init__(self, models_dir: Path, default_model: str):
        self.models_dir = models_dir
        self.default_model = default_model
        self._models = {
            default_model: self._load_model(default_model),
        }

    def get(self, model_name: str | None = None):
        selected_name = model_name or self.default_model
        if selected_name not in self._models:
            self._models[selected_name] = self._load_model(selected_name)
        return self._models[selected_name]

    def model_folder_name(self, model_name: str | None = None) -> str:
        return model_name or self.default_model

    def available_models(self) -> list[str]:
        return sorted(
            path.name
            for path in self.models_dir.iterdir()
            if path.is_dir() and (path / f"{path.name}.ifc").is_file()
        )

    def _load_model(self, model_name: str):
        model_path = self._model_path(model_name)
        return ifcopenshell.open(str(model_path))

    def _model_path(self, model_name: str) -> Path:
        if Path(model_name).name != model_name:
            raise ValueError(f"Invalid model name: {model_name}")

        model_path = self.models_dir / model_name / f"{model_name}.ifc"
        if not model_path.is_file():
            raise FileNotFoundError(f"IFC model not found: {model_path}")
        return model_path
