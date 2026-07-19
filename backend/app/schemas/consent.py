from uuid import UUID

from pydantic import BaseModel, Field


class ConsentRequestIn(BaseModel):
    guardianName: str = Field(min_length=1, max_length=200)
    guardianEmail: str = Field(min_length=3, max_length=255)
    guardianPhone: str | None = Field(default=None, max_length=32)


class ConsentRequestOut(BaseModel):
    competitorId: UUID
    status: str
    expiresAt: str
    # Token returned for automated tests / link construction; also emailed via outbox
    token: str


class ConsentGrantIn(BaseModel):
    scopes: list[str] = Field(default_factory=list)
    grantedBy: str | None = Field(default=None, max_length=255)


class ConsentGrantOut(BaseModel):
    competitorId: UUID
    status: str
    scopesGranted: list[str]
    publicProfileVisible: bool


class ConsentWithdrawOut(BaseModel):
    competitorId: UUID
    status: str
    flags: list[str]
    publicProfileVisible: bool


class PublicCompetitorOut(BaseModel):
    competitorRef: str
    displayName: str | None = None
    public: bool
