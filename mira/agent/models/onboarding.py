"""Canonical onboarding state object (PRD §2.2)."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal, Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

OnboardingPhaseState = Literal[
    "intake",
    "research",
    "map",
    "awaiting_approval",
    "code",
    "dry_run",
    "initial_sync",
    "scheduled",
    "failed",
]

SourceSystem = Literal[
    "stripe",
    "invoiced",
    "google_sheets",
    "epicor",
    "generic_rest",
    "csv_drop",
    "sftp",
    "unknown",
]
Deployment = Literal["cloud", "on_prem", "hybrid", "unknown"]
AccessMethod = Literal[
    "api_key",
    "oauth",
    "db_dump",
    "sftp",
    "shared_drive",
    "csv_export",
    "unknown",
]
AuthStatus = Literal["missing", "provided", "validated", "failed"]
FrequencyRequired = Literal["realtime", "hourly", "daily", "weekly"]

ArtifactKind = Literal[
    "sample_csv",
    "api_doc_url",
    "uploaded_pdf",
    "api_response_sample",
]

DomainKind = Literal["categorical", "range", "regex", "unique_id", "freeform_text"]
SemanticRole = Literal[
    "monetary_amount",
    "currency_code",
    "timestamp",
    "identifier",
    "foreign_key",
    "category",
    "text",
    "boolean",
    "other",
]

BlockerNeeds = Literal["customer_input", "fde_input", "research"]
StakeholderRole = Literal["customer", "fde", "internal", "other"]
ConversationRole = Literal["user", "assistant", "system"]
ResearchStatus = Literal["not_started", "heuristic", "web", "blocked"]


class SourceProfile(BaseModel):
    model_config = ConfigDict(extra="forbid")

    system: SourceSystem = "unknown"
    deployment: Deployment = "unknown"
    access_method: AccessMethod = "unknown"
    auth_status: AuthStatus = "missing"
    frequency_required: FrequencyRequired = "daily"
    historical_backfill_required: bool = True
    business_quirks: list[str] = Field(default_factory=list)


class ArtifactCollected(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kind: ArtifactKind
    uri: str
    ingested_at: datetime


class TableLinkage(BaseModel):
    model_config = ConfigDict(extra="forbid")

    to_table: str
    via: str
    cardinality: Literal["one_to_one", "many_to_one", "one_to_many", "many_to_many"]


class TableDescription(BaseModel):
    model_config = ConfigDict(extra="forbid")

    table_name: str
    summary: str
    row_grain: str
    linkages: list[TableLinkage] = Field(default_factory=list)
    datasource: str = ""
    pull_process: str = ""
    known_quirks: list[str] = Field(default_factory=list)


class ColumnDomain(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kind: DomainKind
    min: Optional[float] = None
    max: Optional[float] = None
    pattern: Optional[str] = None


class ColumnDescription(BaseModel):
    model_config = ConfigDict(extra="forbid")

    table_name: str
    field: str
    datatype: str
    domain: Optional[ColumnDomain] = None
    missing_indicator: str = ""
    unit: str = ""
    semantic_role: SemanticRole = "other"
    nl_summary: str = ""


class Blocker(BaseModel):
    model_config = ConfigDict(extra="forbid")

    code: str
    message: str
    needs: BlockerNeeds


class Approval(BaseModel):
    model_config = ConfigDict(extra="forbid")

    customer_confirmed_at: Optional[datetime] = None
    fde_confirmed_at: Optional[datetime] = None
    fde_user: Optional[str] = None
    customer_telegram_user_id: Optional[str] = None
    fde_telegram_user_id: Optional[str] = None


class StakeholderSummary(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = ""
    role: StakeholderRole = "other"
    company: str = ""
    telegram_username: Optional[str] = None
    telegram_user_id: Optional[str] = None
    notes: str = ""


class ConversationTurn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    role: ConversationRole
    text: str
    channel: str = "chat"
    created_at: datetime


class ResearchSummary(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: ResearchStatus = "not_started"
    source_system: SourceSystem = "unknown"
    summary: str = ""
    doc_urls: list[str] = Field(default_factory=list)
    likely_access_paths: list[str] = Field(default_factory=list)
    known_quirks: list[str] = Field(default_factory=list)
    open_questions: list[str] = Field(default_factory=list)
    note: str = ""
    researched_at: Optional[datetime] = None


class RecommendedPlan(BaseModel):
    model_config = ConfigDict(extra="forbid")

    summary: str = ""
    recommended_access_method: AccessMethod = "unknown"
    steps: list[str] = Field(default_factory=list)
    risks: list[str] = Field(default_factory=list)
    assumptions: list[str] = Field(default_factory=list)
    updated_at: Optional[datetime] = None


class TelegramUiPreferences(BaseModel):
    model_config = ConfigDict(extra="forbid")

    muted: bool = False
    muted_at: Optional[datetime] = None
    muted_by_user_id: Optional[str] = None


class UiPreferences(BaseModel):
    model_config = ConfigDict(extra="forbid")

    telegram: TelegramUiPreferences = Field(default_factory=TelegramUiPreferences)


class OnboardingState(BaseModel):
    """Persisted row payload for `onboarding_runs.document` (plus indexed `state` column)."""

    model_config = ConfigDict(extra="forbid")

    run_id: UUID
    company_id: str
    state: OnboardingPhaseState = "intake"
    source: SourceProfile = Field(default_factory=SourceProfile)
    tables_in_scope: list[str] = Field(default_factory=list)
    artifacts_collected: list[ArtifactCollected] = Field(default_factory=list)
    table_descriptions: list[TableDescription] = Field(default_factory=list)
    column_descriptions: list[ColumnDescription] = Field(default_factory=list)
    mapping_contract: Optional[dict[str, Any]] = None
    approval: Approval = Field(default_factory=Approval)
    blockers: list[Blocker] = Field(default_factory=list)
    project_objective: str = ""
    success_criteria: list[str] = Field(default_factory=list)
    stakeholder_context: list[StakeholderSummary] = Field(default_factory=list)
    constraints: list[str] = Field(default_factory=list)
    open_questions: list[str] = Field(default_factory=list)
    next_question: Optional[str] = None
    confidence_overall: float = 0.0
    research_summary: ResearchSummary = Field(default_factory=ResearchSummary)
    recommended_plan: RecommendedPlan = Field(default_factory=RecommendedPlan)
    ui_preferences: UiPreferences = Field(default_factory=UiPreferences)
    conversation_history: list[ConversationTurn] = Field(default_factory=list)
    phase3: dict[str, Any] = Field(default_factory=dict)
    phase4: dict[str, Any] = Field(default_factory=dict)
    """PR URLs, dry-run summaries, dashboard URL, etc. (extensible)."""

    def apply_patch(self, patch: dict[str, Any]) -> None:
        """Shallow merge top-level keys from patch into this model."""
        data = self.model_dump(mode="json")
        for k, v in patch.items():
            if k in data and isinstance(data[k], dict) and isinstance(v, dict):
                merged = {**data[k], **v}
                data[k] = merged
            else:
                data[k] = v
        updated = OnboardingState.model_validate(data)
        for name in type(self).model_fields:
            setattr(self, name, getattr(updated, name))
