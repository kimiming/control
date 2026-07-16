import json
from pathlib import Path
from typing import Any

from fastapi import UploadFile
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.models.material import Material, MaterialGroup
from app.models.task import MarketingTask
from app.services.image_storage import save_compressed_image


class MaterialService:
    def list_materials(
        self,
        db: Session,
        material_type: str | None = None,
        owner_id: int | None = None,
        group_id: int | None = None,
        keyword: str | None = None,
    ) -> list[Material]:
        stmt = select(Material).order_by(Material.priority.desc(), Material.created_at.asc())
        if owner_id is not None:
            stmt = stmt.where(Material.owner_id == owner_id)
        if material_type:
            stmt = stmt.where(Material.material_type == material_type)
        if group_id is not None:
            stmt = stmt.where(Material.group_id.is_(None) if group_id == 0 else Material.group_id == group_id)
        normalized_keyword = (keyword or "").strip()
        if normalized_keyword:
            stmt = stmt.where(or_(
                Material.name.contains(normalized_keyword, autoescape=True),
                Material.content.contains(normalized_keyword, autoescape=True),
                Material.remark.contains(normalized_keyword, autoescape=True),
            ))
        return list(db.scalars(stmt).all())

    def list_groups(self, db: Session, owner_id: int | None = None) -> list[MaterialGroup]:
        stmt = select(MaterialGroup).order_by(MaterialGroup.created_at.asc(), MaterialGroup.id.asc())
        if owner_id is not None:
            stmt = stmt.where(MaterialGroup.owner_id == owner_id)
        return list(db.scalars(stmt).all())

    def get_group(self, db: Session, group_id: int, owner_id: int | None = None) -> MaterialGroup:
        group = db.get(MaterialGroup, group_id)
        if not group or (owner_id is not None and group.owner_id != owner_id):
            raise ValueError("Material group not found")
        return group

    def create_group(self, db: Session, name: str, remark: str | None, color: str = "blue", owner_id: int | None = None) -> MaterialGroup:
        self._ensure_group_name_available(db, name, owner_id)
        group = MaterialGroup(owner_id=owner_id, name=name.strip(), remark=remark, color=self._validate_group_color(color))
        db.add(group)
        db.commit()
        db.refresh(group)
        return group

    def update_group(self, db: Session, group_id: int, name: str, remark: str | None, color: str = "blue", owner_id: int | None = None) -> MaterialGroup:
        group = self.get_group(db, group_id, owner_id)
        self._ensure_group_name_available(db, name, owner_id, group_id)
        group.name = name.strip()
        group.remark = remark
        group.color = self._validate_group_color(color)
        db.commit()
        db.refresh(group)
        return group

    def delete_group(self, db: Session, group_id: int, owner_id: int | None = None) -> None:
        group = self.get_group(db, group_id, owner_id)
        for material in db.scalars(select(Material).where(Material.group_id == group.id)).all():
            material.group_id = None
        for task in db.scalars(select(MarketingTask).where(MarketingTask.material_group_id == group.id)).all():
            task.material_group_id = None
        for task in db.scalars(select(MarketingTask).where(MarketingTask.material_group_ids.is_not(None))).all():
            try:
                group_ids = [int(item) for item in json.loads(task.material_group_ids or "[]")]
            except (TypeError, ValueError, json.JSONDecodeError):
                group_ids = []
            if group.id in group_ids:
                task.material_group_ids = json.dumps([item for item in group_ids if item != group.id])
        db.delete(group)
        db.commit()

    def move_materials(self, db: Session, ids: list[int], group_id: int | None, owner_id: int | None = None) -> int:
        if group_id is not None:
            self.get_group(db, group_id, owner_id)
        stmt = select(Material).where(Material.id.in_(ids))
        if owner_id is not None:
            stmt = stmt.where(Material.owner_id == owner_id)
        materials = list(db.scalars(stmt).all())
        for material in materials:
            material.group_id = group_id
        db.commit()
        return len(materials)

    def list_group_materials(self, db: Session, group_id: int, owner_id: int | None = None) -> list[Material]:
        self.get_group(db, group_id, owner_id)
        stmt = select(Material).where(Material.group_id == group_id)
        if owner_id is not None:
            stmt = stmt.where(Material.owner_id == owner_id)
        return list(db.scalars(stmt).all())

    def get_material(self, db: Session, material_id: int, owner_id: int | None = None) -> Material:
        material = db.get(Material, material_id)
        if not material or (owner_id is not None and material.owner_id != owner_id):
            raise ValueError("Material not found")
        return material

    async def create_material(self, db: Session, data: dict[str, Any], file: UploadFile | None = None, owner_id: int | None = None) -> Material:
        self._validate_group(db, data.get("group_id"), owner_id)
        data["owner_id"] = owner_id
        material = Material(**data)
        if file:
            material.file_path = await self._save_file(file)
        db.add(material)
        db.commit()
        db.refresh(material)
        return material

    async def import_text_materials(
        self,
        db: Session,
        file: UploadFile,
        group_id: int | None = None,
        owner_id: int | None = None,
        delimiter: str | None = None,
    ) -> dict[str, int]:
        if not file.filename or Path(file.filename).suffix.lower() != ".txt":
            raise ValueError("Only TXT files are supported")
        self._validate_group(db, group_id, owner_id)
        data = await file.read()
        try:
            text = data.decode("utf-8-sig")
        except UnicodeDecodeError:
            text = data.decode("gb18030", errors="ignore")
        base_name = Path(file.filename).stem.strip() or "导入文字"
        base_name = base_name[:120]
        materials: list[Material] = []
        entries, skipped, custom_split = self._split_text_entries(text, delimiter)
        for entry_number, content in entries:
            materials.append(
                Material(
                    owner_id=owner_id,
                    group_id=group_id,
                    name=(
                        f"{base_name}-第{entry_number}份"
                        if custom_split
                        else f"{base_name}-第{entry_number}行"
                    )[:150],
                    material_type="text",
                    content=content,
                    priority=0,
                    remark=f"从 {file.filename} 导入",
                )
            )
        if not materials:
            raise ValueError("TXT file has no non-empty lines")
        db.add_all(materials)
        db.commit()
        return {"created": len(materials), "skipped": skipped}

    def _split_text_entries(
        self,
        text: str,
        delimiter: str | None = None,
    ) -> tuple[list[tuple[int, str]], int, bool]:
        normalized_delimiter = (delimiter or "").strip()
        custom_split = bool(normalized_delimiter)
        raw_entries = text.split(normalized_delimiter) if custom_split else text.splitlines()
        entries: list[tuple[int, str]] = []
        skipped = 0
        for entry_number, raw_entry in enumerate(raw_entries, start=1):
            content = raw_entry.strip()
            if not content:
                skipped += 1
                continue
            entries.append((entry_number, content))
        return entries, skipped, custom_split

    async def import_image_materials(
        self,
        db: Session,
        files: list[UploadFile],
        group_id: int | None = None,
        owner_id: int | None = None,
    ) -> dict[str, Any]:
        self._validate_group(db, group_id, owner_id)
        if not files:
            raise ValueError("请选择图片文件")
        if len(files) > 200:
            raise ValueError("单次最多导入200张图片")
        if sum(file.size or 0 for file in files) > 180 * 1024 * 1024:
            raise ValueError("单次图片文件总大小不能超过180MB")

        allowed_suffixes = {".jpg", ".jpeg", ".png", ".webp", ".gif", ".bmp"}
        materials: list[Material] = []
        skipped_files: list[str] = []
        for index, file in enumerate(files, start=1):
            original_name = Path(file.filename or f"图片{index}").name
            suffix = Path(original_name).suffix.lower()
            if suffix not in allowed_suffixes or (file.size is not None and file.size > 20 * 1024 * 1024):
                skipped_files.append(original_name)
                continue
            try:
                file_path = await self._save_file(file)
            except ValueError:
                skipped_files.append(original_name)
                continue
            base_name = Path(original_name).stem.strip() or f"导入图片{index}"
            materials.append(Material(
                owner_id=owner_id,
                group_id=group_id,
                name=base_name[:150],
                material_type="image",
                file_path=file_path,
                priority=0,
                remark=f"从 {original_name} 批量导入",
            ))
        if not materials:
            raise ValueError("没有可导入的有效图片，每张图片不能超过20MB")
        db.add_all(materials)
        db.commit()
        return {
            "created": len(materials),
            "skipped": len(skipped_files),
            "skipped_files": skipped_files[:20],
        }

    async def update_material(self, db: Session, material_id: int, data: dict[str, Any], file: UploadFile | None = None, owner_id: int | None = None) -> Material:
        material = self.get_material(db, material_id, owner_id)
        self._validate_group(db, data.get("group_id"), owner_id)
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
            "group_id": material.group_id,
            "material_type": material.material_type,
            "content": material.content,
            "file_path": material.file_path,
            "priority": material.priority,
            "remark": material.remark,
            "created_at": material.created_at.isoformat() if material.created_at else None,
            "updated_at": material.updated_at.isoformat() if material.updated_at else None,
        }

    def serialize_group(
        self,
        group: MaterialGroup,
        material_count: int = 0,
        type_counts: dict[str, int] | None = None,
    ) -> dict[str, Any]:
        type_counts = type_counts or {}
        return {
            "id": group.id,
            "name": group.name,
            "color": group.color or "blue",
            "remark": group.remark,
            "material_count": material_count,
            "text_count": type_counts.get("text", 0),
            "image_count": type_counts.get("image", 0),
            "contact_count": type_counts.get("contact", 0),
            "created_at": group.created_at.isoformat() if group.created_at else None,
            "updated_at": group.updated_at.isoformat() if group.updated_at else None,
        }

    def _validate_group(self, db: Session, group_id: int | None, owner_id: int | None) -> None:
        if group_id is not None:
            self.get_group(db, group_id, owner_id)

    def _ensure_group_name_available(self, db: Session, name: str, owner_id: int | None, exclude_id: int | None = None) -> None:
        clean_name = name.strip()
        if not clean_name:
            raise ValueError("Material group name is required")
        stmt = select(MaterialGroup).where(MaterialGroup.name == clean_name)
        if owner_id is not None:
            stmt = stmt.where(MaterialGroup.owner_id == owner_id)
        if exclude_id is not None:
            stmt = stmt.where(MaterialGroup.id != exclude_id)
        if db.scalar(stmt):
            raise ValueError("Material group name already exists")

    def _validate_group_color(self, color: str) -> str:
        allowed = {"red", "orange", "yellow", "green", "blue", "geekblue", "purple"}
        if color not in allowed:
            raise ValueError("Invalid material group color")
        return color

    async def _save_file(self, file: UploadFile) -> str:
        return await save_compressed_image(file, "static/materials")


material_service = MaterialService()
