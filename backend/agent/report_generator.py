"""Company Process Intelligence Report: multi-section LLM narrative generator.

Produces executive summary, per-process narratives, and operations analysis
(automation + optimization) from computed report metrics. Uses Nova/Bedrock.
"""
import logging

from botocore.exceptions import ClientError

from config import NOVA_MODEL_ID
from agent.bedrock_client import (
    get_bedrock_client,
    check_bedrock_credentials,
    converse_with_retry,
    extract_response_text,
)

logger = logging.getLogger("consularis.agent")


def _metrics_context(metrics: dict) -> str:
    """Build a compact text representation of report metrics for LLM context."""
    parts = []
    parts.append(f"Workspace: {metrics.get('workspace_name', '')}")
    totals = metrics.get("totals", {})
    parts.append(
        f"Totals: annual_cost={totals.get('annual_cost')}, annual_volume={totals.get('annual_volume')}, "
        f"weighted_avg_error_rate={totals.get('weighted_avg_error_rate')}%, "
        f"automation_readiness_score={totals.get('automation_readiness_score')}, "
        f"step_count={totals.get('step_count')}, process_count={totals.get('process_count')}, decision_count={totals.get('decision_count')}"
    )
    for proc in metrics.get("per_process", []):
        parts.append(
            f"Process {proc.get('id')} ({proc.get('name')}): owner={proc.get('owner')}, category={proc.get('category')}, "
            f"criticality={proc.get('criticality')}, step_count={proc.get('step_count')}, "
            f"annual_cost={proc.get('annual_cost')}, annual_volume={proc.get('annual_volume')}, "
            f"avg_error_rate={proc.get('avg_error_rate')}%, automation={proc.get('automation_breakdown')}"
        )
    dist = metrics.get("distributions", {})
    parts.append(f"Automation distribution: {dist.get('automation_potential', {})}")
    parts.append(f"Current state distribution: {dist.get('current_state', {})}")
    top = metrics.get("top_issues", {})
    parts.append(f"Highest error steps: {top.get('highest_error_steps', [])[:5]}")
    parts.append(f"Highest cost steps: {top.get('highest_cost_steps', [])[:5]}")
    parts.append(f"Manual high-volume steps: {top.get('manual_high_volume_steps', [])[:5]}")
    return "\n".join(parts)


EXECUTIVE_SUMMARY_PROMPT = """You are the Consularis Report Writer. You produce the Executive Summary for a Company Process Intelligence Report.

You will receive the workspace name and key metrics. Output markdown only. Do NOT start with a heading like "Executive Summary" or "Overview"—the report already has a section title.

Write in clear, full sentences. Use bullet points to structure the content so it is easy to scan; each bullet should be a complete sentence (not a fragment).

Structure your reply as follows:

1. **Overview**: One sentence: [Workspace name] has [X] processes and [Y] steps. Use the exact workspace name and numbers from the metrics.

2. **Key findings**: A short bullet list (3–5 bullets). Each bullet is one full sentence that includes concrete numbers (e.g. total annual cost, total volume, weighted error rate, automation readiness score). Example: "Total annual cost across all processes is €3,739,470 with 576,022 transactions per year."

3. **Top recommendations**: A short bullet list (2–3 bullets). Each bullet is one full sentence with a tailored recommendation. Use actual process names (e.g. Prescription, Selection and Acquisition) and step names where relevant. Example: "We recommend automating 'Acquire Medication' in Selection and Acquisition using EDI, which would save €X per year." Do not give generic advice; name the specific process and step."""

# Process narratives disabled: user requested less prose; landscape cards are enough.
PROCESS_NARRATIVES_PROMPT = ""

OPERATIONS_ANALYSIS_PROMPT = """You are the Consularis Operations Analyst. You produce a short Automation opportunities section for a Company Process Intelligence Report.

You will receive metrics. Focus ONLY on steps with **high** automation potential (ignore medium/low for this section).

Output markdown. Do NOT use a main heading like "Operations Analysis"—the report has a section title. Use full sentences; structure with bullet points so the content is clear and scannable. Each bullet should be a complete sentence.

Write:

1. **High-potential steps**: A short bullet list. Each bullet is one full sentence that names a step and its process (e.g. "Acquire Medication in Selection and Acquisition") and briefly explains why it is automatable, including cost or volume where relevant. Use only the steps that appear in the data with high automation potential.

2. **Proposed automated workflow**: One short paragraph (2–4 sentences) describing a concrete workflow for this company. Pick 1–3 high-potential steps that logically chain. For example: "For [workspace name], we recommend automating [step A] and [step B] using [specific tool, e.g. n8n + EDI]. This would reduce [cost/time/errors] by [concrete effect]." Use the actual workspace name and step/process names from the data.

3. One short sentence: They can book an appointment with Consularis (email on this page) to implement this.

Be concise. One workflow only."""


def _llm_call(session_id: str, system_text: str, user_text: str, section_name: str) -> str:
    """Single LLM call; returns extracted text or error message."""
    client = get_bedrock_client()
    try:
        response = converse_with_retry(
            client,
            modelId=NOVA_MODEL_ID,
            system=[{"text": system_text}],
            messages=[{"role": "user", "content": [{"text": user_text}]}],
            inferenceConfig={"maxTokens": 2048, "temperature": 0.4},
        )
    except ClientError as e:
        logger.exception("[REPORT] %s session_id=%s Bedrock error: %s", section_name, session_id, e)
        return f"*The {section_name} section could not be generated (AWS error). Please try again.*"
    except Exception as e:
        logger.exception("[REPORT] %s session_id=%s error: %s", section_name, session_id, e)
        return f"*The {section_name} section could not be generated. Please try again.*"
    text = extract_response_text(response)
    return text or f"*No content returned for {section_name}.*"


def run_report_narratives(session_id: str, metrics: dict) -> dict[str, str]:
    """Generate LLM narratives for executive summary, process narratives, and operations analysis.
    Returns dict with keys: executive_summary, process_narratives, operations_analysis."""
    cred_err = check_bedrock_credentials()
    if cred_err:
        return {
            "executive_summary": f"*Report narratives are not available: {cred_err}*",
            "process_narratives": "",
            "operations_analysis": f"*Report narratives are not available: {cred_err}*",
        }

    context = _metrics_context(metrics)

    executive_summary = _llm_call(
        session_id,
        EXECUTIVE_SUMMARY_PROMPT + "\n\n--- Metrics ---\n\n" + context,
        "Generate the Executive Summary as described. Do not include any heading line.",
        "Executive Summary",
    )

    # Process narratives: disabled (user requested less prose; landscape cards suffice)
    process_narratives = ""

    # Operations: only high-potential steps for context
    high_steps = [
        s for s in metrics.get("per_step", [])
        if (s.get("automation_potential") or "").lower() == "high"
    ]
    process_names = {p["id"]: p.get("name", p["id"]) for p in metrics.get("per_process", [])}
    high_steps_with_process_names = [
        f"{s.get('id')} {s.get('name')} (process: {process_names.get(s.get('process_id'), s.get('process_id'))}): "
        f"annual_cost={s.get('annual_cost')}, annual_volume={s.get('annual_volume')}"
        for s in high_steps[:30]
    ]
    context_ops = context + "\n\nHigh automation-potential steps only:\n" + "\n".join(high_steps_with_process_names or ["(none)"])

    operations_analysis = _llm_call(
        session_id,
        OPERATIONS_ANALYSIS_PROMPT + "\n\n--- Metrics ---\n\n" + context_ops,
        "Generate the Automation opportunities section: high-potential steps list and one tailored workflow. No heading.",
        "Operations analysis",
    )

    return {
        "executive_summary": executive_summary,
        "process_narratives": process_narratives,
        "operations_analysis": operations_analysis,
    }
