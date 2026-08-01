from enum import Enum

from pydantic import BaseModel, Field


class CredentialMode(str, Enum):
    TEMP_PASSWORD = "TEMP_PASSWORD"
    INVITE = "INVITE"


class CreateUserRequest(BaseModel):
    email: str = Field(min_length=3, max_length=255)
    full_name: str = Field(min_length=1, max_length=255, alias="fullName")
    role: str
    phone_number: str = Field(min_length=1, max_length=50, alias="phoneNumber")
    institution_id: str | None = Field(default=None, alias="institutionId")
    credential_mode: CredentialMode = Field(alias="credentialMode")
    temporary_password: str | None = Field(default=None, alias="temporaryPassword")

    model_config = {"populate_by_name": True}


class UserOut(BaseModel):
    user_id: str = Field(alias="userId")
    email: str
    full_name: str = Field(alias="fullName")
    role: str
    institution_id: str | None = Field(default=None, alias="institutionId")
    is_active: bool = Field(alias="isActive")
    must_change_password: bool = Field(alias="mustChangePassword")
    phone_number: str | None = Field(default=None, alias="phoneNumber")

    model_config = {"populate_by_name": True}


class CreateUserResponse(UserOut):
    temporary_password: str | None = Field(default=None, alias="temporaryPassword")
    invite_sent: bool = Field(default=False, alias="inviteSent")


class PatchUserRequest(BaseModel):
    full_name: str | None = Field(default=None, alias="fullName")
    institution_id: str | None = Field(default=None, alias="institutionId")
    is_active: bool | None = Field(default=None, alias="isActive")

    model_config = {"populate_by_name": True}


class ResetPasswordRequest(BaseModel):
    temporary_password: str | None = Field(default=None, alias="temporaryPassword")
    send_via_sms: bool = Field(default=False, alias="sendViaSms")
    phone_number: str | None = Field(default=None, alias="phoneNumber")

    model_config = {"populate_by_name": True}


class ResetPasswordResponse(UserOut):
    temporary_password: str = Field(alias="temporaryPassword")
    sms_sent: bool = Field(default=False, alias="smsSent")
    sms_error: str | None = Field(default=None, alias="smsError")


class InstitutionListItem(BaseModel):
    institution_id: str = Field(alias="institutionId")
    code: str | None = None
    name: str
    region_id: str | None = Field(default=None, alias="regionId")
    active: bool

    model_config = {"populate_by_name": True}
