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
    open_category_enabled = Column(Boolean, default=False, nullable=False)

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
    # US-ASM-01 rubric config — fail closed when scoring if missing criteria
    # {
    #   "blindMode": true,
    #   "criteria":[{"id":"c1","name":"Accuracy","type":"MEASUREMENT","max":15}],
    #   "penalties":[{"code":"MINOR_NON_COMPLIANCE","deduction":2,"cap":5}]
    # }
    rubric = Column(JSON, nullable=True)

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
    # Extra eligibility checks beyond age, e.g. {"requireNationality":["GH"],"requireEnrolmentAttestation":true}
    eligibility_rules = Column(JSON, nullable=True)

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
    # Bound login account for competitor portal actions (US-SUB-02)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)
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
    """Notification delivery log / outbox (US-NOT-01)."""

    __tablename__ = "notification_outbox"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    cycle_id = Column(UUID(as_uuid=True), nullable=True, index=True)
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
    cycle_id = Column(UUID(as_uuid=True), ForeignKey("cycles.id", ondelete="CASCADE"), nullable=False, index=True)
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
    cycle_id = Column(UUID(as_uuid=True), ForeignKey("cycles.id", ondelete="CASCADE"), nullable=False, index=True)
    skill_id = Column(UUID(as_uuid=True), ForeignKey("skills.id", ondelete="CASCADE"), nullable=True, index=True)
    name = Column(String(120), nullable=False)
    order = Column(Integer, nullable=False, default=1)
    stage_type = Column(String(64), nullable=False, default="GENERIC")
    opens_at = Column(DateTime, nullable=True)
    closes_at = Column(DateTime, nullable=True)
    # Rollup of quota_by_zone totals (activation / legacy clone compat).
    quota = Column(Integer, nullable=True)
    # Per-zone advancement quotas: { "<zoneUuid>": int >= 0 }
    quota_by_zone = Column(JSON, nullable=True)
    min_score = Column(Integer, nullable=True)
    scheme_id = Column(UUID(as_uuid=True), ForeignKey("marking_schemes.id", ondelete="SET NULL"), nullable=True)
    # Branch map: {"default": <order>, "byFamily": {"practical_trades": <order>}}
    branch = Column(JSON, nullable=True)
    # US-SUB-02 (US-SUB-01 stub): required deliverables, formats, late policy, timed duration
    # Example:
    # {
    #   "requiredDeliverables":[{"code":"main","formats":["pdf","zip"],"maxMb":20}],
    #   "latePolicy":"block",
    #   "timedDurationSeconds": null
    # }
    submission_rules = Column(JSON, nullable=True)

    cycle = relationship("Cycle", back_populates="stages")


class Shortlist(Base):
    """Provisional / confirmed shortlist for a stage (US-SHL-01)."""

    __tablename__ = "shortlists"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    cycle_id = Column(UUID(as_uuid=True), ForeignKey("cycles.id", ondelete="CASCADE"), nullable=False, index=True)
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
    """Cycle lifecycle config — substitution cut-off & waitlist order (US-LCY-01)."""

    __tablename__ = "lifecycle_configs"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    cycle_id = Column(
        UUID(as_uuid=True), ForeignKey("cycles.id", ondelete="CASCADE"), nullable=False, unique=True, index=True
    )
    substitution_cutoff_at = Column(DateTime, nullable=False)
    # RANK = promote lowest rank number among WAITLIST in the same zone
    waitlist_order = Column(String(32), nullable=False, default="RANK")


class AppealsConfig(Base):
    """Cycle appeals / DQ / tie-break config (US-APP-01). Fail closed if missing."""

    __tablename__ = "appeals_configs"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    cycle_id = Column(
        UUID(as_uuid=True), ForeignKey("cycles.id", ondelete="CASCADE"), nullable=False, unique=True, index=True
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
    cycle_id = Column(UUID(as_uuid=True), ForeignKey("cycles.id", ondelete="CASCADE"), nullable=False, index=True)
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
    __table_args__ = (UniqueConstraint("cycle_id", "name", name="uq_venues_cycle_id_name"),)

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    cycle_id = Column(UUID(as_uuid=True), ForeignKey("cycles.id", ondelete="CASCADE"), nullable=False, index=True)
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
    cycle_id = Column(UUID(as_uuid=True), ForeignKey("cycles.id", ondelete="CASCADE"), nullable=False, index=True)
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
    cycle_id = Column(UUID(as_uuid=True), ForeignKey("cycles.id", ondelete="CASCADE"), nullable=False, index=True)
    summary = Column(Text, nullable=False)
    severity = Column(String(32), nullable=True)
    recorded_by = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    recorded_at = Column(DateTime, default=datetime.utcnow, nullable=False)


class PublicPortalConfig(Base):
    """Cycle public-portal field set + anti-scraping limits (US-PUB-01). Fail closed if missing."""

    __tablename__ = "public_portal_configs"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    cycle_id = Column(
        UUID(as_uuid=True), ForeignKey("cycles.id", ondelete="CASCADE"), nullable=False, unique=True, index=True
    )
    # Allowed public field keys, e.g. ["displayName","photo","institution","skill","stageStatus","zone"]
    public_fields = Column(JSON, nullable=False, default=list)
    rate_limit_per_minute = Column(Integer, nullable=False, default=60)
    max_page_size = Column(Integer, nullable=False, default=50)


class ResultsConfig(Base):
    """Cycle results publication config — embargo/audience (US-RES-01). Fail closed if missing."""

    __tablename__ = "results_configs"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    cycle_id = Column(
        UUID(as_uuid=True), ForeignKey("cycles.id", ondelete="CASCADE"), nullable=False, unique=True, index=True
    )
    release_at = Column(DateTime, nullable=False)
    # e.g. ["PUBLIC", "COMPETITOR", "INSTITUTION"]
    audience = Column(JSON, nullable=False, default=list)
    neutral_status = Column(String(64), nullable=False, default="IN_PROGRESS")
    # {"1": "GOLD", "2": "SILVER", "3": "BRONZE"}
    award_by_rank = Column(JSON, nullable=False, default=dict)
    default_outcome = Column(String(64), nullable=False, default="FINALIST")


class CertificateTemplate(Base):
    """Certificate body template per outcome for a cycle (US-RES-01)."""

    __tablename__ = "certificate_templates"
    __table_args__ = (
        UniqueConstraint("cycle_id", "outcome", "language", name="uq_certificate_templates_cycle_outcome_lang"),
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    cycle_id = Column(UUID(as_uuid=True), ForeignKey("cycles.id", ondelete="CASCADE"), nullable=False, index=True)
    outcome = Column(String(64), nullable=False)
    language = Column(String(16), nullable=False, default="en")
    body = Column(Text, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)


class ResultPublication(Base):
    """Prepared / released result set under embargo (US-RES-01)."""

    __tablename__ = "result_publications"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    cycle_id = Column(UUID(as_uuid=True), ForeignKey("cycles.id", ondelete="CASCADE"), nullable=False, index=True)
    # Partial release: one skill; null = whole-cycle publication covering all prepared skills
    skill_id = Column(UUID(as_uuid=True), ForeignKey("skills.id", ondelete="CASCADE"), nullable=True, index=True)
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
    cycle_id = Column(UUID(as_uuid=True), ForeignKey("cycles.id", ondelete="CASCADE"), nullable=False, index=True)
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
    cycle_id = Column(UUID(as_uuid=True), ForeignKey("cycles.id", ondelete="CASCADE"), nullable=False, index=True)
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
