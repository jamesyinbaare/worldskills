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


class CycleStatus(str, enum.Enum):
    DRAFT = "DRAFT"
    ACTIVE = "ACTIVE"
    LOCKED = "LOCKED"
    CLOSED = "CLOSED"


class Region(enum.Enum):
    ASHANTI = "Ashanti"
    BONO = "Bono"
    BONO_EAST = "Bono East"
    AHAFO = "Ahafo"
    CENTRAL = "Central"
    EASTERN = "Eastern"
    GREATER_ACCRA = "Greater Accra"
    NORTHERN = "Northern"
    NORTH_EAST = "North East"
    SAVANNAH = "Savannah"
    UPPER_EAST = "Upper East"
    UPPER_WEST = "Upper West"
    VOLTA = "Volta"
    OTI = "Oti"
    WESTERN = "Western"
    WESTERN_NORTH = "Western North"


class User(Base):
    __tablename__ = "users"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    email = Column(String(255), unique=True, nullable=True, index=True)
    username = Column(String(80), unique=True, nullable=True, index=True)
    phone_number = Column(String(50), nullable=True, index=True)
    hashed_password = Column(String(255), nullable=True)
    full_name = Column(String(255), nullable=False)
    role = Column(Enum(UserRole, name="userrole", create_constraint=False), nullable=False)
    is_active = Column(Boolean, default=True, nullable=False)
    institution_id = Column(UUID(as_uuid=True), ForeignKey("institutions.id", ondelete="SET NULL"), nullable=True, index=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)
    last_login = Column(DateTime, nullable=True)

    refresh_tokens = relationship("RefreshToken", back_populates="user", cascade="all, delete-orphan")
    institution = relationship("Institution", foreign_keys=[institution_id])


class Institution(Base):
    """Minimal institution record for COI / nominations (FR-5)."""

    __tablename__ = "institutions"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = Column(String(200), nullable=False, unique=True)
    active = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)


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


class Cycle(Base):
    __tablename__ = "cycles"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = Column(String(120), nullable=False, index=True)
    period_start = Column(Date, nullable=False)
    period_end = Column(Date, nullable=False)
    time_zone = Column(String(64), nullable=False)
    status = Column(
        Enum(CycleStatus, name="cyclestatus", create_constraint=False),
        nullable=False,
        default=CycleStatus.DRAFT,
    )
    languages = Column(JSON, nullable=False, default=list)
    organising_body = Column(JSON, nullable=True)
    branding = Column(JSON, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    skills = relationship("Skill", back_populates="cycle", cascade="all, delete-orphan")
    stages = relationship("Stage", back_populates="cycle", cascade="all, delete-orphan")
    age_rules = relationship("AgeRule", back_populates="cycle", cascade="all, delete-orphan")
    pathways = relationship("Pathway", back_populates="cycle", cascade="all, delete-orphan")
    marking_schemes = relationship("MarkingScheme", back_populates="cycle", cascade="all, delete-orphan")


class AgeRule(Base):
    __tablename__ = "age_rules"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    cycle_id = Column(UUID(as_uuid=True), ForeignKey("cycles.id", ondelete="CASCADE"), nullable=False, index=True)
    name = Column(String(120), nullable=False)
    max_age = Column(Integer, nullable=False)
    reference_date = Column(Date, nullable=True)

    cycle = relationship("Cycle", back_populates="age_rules")


class Pathway(Base):
    __tablename__ = "pathways"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    cycle_id = Column(UUID(as_uuid=True), ForeignKey("cycles.id", ondelete="CASCADE"), nullable=False, index=True)
    name = Column(String(120), nullable=False)

    cycle = relationship("Cycle", back_populates="pathways")


class MarkingScheme(Base):
    __tablename__ = "marking_schemes"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    cycle_id = Column(UUID(as_uuid=True), ForeignKey("cycles.id", ondelete="CASCADE"), nullable=False, index=True)
    name = Column(String(120), nullable=False)

    cycle = relationship("Cycle", back_populates="marking_schemes")


class Skill(Base):
    __tablename__ = "skills"
    __table_args__ = (UniqueConstraint("cycle_id", "name", name="uq_skills_cycle_id_name"),)

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    cycle_id = Column(UUID(as_uuid=True), ForeignKey("cycles.id", ondelete="CASCADE"), nullable=False, index=True)
    name = Column(String(120), nullable=False)
    number = Column(String(32), nullable=True)
    family_id = Column(String(64), nullable=True)
    age_rule_id = Column(UUID(as_uuid=True), ForeignKey("age_rules.id", ondelete="SET NULL"), nullable=True)
    pathway_id = Column(UUID(as_uuid=True), ForeignKey("pathways.id", ondelete="SET NULL"), nullable=True)
    scheme_id = Column(UUID(as_uuid=True), ForeignKey("marking_schemes.id", ondelete="SET NULL"), nullable=True)
    capacity = Column(Integer, nullable=True)
    active = Column(Boolean, default=True, nullable=False)

    cycle = relationship("Cycle", back_populates="skills")


class Zone(Base):
    """Cycle-scoped zone stub (full US-ZON-01 later). Required for expert assignment."""

    __tablename__ = "zones"
    __table_args__ = (UniqueConstraint("cycle_id", "name", name="uq_zones_cycle_id_name"),)

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    cycle_id = Column(UUID(as_uuid=True), ForeignKey("cycles.id", ondelete="CASCADE"), nullable=False, index=True)
    name = Column(String(120), nullable=False)
    active = Column(Boolean, default=True, nullable=False)


class ExpertAssignment(Base):
    __tablename__ = "expert_assignments"
    __table_args__ = (
        UniqueConstraint(
            "cycle_id", "expert_id", "skill_id", "zone_id", name="uq_expert_assignments_cycle_expert_skill_zone"
        ),
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    cycle_id = Column(UUID(as_uuid=True), ForeignKey("cycles.id", ondelete="CASCADE"), nullable=False, index=True)
    expert_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    skill_id = Column(UUID(as_uuid=True), ForeignKey("skills.id", ondelete="CASCADE"), nullable=False, index=True)
    zone_id = Column(UUID(as_uuid=True), ForeignKey("zones.id", ondelete="CASCADE"), nullable=False, index=True)
    coi_flags = Column(JSON, nullable=False, default=list)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)


class Competitor(Base):
    """Competitor record — nomination shell or full registration (US-REG-01)."""

    __tablename__ = "competitors"
    __table_args__ = (UniqueConstraint("cycle_id", "ref_no", name="uq_competitors_cycle_id_ref_no"),)

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    cycle_id = Column(UUID(as_uuid=True), ForeignKey("cycles.id", ondelete="CASCADE"), nullable=False, index=True)
    skill_id = Column(UUID(as_uuid=True), ForeignKey("skills.id", ondelete="CASCADE"), nullable=False, index=True)
    zone_id = Column(UUID(as_uuid=True), ForeignKey("zones.id", ondelete="CASCADE"), nullable=False, index=True)
    institution_id = Column(
        UUID(as_uuid=True), ForeignKey("institutions.id", ondelete="SET NULL"), nullable=True, index=True
    )
    ref_no = Column(String(64), nullable=False)
    status = Column(String(32), nullable=False, default="REGISTERED")
    # Registration profile (nullable when created via nomination shell)
    given_names = Column(String(100), nullable=True)
    family_name = Column(String(100), nullable=True)
    date_of_birth = Column(Date, nullable=True)
    email = Column(String(255), nullable=True)
    mobile = Column(String(32), nullable=True)
    whatsapp = Column(String(32), nullable=True)
    national_id = Column(String(64), nullable=True, index=True)
    photo_key = Column(String(512), nullable=True)
    coach = Column(JSON, nullable=True)
    flags = Column(JSON, nullable=False, default=list)
    registration_payload = Column(JSON, nullable=True)
    # Guardian consent (US-REG-02) — privacy by default for minors
    guardian_name = Column(String(200), nullable=True)
    guardian_email = Column(String(255), nullable=True)
    guardian_phone = Column(String(32), nullable=True)
    consent_participation_at = Column(DateTime, nullable=True)
    consent_participation_by = Column(String(255), nullable=True)
    consent_public_at = Column(DateTime, nullable=True)
    consent_public_by = Column(String(255), nullable=True)
    public_profile_visible = Column(Boolean, default=False, nullable=False)


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
    """Cycle registration open/close window — fail closed if missing."""

    __tablename__ = "registration_windows"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    cycle_id = Column(
        UUID(as_uuid=True), ForeignKey("cycles.id", ondelete="CASCADE"), nullable=False, unique=True, index=True
    )
    opens_at = Column(DateTime, nullable=False)
    closes_at = Column(DateTime, nullable=False)


class RegistrationFormDefinition(Base):
    """Configurable registration form (FR-6.13) — never hard-code field rules in code paths."""

    __tablename__ = "registration_form_definitions"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    cycle_id = Column(
        UUID(as_uuid=True), ForeignKey("cycles.id", ondelete="CASCADE"), nullable=False, unique=True, index=True
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
    __table_args__ = (UniqueConstraint("cycle_id", "key", name="uq_idempotency_records_cycle_key"),)

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    cycle_id = Column(UUID(as_uuid=True), ForeignKey("cycles.id", ondelete="CASCADE"), nullable=False, index=True)
    key = Column(String(128), nullable=False)
    status_code = Column(Integer, nullable=False)
    response_body = Column(JSON, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)


class InstitutionCycleMembership(Base):
    """Links an institution to a cycle zone (precondition for nominations)."""

    __tablename__ = "institution_cycle_memberships"
    __table_args__ = (
        UniqueConstraint("cycle_id", "institution_id", name="uq_institution_cycle_memberships_cycle_institution"),
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    cycle_id = Column(UUID(as_uuid=True), ForeignKey("cycles.id", ondelete="CASCADE"), nullable=False, index=True)
    institution_id = Column(
        UUID(as_uuid=True), ForeignKey("institutions.id", ondelete="CASCADE"), nullable=False, index=True
    )
    zone_id = Column(UUID(as_uuid=True), ForeignKey("zones.id", ondelete="CASCADE"), nullable=False, index=True)


class NominationLimit(Base):
    """Per-institution, per-skill nomination limit (config — fail closed if missing)."""

    __tablename__ = "nomination_limits"
    __table_args__ = (
        UniqueConstraint(
            "cycle_id", "institution_id", "skill_id", name="uq_nomination_limits_cycle_institution_skill"
        ),
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    cycle_id = Column(UUID(as_uuid=True), ForeignKey("cycles.id", ondelete="CASCADE"), nullable=False, index=True)
    institution_id = Column(
        UUID(as_uuid=True), ForeignKey("institutions.id", ondelete="CASCADE"), nullable=False, index=True
    )
    skill_id = Column(UUID(as_uuid=True), ForeignKey("skills.id", ondelete="CASCADE"), nullable=False, index=True)
    max_nominations = Column(Integer, nullable=False)


class Nomination(Base):
    __tablename__ = "nominations"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    cycle_id = Column(UUID(as_uuid=True), ForeignKey("cycles.id", ondelete="CASCADE"), nullable=False, index=True)
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
    """Stub outbox until US-NOT-01 — tests assert notify happened."""

    __tablename__ = "notification_outbox"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    cycle_id = Column(UUID(as_uuid=True), nullable=True, index=True)
    recipient_role = Column(String(64), nullable=False)
    recipient_id = Column(UUID(as_uuid=True), nullable=True, index=True)
    template = Column(String(128), nullable=False)
    payload = Column(JSON, nullable=False, default=dict)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)


class Submission(Base):
    """Minimal submission for assessor queue (full submission lifecycle later)."""

    __tablename__ = "submissions"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    cycle_id = Column(UUID(as_uuid=True), ForeignKey("cycles.id", ondelete="CASCADE"), nullable=False, index=True)
    competitor_id = Column(
        UUID(as_uuid=True), ForeignKey("competitors.id", ondelete="CASCADE"), nullable=False, index=True
    )
    state = Column(String(32), nullable=False, default="ACCEPTED")


class Score(Base):
    """Minimal score row for segregation-of-duties checks (full assessment later)."""

    __tablename__ = "scores"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    submission_id = Column(
        UUID(as_uuid=True), ForeignKey("submissions.id", ondelete="CASCADE"), nullable=False, index=True
    )
    assessor_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    criterion_id = Column(String(64), nullable=False, default="overall")
    raw = Column(Integer, nullable=True)


class Stage(Base):
    __tablename__ = "stages"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    cycle_id = Column(UUID(as_uuid=True), ForeignKey("cycles.id", ondelete="CASCADE"), nullable=False, index=True)
    skill_id = Column(UUID(as_uuid=True), ForeignKey("skills.id", ondelete="CASCADE"), nullable=True, index=True)
    name = Column(String(120), nullable=False)
    order = Column(Integer, nullable=False, default=1)
    stage_type = Column(String(64), nullable=False, default="GENERIC")
    opens_at = Column(DateTime, nullable=True)
    closes_at = Column(DateTime, nullable=True)
    quota = Column(Integer, nullable=True)
    min_score = Column(Integer, nullable=True)
    scheme_id = Column(UUID(as_uuid=True), ForeignKey("marking_schemes.id", ondelete="SET NULL"), nullable=True)

    cycle = relationship("Cycle", back_populates="stages")


class AuditEvent(Base):
    __tablename__ = "audit_events"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    cycle_id = Column(UUID(as_uuid=True), nullable=True, index=True)
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
