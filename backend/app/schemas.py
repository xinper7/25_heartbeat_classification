from typing import Any, Literal

from pydantic import BaseModel, Field


class ApiResponse(BaseModel):
    code: int = 0
    result: Any = None
    msg: str = "成功"


class LoginIn(BaseModel):
    username: str = Field(min_length=1, max_length=64)
    password: str = Field(min_length=1, max_length=200)


class UserIn(BaseModel):
    username: str = Field(pattern=r"^[a-zA-Z0-9_.-]{3,64}$")
    name: str = Field(min_length=1, max_length=80)
    password: str = Field(min_length=12, max_length=200)
    role: Literal["analyst", "reviewer", "admin"] = "analyst"


class UserUpdate(BaseModel):
    active: bool | None = None
    role: Literal["analyst", "reviewer", "admin"] | None = None
    name: str | None = Field(default=None, min_length=1, max_length=80)


class PasswordIn(BaseModel):
    current_password: str
    new_password: str = Field(min_length=12, max_length=200)


class PatientIn(BaseModel):
    code: str = Field(min_length=1, max_length=64)
    name: str = Field(min_length=1, max_length=80)
    sex: Literal["male", "female", "unknown"] = "unknown"
    age: int | None = Field(default=None, ge=0, le=130)
    note: str = Field(default="", max_length=2000)


class StudyIn(BaseModel):
    patient_id: int
    title: str = Field(min_length=1, max_length=150)
    kind: Literal["signal", "image"]
    note: str = Field(default="", max_length=2000)


class ReviewAction(BaseModel):
    previous_event_id: int | None = None
    comment: str = Field(min_length=5, max_length=5000)


class ReviewIn(ReviewAction):
    conclusion: Literal["confirmed", "needs_attention", "returned"]


class JobIn(BaseModel):
    name: str = Field(min_length=1, max_length=150)
    study_ids: list[int] = Field(min_length=1, max_length=100)
