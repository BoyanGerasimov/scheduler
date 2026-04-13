import uuid
from datetime import date, datetime, time

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator


class TimeInterval(BaseModel):
    start: time
    end: time

    @field_validator('end')
    @classmethod
    def validate_end(cls, value: time, info):
        start = info.data.get('start')
        if start and value <= start:
            raise ValueError('end must be after start')
        return value


class DailySchedule(BaseModel):
    weekday: int = Field(ge=0, le=6)
    intervals: list[TimeInterval]


class RegisterDoctorRequest(BaseModel):
    name: str
    email: EmailStr
    password: str = Field(min_length=8)
    address: str
    weekly_schedule: list[DailySchedule]


class RegisterPatientRequest(BaseModel):
    name: str
    email: EmailStr
    password: str = Field(min_length=8)
    phone: str
    doctor_id: uuid.UUID


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = 'bearer'


class MessageResponse(BaseModel):
    message: str


class UpdateWorkingHoursRequest(BaseModel):
    weekly_schedule: list[DailySchedule]


class TemporaryChangeRequest(BaseModel):
    starts_at: datetime
    ends_at: datetime
    weekly_schedule: list[DailySchedule]

    @field_validator('ends_at')
    @classmethod
    def validate_ends_at(cls, value: datetime, info):
        starts_at = info.data.get('starts_at')
        if starts_at and value <= starts_at:
            raise ValueError('ends_at must be after starts_at')
        return value


class PermanentChangeRequest(BaseModel):
    effective_from: date
    weekly_schedule: list[DailySchedule]


class VisitCreateRequest(BaseModel):
    starts_at: datetime
    ends_at: datetime

    @field_validator('ends_at')
    @classmethod
    def validate_ends_at(cls, value: datetime, info):
        starts_at = info.data.get('starts_at')
        if starts_at and value <= starts_at:
            raise ValueError('ends_at must be after starts_at')
        return value


class VisitResponse(BaseModel):
    id: uuid.UUID
    doctor_id: uuid.UUID
    patient_id: uuid.UUID
    starts_at: datetime
    ends_at: datetime
    status: str
    cancelled_by: str | None

    model_config = ConfigDict(from_attributes=True)
