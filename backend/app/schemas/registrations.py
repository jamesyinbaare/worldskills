from datetime import date, datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field


class FormFieldOut(BaseModel):
    name: str
    type: str
    required: bool = False
    maxLength: int | None = None
    pattern: str | None = None
    allowedValues: list[str] | None = None


class RegistrationFormOut(BaseModel):
    fields: list[FormFieldOut]
    maxSkills: int
    photoMaxMb: int
    photoFormats: list[str]
    readOnly: bool
    window: dict[str, str] | None = None


class PhotoIn(BaseModel):
    contentBase64: str
    contentType: str


class RegistrationCreate(BaseModel):
    givenNames: str | None = None
    familyName: str | None = None
    gender: str | None = None
    dateOfBirth: date | None = None
    email: str | None = None
    mobile: str | None = None
    whatsapp: str | None = None
    nationalId: str | None = None
    nationality: str | None = None
    hasPassport: bool | None = None
    passportNumber: str | None = None
    passportExpiresOn: date | None = None
    institutionId: UUID | None = None
    regionId: UUID | None = None
    zoneId: UUID | None = None  # rejected — zone is derived from region
    skillIds: list[UUID] = Field(default_factory=list)
    coach: dict[str, Any] | None = None
    declarationAccepted: bool | None = None
    photo: PhotoIn | None = None
    captchaToken: str | None = None
    guardianName: str | None = None
    guardianEmail: str | None = None
    guardianPhone: str | None = None


class RegistrationOut(BaseModel):
    competitorId: UUID
    competitorRef: str
    status: str
    flags: list[str] = Field(default_factory=list)
    message: str | None = None


class RegistrationWindowOut(BaseModel):
    opensAt: str
    closesAt: str


class RegistrationWindowUpdate(BaseModel):
    opensAt: datetime
    closesAt: datetime


class RegistrationFormFieldIn(BaseModel):
    name: str
    type: str = "string"
    required: bool = False
    maxLength: int | None = None
    pattern: str | None = None
    allowedValues: list[str] | None = None


class RegistrationFormAdminOut(BaseModel):
    fields: list[FormFieldOut]
    maxSkills: int
    photoMaxMb: int
    photoFormats: list[str]
    nationalIdPattern: str | None = None
    minorAgeUnder: int | None = None
    minorReferenceDate: date | None = None


class RegistrationFormAdminUpdate(BaseModel):
    fields: list[RegistrationFormFieldIn] | None = None
    maxSkills: int | None = Field(default=None, ge=1, le=10)
    photoMaxMb: int | None = Field(default=None, ge=1, le=20)
    photoFormats: list[str] | None = None
    nationalIdPattern: str | None = None
    minorAgeUnder: int | None = None
    minorReferenceDate: date | None = None
    useDefaults: bool = False
