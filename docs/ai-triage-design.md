# AI-Assisted Incident Triage Design

## Purpose

The Incident Triage Assistant demonstrates how an LLM can support an operations team without being trusted to perform autonomous remediation.

The tool is designed for:

- incident categorization
- evidence summarization
- investigation guidance
- stakeholder-update drafting
- Jira-ready incident drafting

It is not designed to execute production changes.

## Input

The API accepts structured incident context including:

- incident identifier
- alert/source
- title
- summary
- logs
- metrics
- SQL evidence
- supporting evidence references

## Processing Pipeline

```text
Untrusted incident evidence
        ↓
Secret and PII redaction
        ↓
LLM structured analysis
        ↓
Schema validation
        ↓
Deterministic operational policy
        ↓
Human-reviewed response
