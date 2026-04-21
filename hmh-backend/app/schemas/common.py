"""
Shared Pydantic v2 schemas — API response wrappers and pagination.
All API responses use ApiSuccess or ApiError for consistency.
"""

from typing import Any, Dict, Generic, List, Optional, TypeVar

from pydantic import BaseModel, ConfigDict

T = TypeVar("T")


class ApiSuccess(BaseModel, Generic[T]):
    """Standard success response envelope."""
    success: bool = True
    data: T
    message: Optional[str] = None


class ApiError(BaseModel):
    """Standard error response envelope."""
    success: bool = False
    message: str
    code: Optional[str] = None
    errors: Optional[Dict[str, List[str]]] = None


class PaginatedResult(BaseModel, Generic[T]):
    """Paginated list response."""
    items: List[T]
    total: int
    page: int
    limit: int
    total_pages: int

    model_config = ConfigDict(from_attributes=True)


class PaginationParams(BaseModel):
    """Query params for list endpoints."""
    page: int = 1
    limit: int = 20

    @property
    def offset(self) -> int:
        return (self.page - 1) * self.limit
