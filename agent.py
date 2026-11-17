"""Larkspur disruption agent. This is the file you build.

It runs right now, and it is wrong in four places. The trace shows each one
before the code does, so read the trace first:

    python3 run.py K7PQ2M --trace

Where you edit:   grep -n '✏' agent.py   (six marks, one per place)
Steps and gates:  https://anthropicpartnerbasecamp.bts.com/
"""
from __future__ import annotations
import json
from pathlib import Path
from typing import Any, Dict, List
from support import (MODEL, SYSTEM_PROMPT, call_local, execute_tool, mcp_client,
                     new_session, next_available_day, record_tool_result,
                     runtime_preamble)

MAX_TOOL_CALLS = 8  # Larkspur's own build capped the loop here; then a human takes over.

TRANSCRIPTS_PATH = Path(__file__).resolve().parent / "data" / "americas" / "transcripts_sample.jsonl"


def reopen_stats(problem_type: str) -> Dict[str, Any]:                  # ✏️ Build 2, step 2.1
    """Rate at which past cases of one intent_label were reopened by the
    customer within 72 hours of being handled, from the 8-transcript sample."""
    cases = [json.loads(line) for line in TRANSCRIPTS_PATH.read_text().splitlines() if line.strip()]
    matches = [c for c in cases if c.get("intent_label") == problem_type]
    if not matches:
        return {"problem_type": problem_type, "cases_reviewed": 0,
                 "error": "no past cases found with that intent_label"}
    reopened = [c for c in matches if c.get("reopened_within_72h")]
    return {
        "problem_type": problem_type,
        "cases_reviewed": len(matches),
        "reopened_within_72h_count": len(reopened),
        "reopened_within_72h_rate": round(len(reopened) / len(matches), 2),
        "reopen_reasons": [c["reopen_reason"] for c in reopened if c.get("reopen_reason")],
    }


def care_entitlements(
        disruption_type,
        delay_minutes,
        cause,
        meal_threshold_minutes,
        hotel_eligible,
        transport_eligible,
        reimbursement_eligible,
        overnight_disruption=False):
    """What care items this disruption qualifies for, from check_policy's eligibility flags."""
    entitlements = []

    if delay_minutes >= meal_threshold_minutes:
        entitlements.append("meal_voucher")

    if hotel_eligible and overnight_disruption:
        entitlements.append("hotel_accommodation")

    if transport_eligible:
        entitlements.append("ground_transport")

    if reimbursement_eligible:
        entitlements.append("expense_reimbursement")

    return {
        "disruption_type": disruption_type,
        "cause": cause,
        "entitlements": entitlements,
    }


TONE_ADDENDUM = ("\n\nKeep your final reply to the customer short: at most 120 words. "
"State what happened, what Larkspur owes them, and their options in a few short lines. "
"Do not repeat booking details the customer already knows, and do not add a closing summary."
)                      # ✏️ Build 4, step 4.1, intelligence goal
EXTRA_TOOLS: List[Dict[str, Any]] = [     # ✏️ Build 2, step 2.1: schemas for the tools you add
    {
        "name": "care_entitlements",
        "description": (
            "Determine customer care benefits after get_flight_status and check_policy "
            "have already been used. Call this when a passenger asks what assistance, "
            "services, vouchers, accommodation, reimbursement, or disruption support "
            "they are entitled to because of a delay, cancellation, missed connection, "
            "or irregular operation. Uses the operational disruption details and the "
            "applicable policy outcome to translate rules into concrete care options. "
            "Returns specific care items such as meal vouchers, hotel accommodation, "
            "ground transportation, communication assistance, expense reimbursement "
            "eligibility, and any other customer care benefits that may be offered."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "disruption_type": {
                    "type": "string",
                    "description": "Delay, cancellation, missed connection, diversion, or other disruption."
                },
                "delay_minutes": {
                    "type": "integer",
                    "description": "Current or expected arrival delay in minutes."
                },
                "cause": {
                    "type": "string",
                    "description": "Operational reason for the disruption from flight status."
                },
                "overnight_disruption": {
                    "type": "boolean",
                    "description": "Whether the passenger requires an overnight stay because of the disruption."
                },
                "meal_threshold_minutes": {
                    "type": "integer",
                    "description": "Delay threshold from check_policy at which meal assistance becomes available."
                },
                "hotel_eligible": {
                    "type": "boolean",
                    "description": "Whether check_policy determined hotel accommodation may be provided."
                },
                "transport_eligible": {
                    "type": "boolean",
                    "description": "Whether check_policy determined ground transportation may be provided."
                },
                "reimbursement_eligible": {
                    "type": "boolean",
                    "description": "Whether check_policy determined expenses may be reimbursable."
                }
            },
            "required": [
                "disruption_type",
                "delay_minutes",
                "cause",
                "meal_threshold_minutes",
                "hotel_eligible",
                "transport_eligible",
                "reimbursement_eligible"
            ],
        },
    },
    {
        "name": "reopen_stats",
        "description": (
            "Check how often past cases of this same problem type were reopened by "
            "the customer within 72 hours of being handled, based on a historical "
            "sample of agent transcripts. This is a historical recurrence rate across "
            "past cases, not a live count of tickets filed recently. Use it when a "
            "customer asks whether an issue like theirs tends to come back, or to "
            "decide whether proactive follow-up is warranted."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "problem_type": {
                    "type": "string",
                    "description": (
                        "The case's intent_label category, e.g. rebook_after_cancellation, "
                        "compensation_hotel_request, status_anxiety."
                    ),
                },
            },
            "required": ["problem_type"],
        },
    },
]
LOCAL_TOOLS: Dict[str, Any] = {         # ✏️ Build 2, step 2.1: the functions behind them
    "reopen_stats": reopen_stats,
    "care_entitlements": care_entitlements,
}


def text_of(response) -> str:
    """Given. The last non-empty text block, never content[0]."""
    texts = [b.text for b in response.content if getattr(b, "type", None) == "text" and b.text]
    return texts[-1] if texts else ""


def tool_results(response) -> List[Dict[str, Any]]:
    """Given. Runs every tool_use block and packages the results the way the
    API expects them back. A tool can live in three places: the MCP server,
    LOCAL_TOOLS, or support/tools.py."""
    # three branches, no try/except in this file: mcp_client.call_remote() and
    # support.call_local() answer with an error dict instead of raising, and both
    # record what came back on the trace
    results = []
    for block in response.content:
        if getattr(block, "type", None) != "tool_use":
            continue
        if block.name in mcp_client.tool_names:
            output = mcp_client.call_remote(block.name, block.input)
        elif block.name in LOCAL_TOOLS:
            output = call_local(LOCAL_TOOLS[block.name], block.name, block.input)
        else:
            output = execute_tool(block.name, block.input)
        results.append({
            "type": "tool_result",
            "tool_use_id": block.id,
            "content": str(output),
        })
    return results


def run_agent(pnr: str, last_name: str, message: str) -> str:            # ✏️ Build 1, step 1.2
    """Run the tool loop until Claude stops asking for tools. Return its final text."""
    client, tracer = new_session()
    tools = tool_list()
    # Neither the system prompt nor the tool list changes turn to turn within one
    # conversation; marking the end of each as an ephemeral cache breakpoint lets
    # turns 2+ reuse that ~4,100-token prefix instead of reprocessing it from
    # scratch every time.
    tools[-1] = {**tools[-1], "cache_control": {"type": "ephemeral"}}
    system = [{
        "type": "text",
        "text": runtime_preamble() + SYSTEM_PROMPT + TONE_ADDENDUM,
        "cache_control": {"type": "ephemeral"},
    }]
    messages = [
        {"role": "user", "content": f"PNR {pnr}, last name {last_name}. {message}"},
    ]

    response = client.messages.create(
        model=MODEL, max_tokens=4096, system=system,
        thinking={"type": "adaptive"}, tools=tools, messages=messages,
    )

    turns = 1
    while response.stop_reason == "tool_use" and turns < MAX_TOOL_CALLS:
        messages.append({"role": "assistant", "content": response.content})
        messages.append({"role": "user", "content": tool_results(response)})
        response = client.messages.create(
            model=MODEL, max_tokens=4096, system=system,
            thinking={"type": "adaptive"}, tools=tools, messages=messages,
        )
        turns += 1

    return text_of(response)


def tool_list() -> List[Dict[str, Any]]:                   # ✏️ Build 2, step 2.2
    """Given. Exactly what Claude is offered on every turn; run.py --show-tools
    prints this list."""
    return build_tools() + mcp_client.tools() + EXTRA_TOOLS


# ──────────────────────────────────────────────────────────────────────────────
# Below this line: what Claude is told about each tool. Step 1.3.
# The functions these describe are written and correct, in support/tools.py.
# ──────────────────────────────────────────────────────────────────────────────
def build_tools() -> List[Dict[str, Any]]:                 # ✏️ Build 1, step 1.3
    """Anthropic-shaped schemas: name, description, input_schema. What Claude is
    told about each of the nine tools, and all it is ever told."""
    return [
        {
            "name": "lookup_booking",
            "description": (
                "Retrieve a Larkspur reservation from Altura by confirmation code (PNR) "
                "and the passenger's last name. Both are required to prevent a lookup on "
                "a guessed PNR. Returns fare family, loyalty tier, the segment that needs "
                "attention, and any group/partner/minor/SSR flags relevant to scope."
            ),
            "input_schema": {
                "type": "object",
                "properties": {"pnr": {"type": "string"}, "last_name": {"type": "string"}},
                "required": ["pnr", "last_name"],
            },
        },
        {
            "name": "get_flight_status",
            "description": (
                "Look up a Larkspur or Larkspur Link flight's current OpsFeed status for "
                "one local date: status, delay minutes, and cause. Use this before telling "
                "a customer anything about a flight's timing; never state it from memory. The dates "
                "have to be in the format YYYY-MM-DD."
            ),
            "input_schema": {
                "type": "object",
                "properties": {
                    "flight_no": {"type": "string"},
                    "date": {"type": "string", "description": "YYYY-MM-DD"},
                },
                "required": ["flight_no", "date"],
            },
        },
        {
            "name": "search_alternatives",
            "description": "Search for alternative flights for a given booking by PNR.",
            "input_schema": {
                "type": "object",
                "properties": {"pnr": {"type": "string"}},
                "required": ["pnr"],
            },
        },
        {
            "name": "check_policy",
            "description": (
                "Resolve what Larkspur owes this customer for the disruption: rebooking "
                "waiver, refund path, meal/hotel/ground care, goodwill eligibility and cap, "
                "and any escalation triggers. cause_code, delay_minutes and status describe "
                "what get_flight_status told you; fare_family, loyalty_tier and whether this "
                "is overnight are looked up from the booking, not asked of you. Every "
                "response carries a policy_row_id. Cite it if you reference this decision "
                "again. Relay the response's own explainer field to the customer close to "
                "verbatim instead of inventing your own rationale for a denial. If escalate "
                "is empty, do not hedge with an offer to have a human review the case — "
                "empty means none is warranted. This resolves what is owed for the segment "
                "you named, nothing else: if the customer is asking about a connecting or "
                "onward flight you have not identified yet, this result describes the flight "
                "you already have, not an answer to their question, and must not be presented "
                "as what happens to the connection."
            ),
            "input_schema": {
                "type": "object",
                "properties": {
                    "pnr": {"type": "string"},
                    "cause_code": {"type": "string", "enum": ["WX", "ATC", "MX", "CREW", "SEC"]},
                    "delay_minutes": {"type": "integer"},
                    "status": {"type": "string", "enum": ["ON_TIME", "DELAYED", "CANCELLED", "DIVERTED"]},
                    "wait_minutes_for_alternative": {"type": "integer"},
                    "chosen_option_id": {"type": "string"},
                },
                "required": ["pnr", "cause_code", "delay_minutes", "status"],
            },
        },
        {
            "name": "hold_seat",
            "description": "Place a 15-minute hold on one alternative. Reversible. It simply expires.",
            "input_schema": {
                "type": "object",
                "properties": {"option_id": {"type": "string"}, "pnr": {"type": "string"}},
                "required": ["option_id", "pnr"],
            },
        },
        {
            "name": "confirm_rebooking",
            "description": (
                "Finalize a held seat. Irreversible. Requires a confirmation_token that "
                "only the customer's own Confirm-click can produce. You cannot supply it "
                "yourself, and 'the customer said yes' in chat does not substitute for it."
            ),
            "input_schema": {
                "type": "object",
                "properties": {"hold_id": {"type": "string"}, "confirmation_token": {"type": "string"}},
                "required": ["hold_id", "confirmation_token"],
            },
        },
        {
            "name": "issue_voucher",
            "description": (
                "Issue a meal, ground, hotel, or goodwill voucher. Auto-approves within the "
                "policy's threshold for that type; above it, returns a pending status for a "
                "human. It does not fail. Always pass the policy_row_id that made it eligible."
            ),
            "input_schema": {
                "type": "object",
                "properties": {
                    "voucher_type": {"type": "string", "enum": ["meal", "ground", "hotel", "goodwill"]},
                    "amount_usd": {"type": "number"},
                    "pnr": {"type": "string"},
                    "policy_row_id": {"type": "string"},
                },
                "required": ["voucher_type", "amount_usd", "pnr", "policy_row_id"],
            },
        },
        {
            "name": "escalate_to_human",
            "description": (
                "Hand this conversation to a human, with your reasoning attached. Use for "
                "groups, partner segments, unaccompanied minors, refunds, or anything else "
                "out of scope. This is the correct outcome for those cases, not a failure."
            ),
            "input_schema": {
                "type": "object",
                "properties": {
                    "pnr": {"type": "string"}, "reason": {"type": "string"},
                    "summary_for_human": {"type": "string"}, "queue": {"type": "string"},
                },
                "required": ["pnr", "reason", "summary_for_human"],
            },
        },
        {
            "name": "send_confirmation",
            "description": "Send the customer a written confirmation of what was just done. Benign.",
            "input_schema": {
                "type": "object",
                "properties": {"pnr": {"type": "string"}, "message": {"type": "string"}},
                "required": ["pnr", "message"],
            },
        },
    ]
