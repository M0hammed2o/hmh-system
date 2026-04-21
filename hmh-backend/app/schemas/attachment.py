"""Pydantic v2 schemas for Attachment."""

import uuid
from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, computed_field

from app.models.enums import AttachmentEntity, AttachmentType


class AttachmentRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    entity_type: AttachmentEntity
    entity_id: uuid.UUID
    file_name: str
    mime_type: str
    file_size_bytes: Optional[int] = None
    attachment_type: AttachmentType
    uploaded_by: Optional[uuid.UUID] = None
    uploaded_at: datetime
    is_active: bool

    @computed_field  # type: ignore[misc]
    @property
    def download_url(self) -> str:
        return f"/api/v1/attachments/{self.id}/download"

    @computed_field  # type: ignore[misc]
    @property
    def is_image(self) -> bool:
        return self.mime_type.startswith("image/")

    @computed_field  # type: ignore[misc]
    @property
    def file_size_display(self) -> str:
        if self.file_size_bytes is None:
            return "—"
        kb = self.file_size_bytes / 1024
        if kb < 1024:
            return f"{kb:.1f} KB"
        return f"{kb / 1024:.1f} MB"


class AttachmentCreate(BaseModel):
    entity_type: AttachmentEntity
    entity_id: uuid.UUID
    file_name: str
    stored_path: str
    mime_type: str
    file_size_bytes: Optional[int] = None
    attachment_type: AttachmentType
