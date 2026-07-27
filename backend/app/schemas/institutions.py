from pydantic import BaseModel, Field


class InstitutionOut(BaseModel):
    institution_id: str = Field(alias="institutionId")
    code: str
    name: str
    region_id: str | None = Field(default=None, alias="regionId")
    active: bool

    model_config = {"populate_by_name": True}


class InstitutionCreate(BaseModel):
    code: str = Field(min_length=1, max_length=64)
    name: str = Field(min_length=1, max_length=200)
    region_id: str = Field(alias="regionId")
    active: bool = True

    model_config = {"populate_by_name": True}


class InstitutionPatch(BaseModel):
    code: str | None = Field(default=None, min_length=1, max_length=64)
    name: str | None = Field(default=None, min_length=1, max_length=200)
    region_id: str | None = Field(default=None, alias="regionId")
    active: bool | None = None

    model_config = {"populate_by_name": True}


class InstitutionImportResult(BaseModel):
    created: int
    updated: int
    errors: list[dict]


class InstitutionLookupOut(BaseModel):
    code: str
    name: str
    institution_id: str = Field(alias="institutionId")

    model_config = {"populate_by_name": True}
