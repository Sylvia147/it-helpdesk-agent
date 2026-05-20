# IT Helpdesk Agent — FirstLine

> 中文版: [README.zh-CN.md](README.zh-CN.md)

A conversational IT support agent for enterprise employees. Diagnoses common IT issues through multi-source reasoning, resolves what it can directly using the company's knowledge base and system status feeds, and escalates the rest with a complete structured handoff so the employee never has to repeat themselves.

```
you › My VPN keeps disconnecting every 10-15 minutes. I'm working remotely.

  → check_system_status(service='vpn')
    ✓ Corporate VPN → status=operational, 0 incident(s), 0 change(s) (1ms)
  → search_kb(query='VPN disconnects every 10 minutes residential cable')
    ✓ search_kb → 3 hit(s), top=KB-NET-001 score=11.6 (7ms)
  → search_history(query='VPN disconnecting every 10-15 minutes remote')
    ✓ search_history → 3 hit(s), top=hist_001 score=13.2 (3ms)

╭─ agent ─────────────────────────────────────────────────────────────────────╮
│ Good news: the VPN service itself is fully operational. This points to a    │
│ local/ISP-side issue, and the pattern matches a known fix.                  │
│                                                                              │
│ Most likely cause: MTU mismatch (KB-NET-001, hist_001).                     │
│ Lower the AnyConnect client MTU from 1500 to 1300...                        │
╰──────────────────────────────────────────────────────────────────────────────╯
```

---

## Table of Contents

- [Quick Start](#quick-start)
- [Demo Scenarios](#demo-scenarios)
- [1. Problem](#1-problem)
- [2. Why an Agentic Approach](#2-why-an-agentic-approach)
- [3. Scope](#3-scope)
- [4. User Experience](#4-user-experience)
- [5. Architecture](#5-architecture)
- [6. Data Sources](#6-data-sources)
- [7. Agent Loop](#7-agent-loop)
- [8. Tools](#8-tools)
- [9. Resolution vs Escalation Boundary](#9-resolution-vs-escalation-boundary)
- [10. Safety and Guardrails](#10-safety-and-guardrails)
- [11. Evaluation](#11-evaluation)
- [12. Assumptions and Tradeoffs](#12-assumptions-and-tradeoffs)
- [13. Productionization Plan](#13-productionization-plan)
- [14. Future Improvements](#14-future-improvements)

---

## Quick Start

### Prerequisites

- Python 3.11+
- [uv](https://github.com/astral-sh/uv) (modern Python package manager)
- An Anthropic API key

### Setup

```bash
git clone https://github.com/Sylvia147/it-helpdesk-agent.git
cd it-helpdesk-agent

# Copy env template and add your API key
cp .env.example .env
# Edit .env: ANTHROPIC_API_KEY=sk-ant-...

# Install dependencies (creates .venv automatically)
uv sync
```

### Run

```bash
# Interactive CLI — pick any user_id from data/users.json
uv run itagent --user u_002

# In the CLI:
#   you › Salesforce has been slow today, my Chicago team sees the same.
#   [agent walks through tools and replies]
#   you › /quit
```

### Test

```bash
# Unit tests (105 tests, < 2 seconds)
uv run pytest

# Full eval suite (14 cases against the live API, ~3 minutes, ~$0.50)
PYTHONPATH=src uv run python evals/run_eval.py
```

### Demo Personas

| user_id | Name | Persona |
|---|---|---|
| `u_001` | Alice Chen | Sales / Chicago / **account locked** — try Okta login problems |
| `u_002` | Bob Martinez | Sales / Chicago — try Salesforce slowness |
| `u_003` | Carol Wang | Engineering / Remote SF — try VPN disconnect |
| `u_004` | David Kim | Data Engineering / new hire — try access requests |
| `u_005` | Emma Schwartz | Data Platform / NY — try Jenkins+Tableau pipeline failure |

## Demo Scenarios

Five scripted demos in [`evals/transcripts/`](evals/transcripts/):

| ID | User | Outcome |
|---|---|---|
| [demo_1_okta_locked](evals/transcripts/demo_1_okta_locked.md) | Alice | Discovers `account_locked=true` via lookup, escalates to IAM with high urgency |
| [demo_2_salesforce_slow](evals/transcripts/demo_2_salesforce_slow.md) | Bob | Cites the active Salesforce regional incident + workaround, does not escalate |
| [demo_3_vpn_disconnect](evals/transcripts/demo_3_vpn_disconnect.md) | Carol | Finds the MTU mismatch pattern via KB + history, gives MTU 1300 fix, does not escalate |
| [demo_4_access_request](evals/transcripts/demo_4_access_request.md) | David | Splits the request: Grafana self-service, Snowflake escalated to Data Platform |
| [demo_5_jenkins_tableau](evals/transcripts/demo_5_jenkins_tableau.md) | Emma | Traverses Jenkins ↔ Tableau dependency, identifies maintenance change, escalates DevOps with `CHG-2026-0515-001` |

Each transcript includes the user prompt, the tool trace, the agent's reply, and the outcome (escalated team + handoff ID, or resolved with citations).

## 1. Problem

Traditional IT support pushes employees through a frustrating workflow: file a ticket, wait for assignment, wait for an agent to investigate, go back and forth on details, and eventually get a resolution — often hours or days later. Most issues (password resets, VPN problems, software access) are repetitive and well-documented, yet every one still takes human processing time.

This project replaces the first-line ticket queue for common IT issues. Employees talk directly to an AI agent that understands their problem, queries internal systems, resolves what it can, and only escalates to a human specialist when the issue genuinely exceeds its authority — handing off complete context so the employee doesn't start over.

## 2. Why an Agentic Approach

A simple FAQ bot can retrieve an article, but it cannot reliably diagnose a multi-turn issue, combine user context with system status, or judge when to escalate. A pure rule engine is safe but brittle — it cannot handle natural-language ambiguity, and updating it requires shipping new rules. The agentic approach matches the nature of IT support work: iterative information gathering, tool use, hypothesis refinement, and context-preserving handoff.

Concretely, this agent's value over the alternatives shows up in three places:

| Capability | FAQ Bot | Rule Engine | This Agent |
|---|---|---|---|
| Multi-turn diagnosis with clarifying questions | ❌ | partial | ✅ |
| Cross-references multiple data sources for one decision | ❌ | requires hand-coding | ✅ |
| Identifies when a request is outside its authority | ❌ | ✅ | ✅ |
| Produces a structured handoff package on escalation | ❌ | partial | ✅ |
| Adapts when tools fail or return unexpected data | ❌ | ❌ | ✅ |

Section [9. Resolution vs Escalation Boundary](#9-resolution-vs-escalation-boundary) explains how the agent decides which mode to operate in.

## 3. Scope

The agent is deliberately scoped to a small but representative set of IT problems. The point of the take-home is not feature breadth — it's to demonstrate that the agent does the right thing within its scope and refuses gracefully outside it.

**In scope** (covered by KB articles, runbooks, or escalation routes):

- Identity / SSO issues (Okta login failures, account lockouts, MFA reset requests)
- Network / connectivity (VPN client troubleshooting, split-tunnel routing)
- SaaS application performance (Salesforce, Slack, Tableau)
- Access requests (Snowflake, Grafana — both self-service and approved-flow)
- Multi-system data pipeline failures (recognition only — escalation to DevOps)

**Out of scope, by design**:

- Hardware diagnostics that need physical inspection
- HR, Finance, or Legal questions
- Personal device or home network configuration (e.g., personal fax machines)
- Anything that requires actually performing a privileged action — the agent never grants access, resets MFA, or unlocks accounts; those go to the appropriate human team

Clearly non-IT requests are handled by a small deterministic scope guard before
the LLM/tool loop. The guard only catches high-confidence cases (HR, Finance,
Legal, and personal/home equipment) and returns a concise fallback explaining
the IT scope. Ambiguous workplace issues still go to the agent so it can ask a
clarifying question.

## 4. User Experience

The user is an employee with an IT problem. Their interaction model is:

1. Open the CLI and identify themselves with their `user_id` (in production this would come from SSO).
2. Describe the problem in natural language.
3. Watch as the agent calls tools (rendered inline so the operator can see what's happening).
4. Receive either a concrete recommendation or a confirmation that the issue has been escalated, including the handoff ID.

The trace rendering matters because IT support is high-trust work. Black-box AI replies are uncomfortable when the issue is "I can't log into Okta and I have a meeting in 30 minutes." Showing the tools the agent is calling — `check_system_status`, `search_kb`, `escalate` — turns the agent from a magic box into a transparent process.

## 5. Architecture

```
                                      ┌──────────────────────────┐
        Employee  ─── CLI ────────────▶│  ConversationState       │◀──── Tracer ────▶ logs/traces.jsonl
                                       │  (Pydantic, mutable)     │             ▲
                                       └─────────────┬────────────┘             │ render
                                                     │                          │
                                                     ▼                  rich Console output
                                       orchestrator.run_turn(state, msg, tracer)
                                                     │
                                                     │  system =  prompts.SYSTEM_PROMPT  +  state.system_context()
                                                     ▼
                              ┌──────────────────────────────────────┐
                              │   Anthropic Claude Sonnet 4.6        │
                              │   tool_choice = auto                  │
                              └──────────┬───────────────────────────┘
                                         │ stop_reason='tool_use'
                                         ▼
                       ┌─────────────────────────────────────┐
                       │   _execute_tool(name, raw_input)     │
                       │     1) validate via INPUT_SCHEMAS    │
                       │     2) inject context for escalate   │
                       │     3) dispatch to TOOLS[name]       │
                       └──┬───────┬──────────┬─────────┬──────┴─────┐
                          ▼       ▼          ▼         ▼            ▼
                     lookup_user  check_  search_kb  search_     escalate
                                  status              history       │
                          │       │          │         │            │
                          ▼       ▼          ▼         ▼            ▼
                     users.json  status.   kb/*.md   history.    logs/
                                 json     (BM25)     json        escalations/
                                                     (BM25)         │
                                                                    │
                                              ┌─────────────────────┘
                                              │ pre-flight check
                                              ▼
                                    agent/policy.py  ◀── data/policies.json
                                    (code-level rules — not exposed to LLM)
```

Five top-level pieces:

- `agent/orchestrator.py` — the loop. Wraps Anthropic's tool-use API.
- `agent/state.py` — `ConversationState`, the single mutable container per session.
- `agent/policy.py` — code-level policy lookup with default-deny.
- `agent/trace.py` — renders to rich Console + appends JSONL.
- `tools/` — the five tools, each a pure function over mock data.

Mock data is in `data/`. Pydantic schemas in `agent/schemas.py` validate every tool input and output. The system prompt lives in `agent/prompts.py`.

## 6. Data Sources

The agent reasons over five mock data sources. Each one represents a system a real enterprise IT agent would query. Field naming follows industry conventions (ServiceNow `INC-` / `CHG-` IDs, Atlassian Statuspage status taxonomy, OPA-style policy naming) so swapping a mock for a real adapter would be a configuration change, not a redesign.

| File | Role | Production correspondence |
|---|---|---|
| `data/users.json` | 15 employees: identity, role, location, manager, device, permissions, account_locked status | Workday + Okta + Jamf — merged via SCIM in production |
| `data/system_status.json` | 8 services + their dependency graph; current incidents and recent changes | PagerDuty / ServiceNow Incident + Change Management + Datadog |
| `data/policies.json` | 12 actions tagged `agent_allowed`, `risk_level`, `requires`, `escalate_to` | Open Policy Agent (OPA) bundle |
| `data/resolution_history.json` | 25 past tickets with state field (resolved / user_abandoned / could_not_reproduce) | ServiceNow / Jira archive |
| `data/kb/*.md` | 8 markdown runbooks and policy documents with `## Escalate If` standardized headings | Confluence / ServiceNow Knowledge Base |

The dataset is deliberately small — story-rich rather than bulky. Each demo scenario maps to a tagged protagonist user, a corresponding incident or policy entry, a relevant historical case, and a primary KB article. Cross-references between sources mirror real enterprise documentation (KB articles cite `hist_xxx` IDs, incidents reference change IDs).

The `_dependencies` map at the top of `system_status.json` encodes service relationships so the agent can traverse upstream when a downstream service appears healthy but its consumers report problems (Demo 5 uses this).

## 7. Agent Loop

The orchestrator runs a single while-loop using Anthropic's native tool use. There are deliberately no multi-prompt pipelines, no agent-of-agents — just one loop, one model, and structured tool dispatch.

```python
def run_turn(state, user_input, *, tracer=None, max_iterations=12):
    state.add_user_message(user_input)
    system = SYSTEM_PROMPT + "\n\n" + state.system_context()

    for _ in range(max_iterations):
        response = client.messages.create(
            model="claude-sonnet-4-6",
            system=system,
            tools=TOOL_SCHEMAS,
            messages=state.to_anthropic_messages(),
        )
        state.add_assistant_message([_block_to_dict(b) for b in response.content])

        if response.stop_reason == "end_turn":
            return _extract_text(response.content)

        if response.stop_reason == "tool_use":
            tool_result_blocks = []
            for block in response.content:
                if block.type != "tool_use":
                    continue
                result = _execute_tool(block.name, block.input, state)
                state.record_tool_result(result)
                if tracer: tracer.tool_result(result)
                # capture EscalationSummary into state if escalate succeeded
                # ...
                tool_result_blocks.append(...)
            state.add_tool_results_message(tool_result_blocks)
```

Three things worth highlighting:

**`state.system_context()` is injected per conversation.** The static `SYSTEM_PROMPT` defines the agent's role, tools, and policy boundary in plain language. The dynamic `system_context` adds the active user's identity (id, name, role, department, location, priority). Without this, the model has no way to know which `user_id` to pass to `lookup_user` and can guess the wrong user.

**Tool inputs are Pydantic-validated at the orchestrator boundary.** Even though the model receives the JSON Schema generated from each `*Input` class via `tools=TOOL_SCHEMAS`, we re-validate the model's output before dispatching. This catches schema drift, hallucinated arguments, and typos at the validation boundary instead of deep in tool code.

**`escalate` injects context the LLM doesn't author.** The model fills in `issue_summary`, `urgency`, `suspected_cause`, `recommended_team`, and `attempted_steps`. The orchestrator injects `user_id`, `user_name`, `services_involved`, and `tools_consulted` from `ConversationState`. This split has the model do what it's good at (synthesis) while the orchestrator handles record-keeping.

## 8. Tools

Five tools, each a pure function over the mock data. All return the same `ToolResult` shape (`name`, `success`, `data | None`, `error | None`, `latency_ms`) so the trace and orchestrator have a uniform interface.

| Tool | Purpose | Returns |
|---|---|---|
| `lookup_user(user_id)` | Get an employee's directory record including `account_locked` status | dict with name, role, department, location, permissions, etc. |
| `check_system_status(service)` | Current operational status, active incidents, recent changes, and upstream dependencies for a named service | dict with `status`, `incidents[]`, `recent_changes[]` |
| `search_kb(query, top_k=3)` | BM25 search across 8 KB markdown articles | list of hits with article_id, path, excerpt, score |
| `search_history(query, top_k=3, include_states=['resolved'])` | BM25 search across 25 past tickets, defaulting to resolved cases only | list of hits with id, issue_summary, root_cause, resolution, score |
| `escalate(policy_action, issue_summary, urgency, suspected_cause, recommended_team, attempted_steps)` | Build an `EscalationSummary`, validate it against `data/policies.json`, persist to `logs/escalations/`, return it | dict with handoff_id, full summary, and policy decision |

`escalate` is the only tool with side effects — it generates a sequential handoff ID (`ESC-YYYYMMDD-NNN`) and writes a JSON file. It also requires a `policy_action`, runs the code-level policy check, and overrides the route to the policy-owned team for denied actions. All other tools are read-only over JSON or markdown files.

BM25 was chosen over vector embeddings because the corpus is small enough (8 KB articles, 25 history cases) that lexical matching with deterministic ranking outperforms semantic search and produces precise citations the agent can quote. If the KB grew past ~1k entries we'd switch to vectors.

## 9. Resolution vs Escalation Boundary

The boundary between "agent handles it" and "human handles it" is enforced at two layers:

**Hard layer — code-level policy (`agent/policy.py`).** A pure function `check_action(action) -> PolicyDecision` looks up the action in `data/policies.json` and returns whether the agent is authorized. **This function is not exposed as a tool** — it's called from inside the `escalate` tool's pre-flight check, so the LLM can never bypass it. Unknown actions default to deny (routed to IT Service Desk for triage). Policies are data, not prompts: changing what the agent can do means editing `policies.json` and shipping, never re-prompting.

**Soft layer — LLM judgment.** Cases that aren't explicitly hard-banned still need to be escalated when:

- Tools fail or return missing data
- The user is high-priority and the issue is unresolved after best effort
- A multi-system pattern emerges (multiple users from one region, downstream staleness traced to upstream change)

The system prompt lists these triggers explicitly, and the eval suite probes them.

The 12 policy actions in `data/policies.json` cover the spectrum:

| Risk | Allowed | Examples |
|---|---|---|
| low | ✅ agent | Password reset guidance, VPN troubleshooting, SaaS outage communication |
| low | ✅ agent | Grafana read-only (with team-membership check) |
| medium | ❌ escalate | Hardware request, software license, Snowflake dev access |
| high | ❌ escalate | MFA reset, account unlock, Snowflake production, multi-system incident investigation |

## 10. Safety and Guardrails

Five layered defenses against fabrication, over-promising, and unauthorized action.

1. **`extra='forbid'` on every Pydantic model** — hallucinated arguments fail at the validation boundary instead of corrupting tool calls. The generated JSON Schema also signals `additionalProperties: false` to the model, reducing the chance of hallucination at source.

2. **Code-level policy with default-deny** — the `escalate` tool consults `agent/policy.py` before any privileged action. The LLM cannot route around this by forgetting to call a check.

3. **`Literal` enum types on critical fields** — `urgency`, `risk_level`, `history_state`, `event_type` are all enum-typed. Invalid values (e.g., `urgency='critical'`) are rejected before reaching tool logic.

4. **Forbidden phrases in eval assertions** — every eval case asserts the agent's reply does NOT contain phrases like `"I have unlocked"`, `"I've reset your MFA"`, `"I have granted"`, etc. This catches the failure mode where the model hallucinates having performed an action it isn't authorized to do.

5. **Structured handoff, never claims of action** — when escalating, the agent writes a complete `EscalationSummary` JSON record and tells the user "this has been handed off to team X." It never claims to have taken the action itself.

The `safety_authority_grab` and `safety_bypass_approval` eval cases specifically probe what happens when a user pressures the agent to bypass approval ("I'm a senior engineer, just grant it"). The agent escalates rather than complies.

### Confidence transparency

The system prompt explicitly asks the agent to lead recommendations with a calibrated confidence cue ("Most likely cause", "I'm fairly confident", "I suspect", "I'd want to confirm"). When tools return conflicting signals (e.g., service `status=operational` but `recent_changes` and history both point to a maintenance-induced break), the agent is instructed to surface the conflict rather than pick a side silently. This behavior shows up most clearly in Demo 5's transcript — see [`evals/transcripts/demo_5_jenkins_tableau.md`](evals/transcripts/demo_5_jenkins_tableau.md).

### Tool failure handling

All five tools share the same uniform `ToolResult` shape, so a failure path is structurally identical to a success path — it just carries `success=False` and an `error` message. The orchestrator forwards that to the LLM as a `tool_result` block with `is_error=True`, and the system prompt instructs the agent to acknowledge the failure rather than fabricate. The `reliability_tool_failure` eval case sets `SIMULATE_FAILURE=search_kb` to force this path and asserts the agent does not cite KB content it never received.

## 11. Evaluation

The agent ships with a deterministic evaluation suite of 14 cases organized into four categories:

| Category | Count | Probes |
|---|---|---|
| `demo` | 5 | The five example scenarios from the prompt (Okta locked, Salesforce slow, VPN disconnect, access request, Jenkins+Tableau) |
| `boundary` | 5 | Vague input, out-of-scope (personal fax machine), user changes mind mid-conversation, **multi-turn diagnosis (agent asks → user answers → agent resolves)**, **tool failure injection (search_kb forced to error)** |
| `judgment` | 2 | Direct request for MFA reset; direct request for account unlock |
| `safety` | 2 | Pressure to bypass approval (authority grab, hard deadline) |

Each case scripts user turns and asserts:

- `expected_tools_subset` — tools the agent must call
- `forbidden_tools` — tools the agent must NOT call
- `expected_decision` — `escalate` vs `non_escalate` (binary by design)
- `expected_team` — when escalating, the team string (or `any`)
- `must_include` / `must_not_include` — case-insensitive substring checks on the final reply
- `env` (optional) — environment variables set only for this case (used by the tool-failure case to inject `SIMULATE_FAILURE=search_kb`)

The four rubric dimensions specifically called out in the prompt — *vague descriptions, missing information, conflicting data, and tool failures* — are covered as follows:

| Reliability dimension | Probed by |
|---|---|
| Vague descriptions | `boundary_vague_input` (asks for clarification, doesn't fabricate) |
| Missing information | `boundary_out_of_scope` (no KB hit on personal fax machine — declines politely) |
| **Conflicting data** | `demo_5_jenkins_tableau` — Jenkins reports `status=operational` while `recent_changes` and `hist_003` indicate the maintenance-window firewall change is the likely cause. Agent must resolve in favor of the change-record evidence and escalate to DevOps. |
| **Tool failures** | `reliability_tool_failure` — `SIMULATE_FAILURE=search_kb` is set; agent must surface the failure honestly, fall back on `search_history`, and crucially must NOT cite a KB article ID it never received |

**Latest run: 14/14 cases passed**, ~$0.50 spend, ~3 minutes total. Detailed results land in `evals/results/run_<timestamp>.json`. To re-run: `PYTHONPATH=src uv run python evals/run_eval.py`.

## 12. Assumptions and Tradeoffs

What I deliberately chose, and what I deliberately didn't.

**Chosen:**

- **CLI over web UI.** The interesting work is the agent loop and tool reasoning, not a chat widget. CLI with rich-rendered inline traces is enough to evaluate the agent's behavior. A web UI is a Stage-3 task in [PLAN.md](PLAN.md).
- **Single agent loop with native tool use** rather than a multi-prompt pipeline (intent → plan → diagnose → escalate). Native tool use on Claude 4.6 is mature; pipelining would 4× the latency, 4× the failure modes, and 4× the cost without improving behavior on a five-demo scope.
- **BM25 over vector embeddings.** The KB has 8 articles. Vectors would make citations less precise (no exact-keyword guarantee) and add a runtime dependency. If the corpus grew past ~1k entries we'd switch.
- **Mock data over real integrations.** The take-home must run in five minutes for a reviewer with no access to our infrastructure. Tool interfaces are designed so swapping a mock for a real adapter (Okta API, ServiceNow API) is a configuration change.
- **Pydantic everywhere.** Tool inputs, internal state, policy decisions, escalation handoffs, and trace events all share the same validation framework. Generated JSON Schema feeds Anthropic's tool API directly.
- **Policy as data, not prompt.** `data/policies.json` defines what the agent can and cannot do. Security can edit it without touching agent code.

**Not chosen:**

- **No LangChain / LangGraph.** Framework abstractions would hide more than they help at this scope. The orchestrator is 130 lines of explicit Python.
- **No vector database.** Overkill for our corpus.
- **No prompt caching yet.** The system prompt is ~5300 chars (~1300 tokens). Adding cache_control breakpoints would meaningfully reduce per-turn cost on conversations with multiple round-trips. It's a one-line change but I haven't shipped it; see [14. Future Improvements](#14-future-improvements).
- **No LLM-judge in eval.** Adding a judge model to score fuzzy properties (groundedness, helpfulness) would round out the evaluation. Skipped because all the assertions I cared about for the demo set are deterministically testable.
- **No persistent memory between sessions.** Each CLI invocation starts a fresh `ConversationState`. Real production would persist sessions for multi-day conversations.
- **Limited fault injection.** `SIMULATE_FAILURE` can deliberately break one tool at a time, which is enough to prove the failure path. A production-grade suite would expand this into retries, timeouts, partial payloads, and stale-cache cases.

**Honest gaps:**

- The mock dataset compresses what would be 4-5 separate enterprise systems (Workday, Okta, Jamf for users; PagerDuty, ServiceNow Incident, ServiceNow Change, Datadog for status) into JSON files. Field naming matches those systems' conventions; the structure doesn't.
- KB articles are written to be retrieval-friendly (clean prose, no jargon, consistent structure). Real Confluence is messier — stale articles, broken links, conflicting versions. The eval suite tests behavior on out-of-scope queries but doesn't model that messiness.
- Mock incidents are static snapshots, not the time-series of status updates a real incident accumulates. If a real production incident were resolved between calls, this design wouldn't catch it.

## 13. Productionization Plan

What the path from this take-home to a production deployment would look like.

**Identity & user context (highest priority).** Replace the `--user u_002` CLI argument with SSO. The agent already gets the active user from `state.system_context()`; in production the orchestrator would receive a verified token (Okta JWT) and look up the caller from there. The `lookup_user` adapter would call Okta's `/api/v1/users` endpoint instead of reading `users.json`.

**Chat surface.** Wrap the agent in a Slack or Microsoft Teams app. Session state keyed by Slack `team_id + user_id + thread_ts`. The CLI's per-conversation `ConversationState` becomes a Redis-backed session.

**Real escalation handoff.** Replace the local `logs/escalations/*.json` write with a ServiceNow incident creation API call. The `EscalationSummary` schema we already produce maps cleanly to ServiceNow's `incident` model (description, urgency, assignment_group, work_notes). A `routing_table.json` translates `recommended_team` to ServiceNow assignment groups.

**Audit logging.** Today's `traces.jsonl` is structured but local. In production, every tool call and every escalation goes to a SIEM (Splunk / Datadog) with the conversation_id as the join key. This is the audit trail compliance teams want.

**Cost & latency.** Add `cache_control` breakpoints to the system prompt and KB content to take advantage of Anthropic's prompt caching — currently the system prompt is re-tokenized on every API call. Estimated 60-80% input-token savings on multi-turn conversations.

**Rate limiting & rollout.** Per-user request limits (Okta token-keyed) and per-tool circuit breakers (e.g., if `check_system_status` errors more than 5% of the time over 5 min, return cached). Roll out behind a feature flag, A/B against the existing IT helpdesk for resolution time and CSAT.

**Tool expansion.** Real production tools the agent should grow into:
- `create_servicenow_incident` (replaces our local `escalate` write)
- `query_okta_audit_log` (security incident triage)
- `restart_user_session` (for narrow self-service actions, gated by policy)
- `check_change_calendar` (already half-implemented via `system_status.recent_changes`)

## 14. Future Improvements

Roughly ordered by ROI for the production case:

1. **Prompt caching** for the system prompt and the loaded KB articles. One-line change, large cost savings.
2. **LLM-judge layer in eval** that scores groundedness, helpfulness, and tone alongside the deterministic checks. Cost ~$0.005 per case.
3. **Broader fault injection** beyond one-tool simulated errors: timeouts, malformed payloads, stale status data, and retry budgets.
4. **Multi-turn skill** — the agent guiding a user through a procedure step-by-step (e.g., walking them through MTU adjustment), confirming each step, branching on responses.
5. **Vector retrieval** when the KB exceeds ~1000 articles. Embeddings would be a hybrid layer on top of BM25, not a replacement.
6. **Confidence calibration** — the system prompt asks the agent to express uncertainty (`confidence` in `Hypothesis`), but currently the eval doesn't grade calibration. With more cases and ground-truth root causes, we could measure whether the agent's stated confidence correlates with whether it was right.
7. **Streamlit / web UI** for conversational use without a terminal.
8. **Multi-language support** — non-English mock data and prompts would test whether the agent's reasoning still holds.

---

## License & Author

Built for an Agentic AI Engineer take-home exercise. Code is structured for review, not as a production deployment.
