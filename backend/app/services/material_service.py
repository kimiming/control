from typing import Any

from fastapi import UploadFile
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.material import Material
from app.services.image_storage import save_compressed_image


class MaterialService:
    def list_materials(self, db: Session, material_type: str | None = None, owner_id: int | None = None) -> list[Material]:
        stmt = select(Material).order_by(Material.priority.desc(), Material.created_at.asc())
        if owner_id is not None:
            stmt = stmt.where(Material.owner_id == owner_id)
        if material_type:
            stmt = stmt.where(Material.material_type == material_type)
        return list(db.scalars(stmt).all())

    def get_material(self, db: Session, material_id: int, owner_id: int | None = None) -> Material:
        material = db.get(Material, material_id)
        if not material or (owner_id is not None and material.owner_id != owner_id):
            raise ValueError("Material not found")
        return material

    async def create_material(self, db: Session, data: dict[str, Any], file: UploadFile | None = None, owner_id: int | None = None) -> Material:
        data["owner_id"] = owner_id
        material = Material(**data)
        if file:
            material.file_path = await self._save_file(file)
        db.add(material)
        db.commit()
        db.refresh(material)
        return material

    async def update_material(self, db: Session, material_id: int, data: dict[str, Any], file: UploadFile | None = None, owner_id: int | None = None) -> Material:
        material = self.get_material(db, material_id, owner_id)
        for key, value in data.items():
            if hasattr(material, key):
                setattr(material, key, value)
        if file:
            material.file_path = await self._save_file(file)
        db.commit()
        db.refresh(material)
        return material

    def delete_material(self, db: Session, material_id: int, owner_id: int | None = None) -> None:
        material = self.get_material(db, material_id, owner_id)
        db.delete(material)
        db.commit()

    def batch_delete(self, db: Session, ids: list[int], owner_id: int | None = None) -> int:
        stmt = select(Material).where(Material.id.in_(ids))
        if owner_id is not None:
            stmt = stmt.where(Material.owner_id == owner_id)
        materials = list(db.scalars(stmt).all())
        for material in materials:
            db.delete(material)
        db.commit()
        return len(materials)

    def serialize_material(self, material: Material) -> dict[str, Any]:
        return {
            "id": material.id,
            "name": material.name,
            "material_type": material.material_type,
            "content": material.content,
            "file_path": material.file_path,
            "priority": material.priority,
            "remark": material.remark,
            "created_at": material.created_at.isoformat() if material.created_at else None,
            "updated_at": material.updated_at.isoformat() if material.updated_at else None,
        }

    async def _save_file(self, file: UploadFile) -> str:
        return await save_compressed_image(file, "static/materials")


material_service = MaterialService()
