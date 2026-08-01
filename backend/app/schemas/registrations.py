from datetime import date, datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field, field_validator


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
    # Used by clients for display; guardian consent is not enforced from age.
    minorAgeUnder: int | None = None
    minorReferenceDate: date | None = None


class PhotoIn(BaseModel):
    contentBase64: str
    contentType: str


class CoachBioIn(BaseModel):
    surname: str = Field(min_length=1, max_length=120)
    firstName: str = Field(min_length=1, max_length=120)
    otherName: str | None = Field(default=None, max_length=120)
    contactNumber: str = Field(min_length=1, max_length=32)
    email: str = Field(min_length=3, max_length=255)
    # Optional; when omitted, contactNumber is used (single phone / WhatsApp field in UI).
    whatsapp: str | None = Field(default=None, max_length=32)
    dateOfBirth: date

    @field_validator("surname", "firstName", "contactNumber", "email", mode="before")
    @classmethod
    def strip_required(cls, value: Any) -> Any:
        if isinstance(value, str):
            return value.strip()
        return value

    @field_validator("otherName", "whatsapp", mode="before")
    @classmethod
    def strip_optional(cls, value: Any) -> Any:
        if value is None:
            return None
        if isinstance(value, str):
            stripped = value.strip()
            return stripped or None
        return value

    def resolved_whatsapp(self) -> str:
        return (self.whatsapp or self.contactNumber).strip()

    @field_validator("email")
    @classmethod
    def email_has_at(cls, value: str) -> str:
        if "@" not in value:
            raise ValueError("EMAIL_INVALID")
        return value.lower()


class RegistrationCreate(BaseModel):
    givenNames: str | None = None
    familyName: str | None = None
    gender: str | None = None
    dateOfBirth: date | None = None
    email: str | None = None
    mobile: str | None = None
    whatsapp: str | None = None
    nationalId: str | None = None
    idDocumentKind: str | None = None
    otherIdType: str | None = None
    nationality: str | None = None
    hasPassport: bool | None = None
    passportNumber: str | None = None
    passportExpiresOn: date | None = None
    affiliationType: str | None = None
    organizationName: str | None = None
    organizationCity: str | None = None
    organizationPhone: str | None = None
    organizationEmail: str | None = None
    heardAbout: str | None = None
    institutionId: UUID | None = None
    regionId: UUID | None = None
    zoneId: UUID | None = None  # rejected — zone is derived from region
    skillIds: list[UUID] = Field(default_factory=list)
    coach: CoachBioIn | dict[str, Any] | None = None
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


class RegistrationDraftIn(BaseModel):
    """Partial registration payload for server-side drafts (all fields optional)."""

    givenNames: str | None = None
    familyName: str | None = None
    gender: str | None = None
    dateOfBirth: date | None = None
    email: str | None = None
    mobile: str | None = None
    whatsapp: str | None = None
    nationalId: str | None = None
    idDocumentKind: str | None = None
    otherIdType: str | None = None
    nationality: str | None = None
    hasPassport: bool | None = None
    passportNumber: str | None = None
    passportExpiresOn: date | None = None
    affiliationType: str | None = None
    organizationName: str | None = None
    organizationCity: str | None = None
    organizationPhone: str | None = None
    organizationEmail: str | None = None
    heardAbout: str | None = None
    institutionId: UUID | None = None
    regionId: UUID | None = None
    zoneId: UUID | None = None
    skillIds: list[UUID] | None = None
    coach: dict[str, Any] | None = None
    declarationAccepted: bool | None = None
    photo: PhotoIn | None = None
    captchaToken: str | None = None
    guardianName: str | None = None
    guardianEmail: str | None = None
    guardianPhone: str | None = None
    currentStep: int | None = Field(default=None, ge=1, le=5)


class RegistrationDraftOut(BaseModel):
    competitorId: UUID
    status: str
    updatedAt: datetime
    currentStep: int | None = None
    givenNames: str | None = None
    familyName: str | None = None
    gender: str | None = None
    dateOfBirth: date | None = None
    email: str | None = None
    mobile: str | None = None
    whatsapp: str | None = None
    nationalId: str | None = None
    idDocumentKind: str | None = None
    otherIdType: str | None = None
    nationality: str | None = None
    hasPassport: bool | None = None
    passportNumber: str | None = None
    passportExpiresOn: date | None = None
    affiliationType: str | None = None
    organizationName: str | None = None
    organizationCity: str | None = None
    organizationPhone: str | None = None
    organizationEmail: str | None = None
    heardAbout: str | None = None
    institutionId: UUID | None = None
    regionId: UUID | None = None
    skillIds: list[UUID] = Field(default_factory=list)
    coach: dict[str, Any] | None = None
    declarationAccepted: bool | None = None
    hasPhoto: bool = False
    institutionName: str | None = None
    institutionCode: str | None = None
    guardianName: str | None = None
    guardianEmail: str | None = None
    guardianPhone: str | None = None


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
