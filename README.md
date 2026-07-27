# Skills Competition Management System (SCMS)

**A configuration-driven platform for running national and international skills competitions** — from registration and eligibility screening through multi-stage assessment, shortlisting, appeals, and embargoed results publication.

Built for **WorldSkills Ghana (WSGh)** and similar bodies. Fully compliant with privacy, audit, and fairness requirements.

---

## 🎯 Overview

SCMS manages the **full lifecycle** of a skills competition:

- **Configuration** → **Registration & Nomination** → **Eligibility & Screening** → **Test Project Submission** → **Expert Assessment & Moderation** → **Shortlisting & Progression** → **Appeals & Disqualifications** → **Scheduling (Physical Stages)** → **Results & Certificates** → **Public Portal**

**Key Differentiators**:
- **100% configuration-driven** — no code changes needed for new competitions, skills, or rules.
- **Strong governance**: Immutable audit trail, RBAC, Conflict of Interest (COI), segregation of duties, privacy-by-default for minors.
- **Competition isolation** — multiple competitions run independently in the same instance.
- **Embargo-aware** public portal and results.

---

## 📋 Core Features (by Epic)

### Phase 1 — MVP
- **Configuration & Setup** (Epic A): Create/clone/validate/activate competitions.
- **Skills, Zones & Pathways** (Epic B): Per-skill rules, age limits, branching pathways.
- **Access & COI** (Epic C): Expert assignment with conflict enforcement.
- **Registration** (Epic D): Institutions nominate → competitors register → guardian consent for minors.
- **Eligibility** (Epic E): Age verification + rule-based screening + overrides.
- **Stages & Pathways** (Epic F): Quotas, thresholds, branching.
- **Submission** (Epic G): Secure, resumable uploads with malware scanning, hashing, timed projects.
- **Assessment** (Epic H): Blind scoring, measurement + judgement marks, moderation/standardisation, penalties.
- **Shortlisting** (Epic I): Ranked shortlists, waitlists, confirmation.
- **Notifications** (Epic M): Event-driven, multi-channel English templates.
- **Results & Certificates** (Epic N): Embargo, release, corrections, template-based certificates.

### Phase 2 — Hardening
- Competitor lifecycle (withdraw/substitute).
- **Appeals, Tie-breaking & Disqualifications** (Epic K).
- Physical stage scheduling & workstation assignment.
- **Public Portal** with consent-gated profiles and embargo-aware progression.
- **Audit & Data Governance** (DSAR, immutable logs).

### Phase 3 — Future
Reporting, dashboards, bulk import, advanced anti-cheating, etc.

---

## 🏗️ Architecture

### Logical Services
- **Config Service** — Cycles, skills, stages, rubrics, forms.
- **Identity & Access** — RBAC, COI, expert assignments.
- **Registration** — Nominations, forms, consent.
- **Assessment** — Submissions, scoring, moderation, shortlisting.
- **Integrity** — Upload scanning, hashing, timestamps.
- **Scheduling** — Venues, sessions, capacity.
- **Notification** — Templates + delivery.
- **Publishing** — Embargoed results, public portal.
- **Platform** — Audit, storage, governance.

### Key Design Principles (from `CLAUDE.md`)
1. **Configuration over code** — Fail closed with `CONFIG_INCOMPLETE`.
2. **Spec is truth** — Implement exactly to acceptance criteria.
3. **Tests first (TDD)** — One test per AC ID.
4. **Auditability** — Every result-affecting action is immutable.
5. **Privacy by default** — Minors require guardian consent; no sensitive PII in public endpoints.
6. **Competition isolation** & **RBAC** on every endpoint.

### Data Model Highlights
See `plan.md` for full details. Key entities: `Competition`, `Skill`, `Stage`, `Competitor`, `Submission`, `Score`, `AppealCase`.

### State Machines
- Competitor, Submission, and Appeal lifecycles fully defined in `plan.md`.

---

## 🛠️ Tech Stack

- **Backend**: TypeScript + Node.js (FastAPI)
- **Database**: PostgreSQL (SQLAlchemy/Alembic)
- **Frontend**: Next.js / React (Tailwind, Shadcn, Radix)
- **Storage**: S3-compatible (MinIO for dev)
- **Auth**: OIDC / JWT

---

## 📁 Project Structure
