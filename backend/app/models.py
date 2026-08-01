import enum
import uuid
from datetime import date, datetime

from sqlalchemy import (
    JSON,
    Boolean,
    Column,
    Date,
    DateTime,
    Enum,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship

from app.dependencies.database import Base


class UserRole(str, enum.Enum):
    SUPER_ADMIN = "SUPER_ADMIN"
    ADMIN = "ADMIN"
    CHIEF_EXPERT = "CHIEF_EXPERT"
    EXPERT = "EXPERT"
    MODERATOR = "MODERATOR"
    INSTITUTION = "INSTITUTION"
    COMPETITOR = "COMPETITOR"
    APPEALS_OFFICER = "APPEALS_OFFICER"


class CompetitionStatus(str, enum.Enum):
    DRAFT = "DRAFT"
    ACTIVE = "ACTIVE"
    LOCKED = "LOCKED"
    CLOSED = "CLOSED"


# Ghana administrative region names (seeded in migration; formerly a Python enum).
GHANA_REGION_NAMES: tuple[str, ...] = (
    "Ashanti",
    "Bono",
    "Bono East",
    "Ahafo",
    "Central",
    "Eastern",
    "Greater Accra",
    "Northern",
    "North East",
    "Savannah",
    "Upper East",
    "Upper West",
    "Volta",
    "Oti",
    "Western",
    "Western North",
)


class StageSelectionMode(str, enum.Enum):
    PER_ZONE = "PER_ZONE"
    NATIONAL_POOL = "NATIONAL_POOL"


class Region(Base):
    """Global region catalog (US-ZON-01)."""

    __tablename__ = "regions"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = Column(String(120), nullable=False, unique=True)
    active = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)


class User(Base):
    __tablename__ = "users"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    email = Column(String(255), unique=True, nullable=True, index=True)
    username = Column(String(80), unique=True, nullable=True, index=True)
    phone_number = Column(String(50), nullable=True, unique=True, index=True)
    hashed_password = Column(String(255), nullable=True)
    full_name = Column(String(255), nullable=False)
    role = Column(Enum(UserRole, name="userrole", create_constraint=False), nullable=False)
    is_active = Column(Boolean, default=True, nullable=False)
    institution_id = Column(UUID(as_uuid=True), ForeignKey("institutions.id", ondelete="SET NULL"), nullable=True, index=True)
    must_change_password = Column(Boolean, default=False, nullable=False)
    pending_password_hash = Column(String(255), nullable=True)
    pending_password_expires_at = Column(DateTime, nullable=True)
    invite_token_hash = Column(String(255), nullable=True)
    invite_expires_at = Column(DateTime, nullable=True)
    created_by_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)
    last_login = Column(DateTime, nullable=True)

    refresh_tokens = relationship("RefreshToken", back_populates="user", cascade="all, delete-orphan")
    created_by = relationship("User", remote_side=[id], foreign_keys=[created_by_id])
    institution = relationship("Institution", foreign_keys=[institution_id])


class Institution(Base):
    """School / institution catalog (US-INS-02). Excel upsert key = code."""

    __tablename__ = "institutions"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    code = Column(String(64), nullable=False, unique=True, default=lambda: f"T-{uuid.uuid4().hex[:10]}")
    name = Column(String(200), nullable=False)
    region_id = Column(UUID(as_uuid=True), ForeignKey("regions.id", ondelete="RESTRICT"), nullable=False, index=True)
    active = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    region = relationship("Region", foreign_keys=[region_id])


class NominationStatus(str, enum.Enum):
    PENDING_REVIEW = "PENDING_REVIEW"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"


class RefreshToken(Base):
    __tablename__ = "refresh_tokens"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    token = Column(String(255), nullable=False, index=True)
    expires_at = Column(DateTime, nullable=False, index=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    revoked_at = Column(DateTime, nullable=True)
    last_used_at = Column(DateTime, nullable=True)

    user = relationship("User", back_populates="refresh_tokens")


class Competition(Base):
    __tablename__ = "competitions"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = Column(String(120), nullable=False, index=True)
    period_start = Column(Date, nullable=False)
    period_end = Column(Date, nullable=False)
    time_zone = Column(String(64), nullable=False)
    status = Column(
        Enum(CompetitionStatus, name="competitionstatus", create_constraint=False),
        nullable=False,
        default=CompetitionStatus.DRAFT,
    )
    languages = Column(JSON, nullable=False, default=list)
    description = Column(Text, nullable=True)
    organising_body = Column(JSON, nullable=True)
    branding = Column(JSON, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    skills = relationship("Skill", back_populates="competition", cascade="all, delete-orphan")
    stages = relationship("Stage", back_populates="competition", cascade="all, delete-orphan")
    exercises = relationship("Exercise", back_populates="competition", cascade="all, delete-orphan")
    age_rules = relationship("AgeRule", back_populates="competition", cascade="all, delete-orphan")
    pathways = relationship("Pathway", back_populates="competition", cascade="all, delete-orphan")
    marking_schemes = relationship("MarkingScheme", back_populates="competition", cascade="all, delete-orphan")


class Family(Base):
    """Global skill family catalog (US-SKL-02)."""

    __tablename__ = "families"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = Column(String(120), nullable=False, unique=True)
    description = Column(Text, nullable=True)
    active = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    catalog_skills = relationship("CatalogSkill", back_populates="family")


class CatalogSkill(Base):
    """Global skill catalog entry (US-SKL-02). Associated to cycles via Skill (CycleSkill)."""

    __tablename__ = "catalog_skills"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = Column(String(120), nullable=False, unique=True)
    number = Column(String(32), nullable=True)
    family_id = Column(UUID(as_uuid=True), ForeignKey("families.id", ondelete="RESTRICT"), nullable=False, index=True)
    description = Column(Text, nullable=True)
    active = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    family = relationship("Family", back_populates="catalog_skills")
    cycle_skills = relationship("Skill", back_populates="catalog_skill")


class AgeRule(Base):
    __tablename__ = "age_rules"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    competition_id = Column(UUID(as_uuid=True), ForeignKey("competitions.id", ondelete="CASCADE"), nullable=False, index=True)
    name = Column(String(120), nullable=False)
    max_age = Column(Integer, nullable=False)
    reference_date = Column(Date, nullable=True)
    open_category_enabled = Column(Boolean, default=False, nullable=False)

    competition = relationship("Competition", back_populates="age_rules")


class Pathway(Base):
    __tablename__ = "pathways"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    competition_id = Column(UUID(as_uuid=True), ForeignKey("competitions.id", ondelete="CASCADE"), nullable=False, index=True)
    name = Column(String(120), nullable=False)

    competition = relationship("Competition", back_populates="pathways")


class MarkingScheme(Base):
    __tablename__ = "marking_schemes"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    competition_id = Column(UUID(as_uuid=True), ForeignKey("competitions.id", ondelete="CASCADE"), nullable=False, index=True)
    name = Column(String(120), nullable=False)
    # US-ASM-01 rubric config — fail closed when scoring if missing criteria
    # {
    #   "blindMode": true,
    #   "criteria":[{"id":"c1","name":"Accuracy","type":"MEASUREMENT","max":15}],
    #   "penalties":[{"code":"MINOR_NON_COMPLIANCE","deduction":2,"cap":5}]
    # }
    rubric = Column(JSON, nullable=True)
    # Optional Word/PDF marking document for experts (US-SUB-03)
    document_object_key = Column(String(512), nullable=True)
    document_file_name = Column(String(255), nullable=True)
    document_content_type = Column(String(120), nullable=True)
    document_scan_status = Column(String(32), nullable=True)  # CLEAN | INFECTED | PENDING

    competition = relationship("Competition", back_populates="marking_schemes")


class Skill(Base):
    """CycleSkill — association of a catalog skill to a competition with per-cycle age rule (US-SKL-01)."""

    __tablename__ = "skills"
    __table_args__ = (
        UniqueConstraint("competition_id", "name", name="uq_skills_competition_id_name"),
        UniqueConstraint("competition_id", "catalog_skill_id", name="uq_skills_competition_id_catalog_skill_id"),
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    competition_id = Column(UUID(as_uuid=True), ForeignKey("competitions.id", ondelete="CASCADE"), nullable=False, index=True)
    catalog_skill_id = Column(
        UUID(as_uuid=True), ForeignKey("catalog_skills.id", ondelete="RESTRICT"), nullable=True, index=True
    )
    name = Column(String(120), nullable=False)
    number = Column(String(32), nullable=True)
    # Catalog family UUID as string for branching (byFamily); denormalized from catalog
    family_id = Column(String(64), nullable=True)
    age_rule_id = Column(UUID(as_uuid=True), ForeignKey("age_rules.id", ondelete="SET NULL"), nullable=True)
    # Embedded age rule (preferred — per skill per competition)
    max_age = Column(Integer, nullable=True)
    age_reference_date = Column(Date, nullable=True)
    open_category_enabled = Column(Boolean, nullable=True)
    pathway_id = Column(UUID(as_uuid=True), ForeignKey("pathways.id", ondelete="SET NULL"), nullable=True)
    scheme_id = Column(UUID(as_uuid=True), ForeignKey("marking_schemes.id", ondelete="SET NULL"), nullable=True)
    capacity = Column(Integer, nullable=True)
    # Max competitors each school may register for this skill (applies to all institutions)
    school_quota = Column(Integer, nullable=True)
    active = Column(Boolean, default=True, nullable=False)
    # Extra eligibility checks beyond age, e.g. {"requireNationality":["GH"],"requireEnrolmentAttestation":true}
    eligibility_rules = Column(JSON, nullable=True)
    # Skill-area criteria document for competitors / institutions
    criteria_object_key = Column(String(512), nullable=True)
    criteria_file_name = Column(String(255), nullable=True)
    criteria_content_type = Column(String(120), nullable=True)
    criteria_scan_status = Column(String(32), nullable=True)  # CLEAN | INFECTED | PENDING

    competition = relationship("Competition", back_populates="skills")
    catalog_skill = relationship("CatalogSkill", back_populates="cycle_skills")


class Zone(Base):
    """Cycle-scoped zone stub (full US-ZON-01 later). Required for expert assignment."""

    __tablename__ = "zones"
    __table_args__ = (UniqueConstraint("competition_id", "name", name="uq_zones_competition_id_name"),)

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    competition_id = Column(UUID(as_uuid=True), ForeignKey("competitions.id", ondelete="CASCADE"), nullable=False, index=True)
    name = Column(String(120), nullable=False)
    active = Column(Boolean, default=True, nullable=False)


class CompetitionRegionZone(Base):
    """Maps a catalog region to a competition zone (US-ZON-01)."""

    __tablename__ = "competition_region_zones"
    __table_args__ = (
        UniqueConstraint("competition_id", "region_id", name="uq_competition_region_zones_competition_region"),
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    competition_id = Column(UUID(as_uuid=True), ForeignKey("competitions.id", ondelete="CASCADE"), nullable=False, index=True)
    region_id = Column(UUID(as_uuid=True), ForeignKey("regions.id", ondelete="RESTRICT"), nullable=False, index=True)
    zone_id = Column(UUID(as_uuid=True), ForeignKey("zones.id", ondelete="CASCADE"), nullable=False, index=True)


class ExpertAssignment(Base):
    __tablename__ = "expert_assignments"
    __table_args__ = (
        UniqueConstraint(
            "competition_id", "expert_id", "skill_id", "zone_id", name="uq_expert_assignments_competition_expert_skill_zone"
        ),
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    competition_id = Column(UUID(as_uuid=True), ForeignKey("competitions.id", ondelete="CASCADE"), nullable=False, index=True)
    expert_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    skill_id = Column(UUID(as_uuid=True), ForeignKey("skills.id", ondelete="CASCADE"), nullable=False, index=True)
    zone_id = Column(UUID(as_uuid=True), ForeignKey("zones.id", ondelete="CASCADE"), nullable=False, index=True)
    coi_flags = Column(JSON, nullable=False, default=list)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)


class Competitor(Base):
    """Competitor record — nomination shell or full registration (US-REG-01)."""

    __tablename__ = "competitors"
    __table_args__ = (
        UniqueConstraint("competition_id", "ref_no", name="uq_competitors_competition_id_ref_no"),
        UniqueConstraint("competition_id", "user_id", name="uq_competitors_competition_id_user_id"),
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    competition_id = Column(UUID(as_uuid=True), ForeignKey("competitions.id", ondelete="CASCADE"), nullable=False, index=True)
    skill_id = Column(UUID(as_uuid=True), ForeignKey("skills.id", ondelete="CASCADE"), nullable=True, index=True)
    zone_id = Column(UUID(as_uuid=True), ForeignKey("zones.id", ondelete="CASCADE"), nullable=True, index=True)
    region_id = Column(UUID(as_uuid=True), ForeignKey("regions.id", ondelete="RESTRICT"), nullable=True, index=True)
    institution_id = Column(
        UUID(as_uuid=True), ForeignKey("institutions.id", ondelete="SET NULL"), nullable=True, index=True
    )
    # Bound login account for competitor portal actions (US-SUB-02)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)
    ref_no = Column(String(64), nullable=True)
    status = Column(String(32), nullable=False, default="REGISTERED")
    # Registration profile (nullable when created via nomination shell)
    given_names = Column(String(100), nullable=True)
    family_name = Column(String(100), nullable=True)
    gender = Column(String(16), nullable=True)  # Male | Female
    date_of_birth = Column(Date, nullable=True)
    email = Column(String(255), nullable=True)
    mobile = Column(String(32), nullable=True)
    whatsapp = Column(String(32), nullable=True)
    national_id = Column(String(64), nullable=True, index=True)
    id_document_kind = Column(String(32), nullable=True)  # GHANA_CARD | OTHER
    other_id_type = Column(String(64), nullable=True)  # Passport | Driver's License | Student ID
    has_passport = Column(Boolean, default=False, nullable=False)
    passport_number = Column(String(64), nullable=True)
    passport_expires_on = Column(Date, nullable=True)
    photo_key = Column(String(512), nullable=True)
    coach = Column(JSON, nullable=True)
    flags = Column(JSON, nullable=False, default=list)
    registration_payload = Column(JSON, nullable=True)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)
    # Affiliation (school / company / workshop)
    affiliation_type = Column(String(32), nullable=True)  # school | company | workshop
    organization_name = Column(String(200), nullable=True)
    organization_city = Column(String(120), nullable=True)
    organization_phone = Column(String(32), nullable=True)
    organization_email = Column(String(255), nullable=True)
    heard_about = Column(String(32), nullable=True)
    # Guardian consent (US-REG-02) — privacy by default for minors
    guardian_name = Column(String(200), nullable=True)
    guardian_email = Column(String(255), nullable=True)
    guardian_phone = Column(String(32), nullable=True)
    consent_participation_at = Column(DateTime, nullable=True)
    consent_participation_by = Column(String(255), nullable=True)
    consent_public_at = Column(DateTime, nullable=True)
    consent_public_by = Column(String(255), nullable=True)
    public_profile_visible = Column(Boolean, default=False, nullable=False)
    # Signed guardian consent form (PDF upload)
    consent_form_key = Column(String(512), nullable=True)
    consent_form_uploaded_at = Column(DateTime, nullable=True)
    consent_form_sha256 = Column(String(64), nullable=True)
    # Admin verification of signed consent form
    consent_verification_status = Column(String(32), nullable=True)  # PENDING | VERIFIED | REJECTED
    consent_verified_at = Column(DateTime, nullable=True)
    consent_verified_by = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    consent_verification_reason = Column(Text, nullable=True)
    # Eligibility (US-ELG-01)
    nationality = Column(String(8), nullable=True)
    enrolment_attested = Column(Boolean, default=False, nullable=False)
    eligibility_status = Column(String(32), nullable=True)  # ELIGIBLE | INELIGIBLE | OPEN_CATEGORY
    eligibility_failed_rules = Column(JSON, nullable=False, default=list)
    eligibility_category = Column(String(32), nullable=True)  # COMPETITIVE | OPEN
    eligibility_override_reason = Column(Text, nullable=True)
    eligibility_override_at = Column(DateTime, nullable=True)
    eligibility_override_by = Column(UUID(as_uuid=True), nullable=True)
    # US-LCY-01 withdrawal / substitution
    withdrawn_at = Column(DateTime, nullable=True)
    withdrawn_reason = Column(Text, nullable=True)
    withdrawn_by = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    substitutes_id = Column(
        UUID(as_uuid=True), ForeignKey("competitors.id", ondelete="SET NULL"), nullable=True, index=True
    )
    substituted_by_id = Column(
        UUID(as_uuid=True), ForeignKey("competitors.id", ondelete="SET NULL"), nullable=True, index=True
    )
    # US-APP-01 disqualification
    dq_reason = Column(String(64), nullable=True)
    dq_at = Column(DateTime, nullable=True)
    dq_by = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)


class ConsentRequest(Base):
    """Tokenised guardian consent request (OTP/link)."""

    __tablename__ = "consent_requests"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    competitor_id = Column(
        UUID(as_uuid=True), ForeignKey("competitors.id", ondelete="CASCADE"), nullable=False, index=True
    )
    token = Column(String(64), nullable=False, unique=True, index=True)
    expires_at = Column(DateTime, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    consumed_at = Column(DateTime, nullable=True)


class RegistrationWindow(Base):
    """Competition registration open/close window — fail closed if missing."""

    __tablename__ = "registration_windows"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    competition_id = Column(
        UUID(as_uuid=True), ForeignKey("competitions.id", ondelete="CASCADE"), nullable=False, unique=True, index=True
    )
    opens_at = Column(DateTime, nullable=False)
    closes_at = Column(DateTime, nullable=False)


class RegistrationFormDefinition(Base):
    """Configurable registration form (FR-6.13) — never hard-code field rules in code paths."""

    __tablename__ = "registration_form_definitions"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    competition_id = Column(
        UUID(as_uuid=True), ForeignKey("competitions.id", ondelete="CASCADE"), nullable=False, unique=True, index=True
    )
    fields = Column(JSON, nullable=False, default=list)
    max_skills = Column(Integer, nullable=False, default=1)
    photo_max_mb = Column(Integer, nullable=False, default=2)
    photo_formats = Column(JSON, nullable=False, default=list)
    national_id_pattern = Column(String(128), nullable=True)
    # Age under this threshold (on reference date) requires guardian consent
    minor_age_under = Column(Integer, nullable=True)
    minor_reference_date = Column(Date, nullable=True)


class IdempotencyRecord(Base):
    __tablename__ = "idempotency_records"
    __table_args__ = (UniqueConstraint("competition_id", "key", name="uq_idempotency_records_competition_key"),)

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    competition_id = Column(UUID(as_uuid=True), ForeignKey("competitions.id", ondelete="CASCADE"), nullable=False, index=True)
    key = Column(String(128), nullable=False)
    status_code = Column(Integer, nullable=False)
    response_body = Column(JSON, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)


class InstitutionCompetitionMembership(Base):
    """Links an institution to a competition zone (precondition for nominations)."""

    __tablename__ = "institution_competition_memberships"
    __table_args__ = (
        UniqueConstraint("competition_id", "institution_id", name="uq_institution_competition_memberships_competition_institution"),
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    competition_id = Column(UUID(as_uuid=True), ForeignKey("competitions.id", ondelete="CASCADE"), nullable=False, index=True)
    institution_id = Column(
        UUID(as_uuid=True), ForeignKey("institutions.id", ondelete="CASCADE"), nullable=False, index=True
    )
    zone_id = Column(UUID(as_uuid=True), ForeignKey("zones.id", ondelete="CASCADE"), nullable=False, index=True)


class NominationLimit(Base):
    """Per-institution, per-skill nomination limit (config — fail closed if missing)."""

    __tablename__ = "nomination_limits"
    __table_args__ = (
        UniqueConstraint(
            "competition_id", "institution_id", "skill_id", name="uq_nomination_limits_competition_institution_skill"
        ),
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    competition_id = Column(UUID(as_uuid=True), ForeignKey("competitions.id", ondelete="CASCADE"), nullable=False, index=True)
    institution_id = Column(
        UUID(as_uuid=True), ForeignKey("institutions.id", ondelete="CASCADE"), nullable=False, index=True
    )
    skill_id = Column(UUID(as_uuid=True), ForeignKey("skills.id", ondelete="CASCADE"), nullable=False, index=True)
    max_nominations = Column(Integer, nullable=False)


class Nomination(Base):
    __tablename__ = "nominations"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    competition_id = Column(UUID(as_uuid=True), ForeignKey("competitions.id", ondelete="CASCADE"), nullable=False, index=True)
    institution_id = Column(
        UUID(as_uuid=True), ForeignKey("institutions.id", ondelete="CASCADE"), nullable=False, index=True
    )
    skill_id = Column(UUID(as_uuid=True), ForeignKey("skills.id", ondelete="CASCADE"), nullable=False, index=True)
    competitor_ref = Column(String(64), nullable=False)
    competitor_id = Column(
        UUID(as_uuid=True), ForeignKey("competitors.id", ondelete="SET NULL"), nullable=True, index=True
    )
    status = Column(
        Enum(NominationStatus, name="nominationstatus", create_constraint=False),
        nullable=False,
        default=NominationStatus.PENDING_REVIEW,
    )
    reason = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)


class NotificationOutbox(Base):
    """Notification delivery log / outbox (US-NOT-01)."""

    __tablename__ = "notification_outbox"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    competition_id = Column(UUID(as_uuid=True), nullable=True, index=True)
    recipient_role = Column(String(64), nullable=False)
    recipient_id = Column(UUID(as_uuid=True), nullable=True, index=True)
    template = Column(String(128), nullable=False)
    payload = Column(JSON, nullable=False, default=dict)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    # US-NOT-01 delivery fields
    event_key = Column(String(128), nullable=True, index=True)
    channel = Column(String(32), nullable=True)
    language = Column(String(16), nullable=True)
    rendered_subject = Column(String(512), nullable=True)
    rendered_body = Column(Text, nullable=True)
    # QUEUED | SENT | FAILED | SKIPPED | FALLBACK_SENT
    status = Column(String(32), nullable=False, default="QUEUED")
    error = Column(Text, nullable=True)
    dedupe_key = Column(String(128), nullable=True, index=True)


class NotificationTemplate(Base):
    """Editable per-event localised template (US-NOT-01)."""

    __tablename__ = "notification_templates"
    __table_args__ = (
        UniqueConstraint("event_key", "language", name="uq_notification_templates_event_language"),
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    event_key = Column(String(128), nullable=False, index=True)
    language = Column(String(16), nullable=False, default="en")
    subject = Column(String(512), nullable=False)
    body = Column(Text, nullable=False)
    essential = Column(Boolean, default=False, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)


class NotificationPreference(Base):
    """Per-user channel + language preferences (US-NOT-01)."""

    __tablename__ = "notification_preferences"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, unique=True, index=True
    )
    preferred_channel = Column(String(32), nullable=False, default="EMAIL")  # EMAIL | SMS | WHATSAPP
    fallback_channel = Column(String(32), nullable=True, default="SMS")
    language = Column(String(16), nullable=False, default="en")
    email = Column(String(255), nullable=True)
    phone = Column(String(32), nullable=True)
    whatsapp = Column(String(32), nullable=True)
    opt_out_non_essential = Column(Boolean, default=False, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)


class Submission(Base):
    """Stage submission lifecycle (US-SUB-02)."""

    __tablename__ = "submissions"
    __table_args__ = (
        UniqueConstraint("competitor_id", "stage_id", name="uq_submissions_competitor_stage"),
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    competition_id = Column(UUID(as_uuid=True), ForeignKey("competitions.id", ondelete="CASCADE"), nullable=False, index=True)
    competitor_id = Column(
        UUID(as_uuid=True), ForeignKey("competitors.id", ondelete="CASCADE"), nullable=False, index=True
    )
    stage_id = Column(UUID(as_uuid=True), ForeignKey("stages.id", ondelete="CASCADE"), nullable=True, index=True)
    # OPEN | UPLOADED | SCANNING | ACCEPTED | QUARANTINED | LATE | ACCEPTED_PENDING_SCAN
    state = Column(String(32), nullable=False, default="OPEN")
    deadline_at = Column(DateTime, nullable=True)
    submitted_at = Column(DateTime, nullable=True)
    late = Column(Boolean, default=False, nullable=False)
    content_hash = Column(String(128), nullable=True)
    timed_started_at = Column(DateTime, nullable=True)
    timed_expires_at = Column(DateTime, nullable=True)
    upload_locked = Column(Boolean, default=False, nullable=False)
    receipt = Column(String(64), nullable=True)
    # Blind assessment anonymised code (US-ASM-01)
    anon_code = Column(String(32), nullable=True, index=True)
    score_total = Column(Integer, nullable=True)


class Artefact(Base):
    """A deliverable file attached to a submission."""

    __tablename__ = "artefacts"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    submission_id = Column(
        UUID(as_uuid=True), ForeignKey("submissions.id", ondelete="CASCADE"), nullable=False, index=True
    )
    deliverable_code = Column(String(64), nullable=False)
    filename = Column(String(255), nullable=False)
    content_type = Column(String(128), nullable=True)
    size = Column(Integer, nullable=False, default=0)
    storage_key = Column(String(512), nullable=True)
    sha256 = Column(String(128), nullable=True)
    # PENDING | CLEAN | INFECTED
    scan_status = Column(String(32), nullable=False, default="PENDING")
    quarantined = Column(Boolean, default=False, nullable=False)
    # Resumable upload tracking
    upload_id = Column(String(64), nullable=True, unique=True, index=True)
    total_size = Column(Integer, nullable=True)
    received_bytes = Column(Integer, nullable=False, default=0)
    complete = Column(Boolean, default=False, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    completed_at = Column(DateTime, nullable=True)


class Score(Base):
    """Per-criterion (or penalty) mark for a submission (US-ASM-01)."""

    __tablename__ = "scores"
    __table_args__ = (
        UniqueConstraint(
            "submission_id",
            "criterion_id",
            "assessor_id",
            "score_type",
            name="uq_scores_submission_criterion_assessor_type",
        ),
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    submission_id = Column(
        UUID(as_uuid=True), ForeignKey("submissions.id", ondelete="CASCADE"), nullable=False, index=True
    )
    assessor_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    criterion_id = Column(String(64), nullable=False, default="overall")
    # MEASUREMENT | JUDGEMENT | PENALTY
    score_type = Column(String(32), nullable=False, default="MEASUREMENT")
    raw = Column(Integer, nullable=True)
    standardised = Column(Integer, nullable=True)
    penalty = Column(Integer, nullable=True)
    comment = Column(Text, nullable=True)
    judge_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)
    # DRAFT | FINAL
    status = Column(String(32), nullable=False, default="DRAFT")
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)


class ModerationFlag(Base):
    """Flagged judgement criterion awaiting / after moderation (US-ASM-02)."""

    __tablename__ = "moderation_flags"
    __table_args__ = (
        UniqueConstraint("submission_id", "criterion_id", name="uq_moderation_flags_submission_criterion"),
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    submission_id = Column(
        UUID(as_uuid=True), ForeignKey("submissions.id", ondelete="CASCADE"), nullable=False, index=True
    )
    criterion_id = Column(String(64), nullable=False)
    spread = Column(Integer, nullable=True)
    raw_marks = Column(JSON, nullable=False, default=list)
    flagged = Column(Boolean, default=True, nullable=False)
    # OPEN | NEEDS_SECOND_JUDGE | RESOLVED
    state = Column(String(32), nullable=False, default="OPEN")
    method = Column(String(32), nullable=True)  # STANDARDISE | MANUAL
    standardised_value = Column(Integer, nullable=True)
    reason = Column(Text, nullable=True)
    moderator_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    resolved_at = Column(DateTime, nullable=True)


class Stage(Base):
    __tablename__ = "stages"
    __table_args__ = (
        UniqueConstraint("skill_id", "order", name="uq_stages_skill_id_order"),
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    competition_id = Column(UUID(as_uuid=True), ForeignKey("competitions.id", ondelete="CASCADE"), nullable=False, index=True)
    skill_id = Column(UUID(as_uuid=True), ForeignKey("skills.id", ondelete="CASCADE"), nullable=True, index=True)
    name = Column(String(120), nullable=False)
    order = Column(Integer, nullable=False, default=1)
    stage_type = Column(String(64), nullable=False, default="GENERIC")
    opens_at = Column(DateTime, nullable=True)
    closes_at = Column(DateTime, nullable=True)
    selection_mode = Column(
        String(32),
        nullable=False,
        default=StageSelectionMode.PER_ZONE.value,
    )
    # Rollup of quota_by_zone totals (activation / legacy clone compat).
    quota = Column(Integer, nullable=True)
    # Per-zone advancement quotas: { "<zoneUuid>": int >= 0 }
    quota_by_zone = Column(JSON, nullable=True)
    min_score = Column(Integer, nullable=True)
    # Branch map: {"default": <order>, "byFamily": {"practical_trades": <order>}}
    branch = Column(JSON, nullable=True)
    # Legacy US-SUB-02 fallback; prefer published Exercise.deliverables (US-SUB-01).
    # Example:
    # {
    #   "requiredDeliverables":[{"code":"main","formats":["pdf","zip"],"maxMb":20}],
    #   "latePolicy":"block",
    #   "timedDurationSeconds": null
    # }
    submission_rules = Column(JSON, nullable=True)

    competition = relationship("Competition", back_populates="stages")
    exercise = relationship(
        "Exercise",
        back_populates="stage",
        uselist=False,
        cascade="all, delete-orphan",
    )


class Exercise(Base):
    """Challenge / test project for a stage (US-SUB-01). 1:1 with Stage; holds marking scheme."""

    __tablename__ = "exercises"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    stage_id = Column(
        UUID(as_uuid=True),
        ForeignKey("stages.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
        index=True,
    )
    competition_id = Column(UUID(as_uuid=True), ForeignKey("competitions.id", ondelete="CASCADE"), nullable=False, index=True)
    title = Column(String(200), nullable=False)
    brief = Column(Text, nullable=True)
    # [{code, label?, required, allowedTypes[], maxSizeBytes?}]
    deliverables = Column(JSON, nullable=False, default=list)
    # DRAFT | PUBLISHED
    status = Column(String(32), nullable=False, default="DRAFT")
    scheme_id = Column(UUID(as_uuid=True), ForeignKey("marking_schemes.id", ondelete="SET NULL"), nullable=True)
    # Optional late/timed policy mirrored into submission_rules shape
    late_policy = Column(String(32), nullable=True)  # block | flag-late
    timed_duration_seconds = Column(Integer, nullable=True)
    # Optional Word/PDF challenge pack (US-SUB-01 Phase 1.9)
    pack_object_key = Column(String(512), nullable=True)
    pack_file_name = Column(String(255), nullable=True)
    pack_content_type = Column(String(120), nullable=True)
    pack_scan_status = Column(String(32), nullable=True)  # CLEAN | INFECTED | PENDING
    # When EXERCISE_AVAILABLE SMS fan-out last completed successfully (or was skipped as empty)
    availability_notified_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    stage = relationship("Stage", back_populates="exercise")
    competition = relationship("Competition", back_populates="exercises")


class SmsDelivery(Base):
    """SMS delivery attempt log (Nalo) for competitors and coaches."""

    __tablename__ = "sms_deliveries"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    competitor_id = Column(
        UUID(as_uuid=True), ForeignKey("competitors.id", ondelete="SET NULL"), nullable=True, index=True
    )
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)
    competition_id = Column(
        UUID(as_uuid=True), ForeignKey("competitions.id", ondelete="SET NULL"), nullable=True, index=True
    )
    stage_id = Column(UUID(as_uuid=True), ForeignKey("stages.id", ondelete="SET NULL"), nullable=True, index=True)
    submission_id = Column(
        UUID(as_uuid=True), ForeignKey("submissions.id", ondelete="SET NULL"), nullable=True, index=True
    )
    # competitor | coach
    recipient_role = Column(String(32), nullable=False)
    phone_number = Column(String(64), nullable=False, default="")
    msisdn = Column(String(32), nullable=False, default="")
    message_type = Column(String(64), nullable=False, index=True)
    trigger = Column(String(64), nullable=False, default="")
    # pending | sent | failed
    status = Column(String(32), nullable=False, default="pending", index=True)
    error_message = Column(Text, nullable=True)
    provider = Column(String(32), nullable=False, default="nalo")
    provider_response = Column(Text, nullable=True)
    dedupe_key = Column(String(128), nullable=True, index=True)
    retried_from_id = Column(UUID(as_uuid=True), ForeignKey("sms_deliveries.id", ondelete="SET NULL"), nullable=True)
    triggered_by_user_id = Column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    sent_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)


class Shortlist(Base):
    """Provisional / confirmed shortlist for a stage (US-SHL-01)."""

    __tablename__ = "shortlists"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    competition_id = Column(UUID(as_uuid=True), ForeignKey("competitions.id", ondelete="CASCADE"), nullable=False, index=True)
    stage_id = Column(UUID(as_uuid=True), ForeignKey("stages.id", ondelete="CASCADE"), nullable=False, index=True)
    skill_id = Column(UUID(as_uuid=True), ForeignKey("skills.id", ondelete="CASCADE"), nullable=True, index=True)
    # PROVISIONAL | CONFIRMED
    state = Column(String(32), nullable=False, default="PROVISIONAL")
    is_final_stage = Column(Boolean, default=False, nullable=False)
    generated_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    confirmed_at = Column(DateTime, nullable=True)
    confirmed_by = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    payload = Column(JSON, nullable=True)  # byZone snapshot


class ShortlistEntry(Base):
    __tablename__ = "shortlist_entries"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    shortlist_id = Column(
        UUID(as_uuid=True), ForeignKey("shortlists.id", ondelete="CASCADE"), nullable=False, index=True
    )
    competitor_id = Column(
        UUID(as_uuid=True), ForeignKey("competitors.id", ondelete="CASCADE"), nullable=False, index=True
    )
    zone_id = Column(UUID(as_uuid=True), ForeignKey("zones.id", ondelete="CASCADE"), nullable=False, index=True)
    score = Column(Integer, nullable=False, default=0)
    rank = Column(Integer, nullable=False)
    # ADVANCE | WAITLIST | EXCLUDED
    outcome = Column(String(32), nullable=False)
    reason = Column(String(64), nullable=True)
    advanced = Column(Boolean, default=False, nullable=False)


class LifecycleConfig(Base):
    """Competition lifecycle config — substitution cut-off & waitlist order (US-LCY-01)."""

    __tablename__ = "lifecycle_configs"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    competition_id = Column(
        UUID(as_uuid=True), ForeignKey("competitions.id", ondelete="CASCADE"), nullable=False, unique=True, index=True
    )
    substitution_cutoff_at = Column(DateTime, nullable=False)
    # RANK = promote lowest rank number among WAITLIST in the same zone
    waitlist_order = Column(String(32), nullable=False, default="RANK")


class AppealsConfig(Base):
    """Competition appeals / DQ / tie-break config (US-APP-01). Fail closed if missing."""

    __tablename__ = "appeals_configs"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    competition_id = Column(
        UUID(as_uuid=True), ForeignKey("competitions.id", ondelete="CASCADE"), nullable=False, unique=True, index=True
    )
    appeal_window_opens_at = Column(DateTime, nullable=False)
    appeal_window_closes_at = Column(DateTime, nullable=False)
    # Allowed DQ reason codes, e.g. ["CHEATING", "MISCONDUCT"]
    dq_reasons = Column(JSON, nullable=False, default=list)
    # Ordered tie-break rules, e.g. ["SCORE_DESC", "YOUNGER_FIRST", "REF_NO_ASC", "JURY_DECISION"]
    tie_break_rules = Column(JSON, nullable=False, default=list)


class AppealCase(Base):
    """Appeal case lifecycle (US-APP-01)."""

    __tablename__ = "appeal_cases"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    competition_id = Column(UUID(as_uuid=True), ForeignKey("competitions.id", ondelete="CASCADE"), nullable=False, index=True)
    competitor_id = Column(
        UUID(as_uuid=True), ForeignKey("competitors.id", ondelete="CASCADE"), nullable=False, index=True
    )
    stage_id = Column(UUID(as_uuid=True), ForeignKey("stages.id", ondelete="CASCADE"), nullable=False, index=True)
    reason = Column(Text, nullable=False)
    # SUBMITTED | UNDER_REVIEW | UPHELD | DISMISSED | REMEDIED
    state = Column(String(32), nullable=False, default="SUBMITTED")
    officer_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)
    # UPHELD | DISMISSED
    ruling_outcome = Column(String(32), nullable=True)
    ruling_reason = Column(Text, nullable=True)
    # RE_SCORE | RE_RANK | REINSTATE
    remedy = Column(String(32), nullable=True)
    submitted_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    assigned_at = Column(DateTime, nullable=True)
    ruled_at = Column(DateTime, nullable=True)
    lodged_by = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)


class Venue(Base):
    """Physical venue with capacity (US-SCH-01; full US-ZON-01 later)."""

    __tablename__ = "venues"
    __table_args__ = (UniqueConstraint("competition_id", "name", name="uq_venues_competition_id_name"),)

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    competition_id = Column(UUID(as_uuid=True), ForeignKey("competitions.id", ondelete="CASCADE"), nullable=False, index=True)
    zone_id = Column(UUID(as_uuid=True), ForeignKey("zones.id", ondelete="SET NULL"), nullable=True, index=True)
    name = Column(String(200), nullable=False)
    capacity = Column(Integer, nullable=False)
    workstations = Column(Integer, nullable=False)
    active = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)


class ScheduleSession(Base):
    """Timed venue session with workstation capacity (US-SCH-01)."""

    __tablename__ = "schedule_sessions"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    competition_id = Column(UUID(as_uuid=True), ForeignKey("competitions.id", ondelete="CASCADE"), nullable=False, index=True)
    venue_id = Column(UUID(as_uuid=True), ForeignKey("venues.id", ondelete="CASCADE"), nullable=False, index=True)
    starts_at = Column(DateTime, nullable=False)
    ends_at = Column(DateTime, nullable=False)
    # Session size — must be ≤ venue.capacity
    workstations = Column(Integer, nullable=False)
    # SCHEDULED | IN_PROGRESS | COMPLETED | CANCELLED
    state = Column(String(32), nullable=False, default="SCHEDULED")
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    created_by = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)


class SlotAssignment(Base):
    """Competitor → workstation assignment within a session (US-SCH-01)."""

    __tablename__ = "slot_assignments"
    __table_args__ = (
        UniqueConstraint("session_id", "workstation", name="uq_slot_assignments_session_workstation"),
        UniqueConstraint("session_id", "competitor_id", name="uq_slot_assignments_session_competitor"),
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    session_id = Column(
        UUID(as_uuid=True), ForeignKey("schedule_sessions.id", ondelete="CASCADE"), nullable=False, index=True
    )
    competitor_id = Column(
        UUID(as_uuid=True), ForeignKey("competitors.id", ondelete="CASCADE"), nullable=False, index=True
    )
    workstation = Column(String(64), nullable=False)
    # PENDING | READY | NOT_READY
    readiness = Column(String(32), nullable=False, default="PENDING")
    checklist = Column(JSON, nullable=True)
    assigned_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    assigned_by = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)


class HealthSafetyIncident(Base):
    """H&S incident recorded against a physical session (US-SCH-01)."""

    __tablename__ = "health_safety_incidents"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    session_id = Column(
        UUID(as_uuid=True), ForeignKey("schedule_sessions.id", ondelete="CASCADE"), nullable=False, index=True
    )
    competition_id = Column(UUID(as_uuid=True), ForeignKey("competitions.id", ondelete="CASCADE"), nullable=False, index=True)
    summary = Column(Text, nullable=False)
    severity = Column(String(32), nullable=True)
    recorded_by = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    recorded_at = Column(DateTime, default=datetime.utcnow, nullable=False)


class PublicPortalConfig(Base):
    """Competition public-portal field set + anti-scraping limits (US-PUB-01). Fail closed if missing."""

    __tablename__ = "public_portal_configs"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    competition_id = Column(
        UUID(as_uuid=True), ForeignKey("competitions.id", ondelete="CASCADE"), nullable=False, unique=True, index=True
    )
    # Allowed public field keys, e.g. ["displayName","photo","institution","skill","stageStatus","zone"]
    public_fields = Column(JSON, nullable=False, default=list)
    rate_limit_per_minute = Column(Integer, nullable=False, default=60)
    max_page_size = Column(Integer, nullable=False, default=50)


class ResultsConfig(Base):
    """Competition results publication config — embargo/audience (US-RES-01). Fail closed if missing."""

    __tablename__ = "results_configs"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    competition_id = Column(
        UUID(as_uuid=True), ForeignKey("competitions.id", ondelete="CASCADE"), nullable=False, unique=True, index=True
    )
    release_at = Column(DateTime, nullable=False)
    # e.g. ["PUBLIC", "COMPETITOR", "INSTITUTION"]
    audience = Column(JSON, nullable=False, default=list)
    neutral_status = Column(String(64), nullable=False, default="IN_PROGRESS")
    # {"1": "GOLD", "2": "SILVER", "3": "BRONZE"}
    award_by_rank = Column(JSON, nullable=False, default=dict)
    default_outcome = Column(String(64), nullable=False, default="FINALIST")


class CertificateTemplate(Base):
    """Certificate body template per outcome for a competition (US-RES-01)."""

    __tablename__ = "certificate_templates"
    __table_args__ = (
        UniqueConstraint("competition_id", "outcome", "language", name="uq_certificate_templates_competition_outcome_lang"),
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    competition_id = Column(UUID(as_uuid=True), ForeignKey("competitions.id", ondelete="CASCADE"), nullable=False, index=True)
    outcome = Column(String(64), nullable=False)
    language = Column(String(16), nullable=False, default="en")
    body = Column(Text, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)


class ResultPublication(Base):
    """Prepared / released result set under embargo (US-RES-01)."""

    __tablename__ = "result_publications"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    competition_id = Column(UUID(as_uuid=True), ForeignKey("competitions.id", ondelete="CASCADE"), nullable=False, index=True)
    # Partial release: one skill; null = whole-cycle publication covering all prepared skills
    skill_id = Column(UUID(as_uuid=True), ForeignKey("skills.id", ondelete="CASCADE"), nullable=True, index=True)
    # Stage-scoped release (exercise results for that stage); null = finals / skill rollup
    stage_id = Column(UUID(as_uuid=True), ForeignKey("stages.id", ondelete="CASCADE"), nullable=True, index=True)
    # EMBARGOED | RELEASED
    state = Column(String(32), nullable=False, default="EMBARGOED")
    release_at = Column(DateTime, nullable=False)
    audience = Column(JSON, nullable=False, default=list)
    neutral_status = Column(String(64), nullable=False, default="IN_PROGRESS")
    prepared_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    prepared_by = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    released_at = Column(DateTime, nullable=True)
    released_by = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)


class ResultEntry(Base):
    """Versioned competitor result row (US-RES-01)."""

    __tablename__ = "result_entries"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    publication_id = Column(
        UUID(as_uuid=True), ForeignKey("result_publications.id", ondelete="CASCADE"), nullable=False, index=True
    )
    competition_id = Column(UUID(as_uuid=True), ForeignKey("competitions.id", ondelete="CASCADE"), nullable=False, index=True)
    skill_id = Column(UUID(as_uuid=True), ForeignKey("skills.id", ondelete="CASCADE"), nullable=False, index=True)
    competitor_id = Column(
        UUID(as_uuid=True), ForeignKey("competitors.id", ondelete="CASCADE"), nullable=False, index=True
    )
    outcome = Column(String(64), nullable=False)
    score = Column(Integer, nullable=True)
    rank = Column(Integer, nullable=True)
    version = Column(Integer, nullable=False, default=1)
    is_current = Column(Boolean, default=True, nullable=False)
    supersedes_id = Column(UUID(as_uuid=True), ForeignKey("result_entries.id", ondelete="SET NULL"), nullable=True)
    payload = Column(JSON, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)


class Certificate(Base):
    """Issued certificate artefact for a result entry (US-RES-01)."""

    __tablename__ = "certificates"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    competition_id = Column(UUID(as_uuid=True), ForeignKey("competitions.id", ondelete="CASCADE"), nullable=False, index=True)
    publication_id = Column(
        UUID(as_uuid=True), ForeignKey("result_publications.id", ondelete="CASCADE"), nullable=False, index=True
    )
    result_entry_id = Column(
        UUID(as_uuid=True), ForeignKey("result_entries.id", ondelete="CASCADE"), nullable=False, index=True
    )
    competitor_id = Column(
        UUID(as_uuid=True), ForeignKey("competitors.id", ondelete="CASCADE"), nullable=False, index=True
    )
    outcome = Column(String(64), nullable=False)
    rendered_body = Column(Text, nullable=True)
    version = Column(Integer, nullable=False, default=1)
    is_current = Column(Boolean, default=True, nullable=False)
    supersedes_id = Column(UUID(as_uuid=True), ForeignKey("certificates.id", ondelete="SET NULL"), nullable=True)
    issued_at = Column(DateTime, default=datetime.utcnow, nullable=False)


class AuditEvent(Base):
    __tablename__ = "audit_events"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    competition_id = Column(UUID(as_uuid=True), nullable=True, index=True)
    actor_id = Column(UUID(as_uuid=True), nullable=True, index=True)
    actor_role = Column(String(64), nullable=True)
    action = Column(String(128), nullable=False)
    entity_type = Column(String(64), nullable=False)
    entity_id = Column(String(64), nullable=False)
    before = Column(JSON, nullable=True)
    after = Column(JSON, nullable=True)
    reason = Column(Text, nullable=True)
    ip = Column(String(64), nullable=True)
    user_agent = Column(String(512), nullable=True)
    timestamp = Column(DateTime, default=datetime.utcnow, nullable=False)
    signature = Column(String(128), nullable=False)


class DsarJob(Base):
    """Data-subject access / erasure / consent-withdrawal job (US-AUD-01)."""

    __tablename__ = "dsar_jobs"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    subject_id = Column(UUID(as_uuid=True), nullable=False, index=True)
    request_type = Column(String(32), nullable=False)  # ACCESS | ERASURE | WITHDRAW
    status = Column(String(32), nullable=False, default="QUEUED")
    requested_by = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    export_payload = Column(JSON, nullable=True)
    result_summary = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    completed_at = Column(DateTime, nullable=True)


class SystemSettings(Base):
    """Singleton platform settings (one row)."""

    __tablename__ = "system_settings"

    id = Column(Integer, primary_key=True, default=1)
    institution_registration_enabled = Column(Boolean, nullable=False, default=False)
    allow_multiple_active_competitions = Column(Boolean, nullable=False, default=True)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)
