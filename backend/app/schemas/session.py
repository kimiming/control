from pydantic import BaseModel, Field


class SessionCreate(BaseModel):
    username: str = Field(min_length=1, max_length=100)
    phone: str = Field(min_length=5, max_length=32)
    avatar: str | None = Field(default=None, max_length=500)
    session_name: str | None = Field(default=None, max_length=150)
    group_id: int | None = None


class SessionUpdate(BaseModel):
    username: str | None = Field(default=None, min_length=1, max_length=100)
    phone: str | None = Field(default=None, min_length=5, max_length=32)
    avatar: str | None = Field(default=None, max_length=500)
    group_id: int | None = None
    action: str | None = Field(default=None, pattern="^(connect|disconnect)$")


class GroupCreate(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    description: str | None = Field(default=None, max_length=255)


class MoveSessions(BaseModel):
    session_ids: list[int] = Field(min_length=1)
    group_id: int | None = None
