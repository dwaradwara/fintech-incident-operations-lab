from typing import Dict, List, Literal
from pydantic import BaseModel, Field


Severity = Literal["critical", "high", "medium", "low"]
Category = Literal[
    "payment_authorization",
    "webhook_delivery",
    "financial_reconciliation",
    "provider_latency",
    "unknown",
]


class IncidentInput(BaseModel):
    incident_id: str
    source: str
    title: str
    summary: str

    logs: List[str] = Field(default_factory=list)
    metrics: Dict[str, float] = Field(default_factory=dict)
    sql_evidence: List[str] = Field(default_factory=list)
    references: List[str] = Field(default_factory=list)


class JiraDraft(BaseModel):
    summary: str
    description: str
    priority: str
    component: str


class TriageResult(BaseModel):
    incident_id: str

    category: Category
    severity: Severity
    confidence: float = Field(ge=0.0, le=1.0)

    affected_component: str
    likely_failure_domain: str

    evidence_summary: List[str]
    missing_evidence: List[str]
    recommended_investigation: List[str]

    stakeholder_update: str
    jira_draft: JiraDraft

    engine: str

    human_approval_required: bool = True
    autonomous_remediation_allowed: bool = False

    redactions_applied: int = 0
