<!--
  Sync Impact Report
  ==================
  Version change: N/A (initial) -> 1.0.0
  Modified principles: N/A (initial creation)
  Added sections:
    - Core Principles (7 principles)
    - Technology Stack & Deployment Constraints
    - Data Management & Interaction Model
    - Governance
  Removed sections: N/A
  Templates requiring updates:
    - .specify/templates/plan-template.md: ✅ compatible (no changes needed)
    - .specify/templates/spec-template.md: ✅ compatible (no changes needed)
    - .specify/templates/tasks-template.md: ✅ compatible (no changes needed)
    - .specify/templates/commands/*.md: no command files exist
    - README.md: ⚠️ pending (currently empty, should be filled during
      first feature spec)
  Follow-up TODOs: none
-->

# Luna the Dog Constitution

## Core Principles

### I. Open Source & Unrestricted

This project MUST remain fully open source with no licensing
restrictions, usage limitations, or distribution constraints. All code,
documentation, and assets MUST be freely available to anyone.

- No paid features, subscriptions, or premium tiers are permitted.
- No telemetry, analytics, or data collection beyond what the
  owner explicitly configures on their own server.
- Contributions from the community are welcome without CLA
  requirements.

### II. Voice-First Multi-Modal Input

The primary interaction mode is natural language through Telegram
(voice messages and text). The system MUST treat voice, text, and
photo inputs as first-class citizens.

- Voice messages MUST be transcribed and processed with the same
  fidelity as text input.
- Photos MUST be analyzed and metadata extracted automatically
  (e.g., pet condition, document scans, vaccination cards).
- The user MUST NOT need to learn special command syntax; natural
  language is the interface.

### III. Comprehensive Pet Knowledge Base

The core value proposition is accumulating a complete, structured,
and queryable history of each pet. Every interaction MUST contribute
to building this knowledge base.

- The system MUST store: profile data (name, birthday, breed,
  weight history, origin), vaccination records with dates,
  medical history (illnesses, surgeries, castration), medication
  schedules, diet/food history, feeding diary, and free-form notes.
- Historical perspective MUST be preserved: when data changes
  (e.g., food brand switch), the previous value and date range
  MUST be retained, not overwritten.
- The knowledge base MUST support multiple pets per household.

### IV. Proactive Care & Reminders

The system MUST NOT be purely reactive. It MUST proactively
remind, follow up, and prompt the family about pet care tasks.

- Medication reminders MUST be scheduled based on the prescribed
  frequency (e.g., "every 3 months") and fire on time.
- After a reminder fires, the system MUST follow up to confirm
  whether the action was taken (e.g., "Did you give Luna the
  medication?").
- Vaccination due dates MUST be tracked and reminders sent
  in advance.
- The system SHOULD suggest veterinary checkups based on age
  and medical history patterns.

### V. Conversational Agent Architecture

The system operates as an AI agent powered by OpenAI API with
structured tool calling. The agent MUST have access to the full
pet knowledge base as context when answering questions.

- The agent MUST use function/tool calls to read and write
  structured data (not free-text parsing alone).
- When the family asks health-related questions, the agent MUST
  consider the pet's full history (vaccinations, medications,
  conditions, diet) before responding.
- The agent MUST clearly distinguish between factual pet data
  and AI-generated advice, and recommend veterinary consultation
  for serious health concerns.

### VI. Family-First Simplicity

This is a family project. Every family member MUST be able to
interact with the system without technical knowledge.

- Telegram is the primary interface; no terminal or web login
  MUST be required for daily use.
- The web dashboard serves as a secondary read/management
  interface and MUST be intuitive.
- Error messages MUST be human-friendly, never exposing stack
  traces or technical jargon to family users.
- The system MUST handle ambiguous or incomplete input
  gracefully, asking clarifying questions when needed.

### VII. Self-Hosted & Privacy-Respecting

All pet and family data MUST reside on the family's own
infrastructure. No third-party services may store pet data
beyond transient API calls.

- The system MUST be deployable on a single Ubuntu VDS
  via SSH without complex orchestration.
- External API calls (OpenAI, Telegram) MUST only transmit
  the minimum data necessary for processing.
- Backups MUST be supported to prevent data loss.
- Docker-based deployment SHOULD be the default for
  reproducibility and ease of updates.

## Technology Stack & Deployment Constraints

The following technology choices are binding for this project:

- **Language**: Python 3.11+
- **Web Framework**: FastAPI (for web dashboard and webhook
  endpoints)
- **Telegram Bot**: aiogram 3.x (async Telegram Bot framework)
- **AI Backend**: OpenAI API (GPT models with function calling)
- **Database**: PostgreSQL (with SQLAlchemy or asyncpg as ORM/driver)
- **Voice Processing**: OpenAI Whisper API for speech-to-text
- **Deployment Target**: Ubuntu VDS, accessible via SSH
- **Containerization**: Docker + Docker Compose for deployment
- **Migrations**: Alembic for database schema migrations

All dependencies MUST be pinned to specific versions in
requirements files. The system MUST run on a modest VDS
(2 CPU, 4 GB RAM) without performance degradation for a
single-family workload.

## Data Management & Interaction Model

All interactions follow the pattern: **Input -> Agent Processing
-> Structured Storage + Response**.

- **Input channels**: Telegram voice messages, Telegram text,
  Telegram photos, web dashboard forms.
- **Processing**: OpenAI agent extracts structured data from
  natural language, calls appropriate tools to read/write
  the database.
- **Storage**: All pet data is stored in PostgreSQL with proper
  relations, timestamps, and audit trails.
- **Output**: Natural language responses via Telegram, structured
  views via web dashboard.
- **Reminders**: A scheduler (e.g., APScheduler or Celery Beat)
  runs periodic checks for due reminders and sends Telegram
  notifications.
- **Context assembly**: Before answering health questions, the
  agent MUST retrieve relevant pet history sections to include
  in the LLM context.

## Governance

This constitution is the foundational document for the Luna the
Dog project. All design decisions, feature implementations, and
architectural choices MUST align with these principles.

- **Amendments**: Any change to this constitution MUST be
  documented with rationale, reviewed, and versioned. Changes
  to Core Principles require a MAJOR version bump.
- **Versioning**: The constitution follows semantic versioning
  (MAJOR.MINOR.PATCH). MAJOR for principle changes, MINOR for
  new sections or material expansions, PATCH for clarifications.
- **Compliance**: Every pull request and feature spec MUST be
  checked against applicable principles before merge.
- **Guidance**: Use CLAUDE.md and project memory files for
  runtime development guidance and conventions that do not
  rise to constitutional level.

**Version**: 1.0.0 | **Ratified**: 2026-03-07 | **Last Amended**: 2026-03-07
