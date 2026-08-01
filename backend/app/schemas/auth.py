from pydantic import BaseModel, Field


class LoginRequest(BaseModel):
    email: str = Field(min_length=3)
    password: str = Field(min_length=1)


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    must_change_password: bool = Field(default=False, serialization_alias="mustChangePassword")

    model_config = {"populate_by_name": True}


class RefreshRequest(BaseModel):
    refresh_token: str


class MeResponse(BaseModel):
    id: str
    email: str | None
    full_name: str = Field(serialization_alias="fullName")
    role: str
    must_change_password: bool = Field(default=False, serialization_alias="mustChangePassword")
    institution_id: str | None = Field(
        default=None, serialization_alias="institutionId"
    )

    model_config = {"populate_by_name": True}


class RegisterInstitutionRequest(BaseModel):
    email: str = Field(min_length=3, max_length=255)
    full_name: str = Field(min_length=1, max_length=200, alias="fullName")
    password: str = Field(min_length=1)
    password_confirm: str = Field(alias="passwordConfirm")
    phone_number: str = Field(min_length=1, max_length=50, alias="phoneNumber")
    school_code: str = Field(min_length=1, max_length=64, alias="schoolCode")
    captcha_token: str | None = Field(default=None, alias="captchaToken")

    model_config = {"populate_by_name": True}


class AcceptInviteRequest(BaseModel):
    token: str = Field(min_length=10)
    password: str = Field(min_length=1)
    password_confirm: str = Field(alias="passwordConfirm")

    model_config = {"populate_by_name": True}


class RegisterRequest(BaseModel):
    email: str = Field(min_length=3, max_length=255)
    full_name: str = Field(min_length=1, max_length=200, alias="fullName")
    password: str = Field(min_length=1)
    password_confirm: str = Field(alias="passwordConfirm")
    phone_number: str = Field(min_length=1, max_length=50, alias="phoneNumber")
    captcha_token: str | None = Field(default=None, alias="captchaToken")
    role: str | None = None  # ignored / rejected if not COMPETITOR

    model_config = {"populate_by_name": True}


class RegisterResponse(TokenResponse):
    user: dict

    model_config = {"populate_by_name": True}


class ChangePasswordRequest(BaseModel):
    current_password: str = Field(alias="currentPassword")
    new_password: str = Field(alias="newPassword")
    new_password_confirm: str = Field(alias="newPasswordConfirm")

    model_config = {"populate_by_name": True}
