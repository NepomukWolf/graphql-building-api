import ifcopenshell
import ifcopenshell.geom
import numpy as np
import trimesh

class GeometryHandler:
    def __init__(self, element: ifcopenshell.entity_instance):
        settings = ifcopenshell.geom.settings()
        settings.set(settings.USE_WORLD_COORDS, True)
        self.element = element
        self.shape = ifcopenshell.geom.create_shape(settings, element)
        self.geometry = self.shape.geometry
        self.mesh = None
        self._generateMesh()

    def _generateMesh(self, fix_mesh=True):
        verts = np.array(self.geometry.verts).reshape(-1, 3)
        faces = np.array(self.geometry.faces).reshape(-1, 3)
        mesh = trimesh.Trimesh(vertices=verts, faces=faces)
        if fix_mesh:
            mesh.update_faces(mesh.unique_faces())
            mesh.fill_holes()      # Falls Löcher vorhanden sind
            mesh.fix_normals()

        self.mesh = mesh 

    def export(self, file_type: str, **kwargs):
        return self.mesh.export(file_type=file_type, **kwargs)

    def string(self, format) -> str:
        return self.export(format)

    def bbox(self):
        bounds = self.mesh.bounds
        return {
            "min": {"x": bounds[0][0], "y": bounds[0][1], "z": bounds[0][2]},
            "max": {"x": bounds[1][0], "y": bounds[1][1], "z": bounds[1][2]}
        }
        

    def file(self, path):
        self.mesh.export(path)
