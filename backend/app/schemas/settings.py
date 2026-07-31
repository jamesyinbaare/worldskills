"""System settings schemas."""

from pydantic import BaseModel, Field


class SystemSettingsOut(BaseModel):
    institutionRegistrationEnabled: bool
    allowMultipleActiveCompetitions: bool


class SystemSettingsUpdate(BaseModel):
    institutionRegistrationEnabled: bool | None = Field(default=None)
    allowMultipleActiveCompetitions: bool | None = Field(default=None)
