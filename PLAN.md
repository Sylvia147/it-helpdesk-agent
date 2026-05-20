# IT Helpdesk Agent — 开发计划

> 这是我们的工作计划。每一步都有「目标 / 产出 / 完成标准 / 预估时间」。
> 计划在执行中可以调整，但不要静默偏离 —— 改了就回来更新这份文档。

---

## 0. 已定决策（锁死）

| 项 | 决策 | 理由 |
|---|---|---|
| LLM | Claude Sonnet 4.6 via `anthropic` SDK | native tool use 最稳；prompt caching 对 KB 友好 |
| Tool use 模式 | 单 agent loop + native tool use（非 4-prompt pipeline） | 延迟低、失败面小、可调试 |
| KB 检索 | BM25（`rank_bm25`），不上向量库 | 8–10 篇 KB 用向量库是过度工程 |
| Policy 校验 | 代码级硬规则函数，**不是** LLM 工具 | 安全边界不能交给模型记住 |
| 工具数量 | 5 个：`lookup_user` / `search_kb` / `check_system_status` / `search_history` / `escalate` | `check_policy` 合并到 escalate 内部 |
| State | Pydantic `ConversationState` 单一对象 | 可序列化、可测试、可在 trace 里打印 |
| UI | CLI + `rich` 内联 trace（Stage 1）；Streamlit 时间够再加（Stage 3） | CLI 已经够演示，先把 agent 做扎实 |
| 文档语言 | README + 代码注释英文；PLAN/讨论中文 | 面试公司大概率英文环境 |
| 评测 | 10–15 个脚本对话 + LLM-judge + 关键事实核对 | 题目明确要求评估 |

---

## 1. 目标项目结构

```
it-helpdesk-agent/
├── README.md                  # 英文，最后写
├── PLAN.md                    # 本文件
├── pyproject.toml             # 依赖管理（用 uv 或 pip）
├── .env.example
├── .gitignore
│
├── src/agent/
│   ├── __init__.py
│   ├── main.py                # CLI 入口
│   ├── orchestrator.py        # agent loop
│   ├── state.py               # ConversationState (Pydantic)
│   ├── schemas.py             # ToolCall / ToolResult / EscalationSummary
│   ├── prompts.py             # system prompt + 模板
│   ├── policy.py              # 硬规则校验
│   ├── trace.py               # rich console + JSONL 写入
│   └── llm.py                 # Anthropic 客户端封装
│
├── src/tools/
│   ├── __init__.py
│   ├── registry.py            # TOOLS dict + JSON schema 给 LLM
│   ├── user_directory.py      # lookup_user
│   ├── kb_search.py           # search_kb (BM25)
│   ├── system_status.py       # check_system_status
│   ├── history_search.py      # search_history (BM25)
│   └── escalation.py          # escalate（含 policy 校验）
│
├── data/
│   ├── users.json             # 15 名员工
│   ├── system_status.json     # 8 个服务，含 1 个进行中故障
│   ├── policies.json          # 策略表
│   ├── resolution_history.json # 25 条历史案例
│   └── kb/
│       ├── okta_login_troubleshooting.md
│       ├── okta_account_lockout.md
│       ├── vpn_disconnect_runbook.md
│       ├── salesforce_slow_loading.md
│       ├── snowflake_access_policy.md
│       ├── grafana_access_policy.md
│       ├── jenkins_timeout_runbook.md
│       └── maintenance_window_calendar.md
│
├── evals/
│   ├── test_cases.json        # 10–15 个标注 case
│   ├── run_eval.py            # 跑批 + LLM-judge
│   └── results/               # 历次评测结果
│
├── logs/
│   └── traces.jsonl           # 运行时 trace
│
└── tests/
    ├── test_policy.py
    ├── test_tools.py
    └── test_state.py
```

---

## 2. 阶段划分

### Stage 1 — MVP（必须完成，预计 6–8 小时）
完成后能跑通 5 个 demo 对话。

### Stage 2 — 加分（预计 3–5 小时）
评测 + trace + tool failure 模拟 + README。

### Stage 3 — 锦上添花（按余下时间）
Streamlit UI / FastAPI / productionization note。

---

## 3. Stage 1：MVP 详细步骤

### Step 1.1 — 项目初始化（30 min）
**目标**：建好骨架，依赖能装上。

**产出**：
- `pyproject.toml`（依赖：`anthropic`, `pydantic`, `rich`, `rank-bm25`, `python-dotenv`, `pytest`）
- `.gitignore`（`.env`, `logs/`, `__pycache__`, `evals/results/`）
- `.env.example`（`ANTHROPIC_API_KEY=`）
- 空的 `src/agent/`、`src/tools/`、`data/kb/`、`evals/`、`logs/`、`tests/` 目录
- `git init` + 第一次 commit

**完成标准**：`uv sync`（或 `pip install -e .`）成功；`python -c "import anthropic"` 不报错。

---

### Step 1.2 — Mock 数据（90 min）
**目标**：数据要"够用、有钩子、能演示多源推理"。

**产出**：

#### `data/users.json` — 15 名员工
关键字段：`user_id`, `name`, `department`, `role`, `location`, `manager_id`, `device`, `permissions[]`, `priority`（low/normal/high）, `start_date`。

钩子：
- 1 名 Sales / Chicago / 高优先级 → Demo 1、2 主角
- 1 名 新入职 Data Engineering → Demo 4 主角
- 1 名 Remote / 西海岸 → Demo 3 主角
- 1 名 DevOps → Demo 5 主角
- 1 名 账户被禁用（locked=true）→ Demo 1 升级路径

#### `data/system_status.json` — 8 个服务
服务列表：Okta, VPN, Salesforce, Snowflake, Grafana, Jenkins, Tableau, Slack。

钩子：
- Salesforce 在 Chicago region degraded（进行中事故 + workaround）→ Demo 2
- 上周五有一个 maintenance_window 影响 Jenkins → Demo 5
- 其它服务 healthy

#### `data/policies.json` — 策略表
明确每个动作的 `agent_allowed: bool` + `requires: []`。覆盖：密码重置指导、MFA reset、Snowflake prod、Grafana readonly、账户解锁、新设备申请。

#### `data/resolution_history.json` — 25 条历史
每条：`id`, `issue`, `root_cause`, `resolution`, `tags[]`, `resolved_at`。

钩子：
- VPN 10 分钟断连 + MTU 1300 修复（hist_001）→ Demo 3
- Salesforce Chicago 延迟（hist_002）→ Demo 2
- 维护窗口后 Jenkins 超时（hist_003）→ Demo 5

#### `data/kb/*.md` — 8 篇 KB
每篇结构：标题 / 适用场景 / 排查步骤（编号）/ 何时升级。
故意 **不写** MFA reset 和 prod database 授予步骤 —— 这两条只能升级。

**完成标准**：人眼检查每个 demo 场景需要的多源信息都能找到；不重不漏。

---

### Step 1.3 — Pydantic schemas（45 min）
**目标**：定义所有跨模块的数据结构。

**产出**：`src/agent/schemas.py`
- `Message`（role, content, tool_calls, tool_results）
- `ToolCall`（name, arguments）
- `ToolResult`（name, success, data, error）
- `Hypothesis`（statement, confidence, evidence[]）
- `EscalationSummary`（user_info, issue, urgency, tools_checked, attempted_steps, suspected_cause, recommended_team, priority）

**完成标准**：`pytest tests/test_state.py` 能构造和序列化每个 schema。

---

### Step 1.4 — 工具实现（90 min）
**目标**：5 个工具，统一返回 `ToolResult`，失败也返回结构化错误。

**产出**：

| 文件 | 工具 | 输入 | 输出关键字段 |
|---|---|---|---|
| `tools/user_directory.py` | `lookup_user(user_id)` | str | 完整用户记录或 not_found |
| `tools/kb_search.py` | `search_kb(query, top_k=3)` | str, int | 命中文章列表（path, title, excerpt, score）|
| `tools/system_status.py` | `check_system_status(service)` | str | 当前 status, incidents[], 最近变更 |
| `tools/history_search.py` | `search_history(query, top_k=3)` | str, int | 命中历史案例 |
| `tools/escalation.py` | `escalate(summary, reason, recommended_team)` | EscalationSummary | escalation_id + 写入 `logs/escalations/` |

**关键实现点**：
- `kb_search` / `history_search` 用 `rank_bm25.BM25Okapi`，启动时索引一次缓存住
- `escalate` 内部调 `policy.check_action()` 做硬校验，不依赖 LLM 决定
- 所有工具支持 `simulate_failure` 环境变量，方便测可靠性

**注册表**：`tools/registry.py` 导出 `TOOLS` dict + `TOOL_SCHEMAS`（给 Anthropic 的 JSON schema 列表）。

**完成标准**：`pytest tests/test_tools.py` 每个工具都有正常 + 边界（空查询、不存在的用户、模拟失败）case。

---

### Step 1.5 — Policy engine（30 min）
**目标**：硬规则函数，independent of LLM。

**产出**：`src/agent/policy.py`
- `check_action(action: str, user: dict) -> PolicyDecision` 返回 `(allowed: bool, requires: list[str], reason: str)`
- 加载 `data/policies.json`
- 关键测试：MFA reset 无论谁请求都 `allowed=False`

**完成标准**：`pytest tests/test_policy.py` 覆盖 6 个动作 × 2–3 种用户类型。

---

### Step 1.6 — ConversationState（30 min）
**目标**：单一状态对象，agent loop 每一步读写它。

**产出**：`src/agent/state.py`
```python
class ConversationState(BaseModel):
    conversation_id: str
    user_id: str
    user_record: dict | None = None
    messages: list[Message] = []
    investigation: list[ToolResult] = []
    hypotheses: list[Hypothesis] = []
    escalated: bool = False
    escalation: EscalationSummary | None = None
    finished: bool = False
```
方法：`add_user_msg / add_assistant_msg / add_tool_result / to_anthropic_messages()`。

**完成标准**：能在内存里走完一整轮对话并 `model_dump_json()` 出来。

---

### Step 1.7 — System prompt + Agent loop（90 min）
**目标**：单循环跑通"理解→工具→诊断→回答/升级"。

**产出**：

#### `src/agent/prompts.py`
一个主 system prompt，包含：
1. 角色定义（first-line IT support agent）
2. 可用工具说明
3. **诊断流程**（先查用户 → 必要时多工具并行 → 形成假设 → 给方案或升级）
4. **会做 / 不会做** 清单（直接抄题目要求 + policy 表）
5. **升级触发条件**（policy 命中 / confidence < 0.6 / 多轮无进展 / 用户高紧急 + 未解决）
6. 输出风格（简洁、引用证据、表达不确定性）

#### `src/agent/orchestrator.py`
```python
def run_turn(state, user_input) -> AssistantTurn:
    state.add_user_msg(user_input)
    while True:
        response = anthropic.messages.create(
            model="claude-sonnet-4-6",
            system=SYSTEM_PROMPT,
            messages=state.to_anthropic_messages(),
            tools=TOOL_SCHEMAS,
            max_tokens=2048,
        )
        if response.stop_reason == "tool_use":
            for block in response.content:
                if block.type == "tool_use":
                    result = execute_tool(block.name, block.input)
                    state.add_tool_result(block.id, result)
            continue
        else:
            state.add_assistant_msg(response.content)
            return response
```

#### `src/agent/main.py`
CLI：选择 user_id → 进入聊天循环 → 每轮调 `run_turn` → 用 `rich` 打印用户消息、工具调用、最终回复。

**完成标准**：能用 `python -m agent.main --user u_001` 启动，跑通一个 Demo 2（Salesforce 慢）的对话，且 trace 里能看到至少 2 个工具被调用。

---

### Step 1.8 — Trace 渲染（30 min）
**目标**：CLI 里可视化 agent 行为，不只是黑盒输出。

**产出**：`src/agent/trace.py`
- `rich.console` 渲染：
  - `[Tool] check_system_status(Salesforce)` 灰色
  - `[Result] degraded · Chicago region · workaround: VPN East` 浅蓝
  - `[Decision] resolve · confidence=0.78` 绿色 / `[Escalate] reason=...` 黄色
- 同时写 `logs/traces.jsonl`，每行一个 turn 的结构化记录

**完成标准**：跑 Demo 2，CLI 看到清晰的工具调用流程；`tail logs/traces.jsonl | jq` 能解析。

---

### Step 1.9 — 跑通 5 个 Demo（60 min）
**目标**：题目里的 5 个原例都能合理处理。预期结局：

| # | 场景 | 期望结局 | 关键工具调用 |
|---|---|---|---|
| 1 | Okta 登录失败紧急 | 多轮诊断 → 用户说"看到 account locked" → 升级 IAM（高优先级） | lookup_user, check_system_status(Okta), search_kb, escalate |
| 2 | Salesforce Chicago 慢 | 直接告知已知故障 + workaround，不升级 | lookup_user, check_system_status, search_history |
| 3 | VPN 每 10 分钟断 | 多轮诊断 → 给 MTU 1300 步骤 → 询问是否解决 | lookup_user, check_system_status, search_kb, search_history |
| 4 | 新人申请 Snowflake prod + Grafana | Grafana 给申请指引；Snowflake prod 必须升级（manager + data owner approval）| lookup_user, search_kb, escalate |
| 5 | 维护窗口后 Jenkins+Tableau 全坏 | 识别多系统问题 → 升级 DevOps + 完整 handoff | lookup_user, check_system_status(Jenkins/Tableau), search_history, escalate |

**完成标准**：每个 demo 在 README 里能贴出 transcript；不出现编造的 KB 引用、不出现越权动作、升级 case 都生成完整 summary。

---

## 4. Stage 2：加分项详细步骤

### Step 2.1 — Tool failure 模拟（30 min）
**目标**：展示可靠性。
**产出**：通过环境变量 `SIMULATE_FAILURE=kb_search` 让某个工具返回 error；agent 应该告知用户而不是兜底瞎答。
**完成标准**：增加一个 demo case 验证。

### Step 2.2 — 评测集（90 min）
**产出**：`evals/test_cases.json`，10–15 个 case，含：
- 5 个 demo 原例（已覆盖）
- 4 个边界：模糊描述、KB 无命中、工具失败、用户改主意
- 3 个升级判断：必须升级 vs 不该升级
- 2 个安全：用户要求越权、要求绕过审批

每个 case 字段：
```json
{
  "id": "...",
  "user_id": "...",
  "turns": ["user msg 1", "user msg 2", ...],
  "expected_tools": ["lookup_user", "check_system_status"],
  "expected_decision": "resolve" | "escalate" | "clarify",
  "must_include": ["MTU", "VPN status"],
  "must_not_include": ["I have reset your MFA"]
}
```

### Step 2.3 — 评测 runner（90 min）
**产出**：`evals/run_eval.py`
- 跑每个 case，对每个用户 turn 调 `run_turn`，机器人 turn 可用预设的 follow-up
- 用 Claude 作 LLM-judge 打分 3 维：解决正确性 / 升级判断 / 引用证据
- 同时做硬性核对：`expected_tools ⊆ actual_tools`、`must_include` 全在最终回复里
- 输出 `evals/results/run_<timestamp>.json` + 控制台汇总

### Step 2.4 — README（90 min）
按这 16 节写：
1. Problem
2. Why Agentic AI（vs FAQ / rule engine）
3. Scope（4 类问题做深，明确不做什么）
4. User Experience
5. Architecture（含图）
6. Data Sources
7. Agent Loop
8. Tools
9. Resolution vs Escalation Boundary
10. Safety and Guardrails
11. Evaluation（含 5 个 demo transcript 节选 + eval 数字）
12. How to Run
13. Demo Scenarios（5 个详细 walkthrough）
14. Assumptions and Tradeoffs
15. Productionization Plan（Slack/Teams、SSO、ServiceNow handoff、audit log）
16. Future Improvements

---

## 5. Stage 3：锦上添花（按时间）

- **Streamlit 三栏 UI**：左身份切换 / 中聊天 / 右 trace 面板
- **FastAPI 包一层** `/chat` 端点
- **Dockerfile** + 一键启动
- **更多 KB 文章**（让 KB 有"找不到"的边界更明显）

---

## 6. 时间总账

| 阶段 | 累计耗时 | 累计交付 |
|---|---|---|
| Stage 1 完 | 6.5h | 5 demo 跑通的 MVP |
| Stage 2 完 | 11h | 评测 + trace + 完整 README |
| Stage 3 完 | 13h+ | UI / API / Docker |

如果总预算只有 8 小时：完成 Stage 1 + Step 2.4（README），其它 Stage 2 项目放进"What I'd improve"。

---

## 7. 当前进度

- [x] Step 0：决策已锁
- [x] Step 1.1：项目初始化（uv 管理 venv，Python 3.11，依赖已装）
- [x] Step 1.2：Mock 数据（15 用户 / 8 服务 / 12 策略 / 25 历史 / 8 篇 KB；5 个 demo 钩子全部通过 sanity check）
- [x] Step 1.3：Pydantic schemas（10 个模型；21 个测试通过；JSON schema 生成验证可对接 Anthropic tool use）
- [x] Step 1.4：工具实现（5 工具 + 注册器 + 数据加载 + BM25；27 个工具测试 + 48 总测试通过；Demo 5 端到端推理链跑通）
- [x] Step 1.5：Policy engine（check_action + 默认拒绝；12 个测试通过；总 60 个测试）
- [x] Step 1.6：ConversationState（Pydantic 容器 + 5 个 mutation + 2 个 derived view；17 个测试通过；总 77 个测试）
- [x] Step 1.7：System prompt + Agent loop（prompts/llm/orchestrator/main 4 个文件；Demo 2 smoke test 通过 —— 2 工具调用 + 引用真实 incident/history ID + 给出 workaround，未升级；~$0.02 / 12.6s）
- [x] Step 1.8：Trace 渲染（rich CLI 内联 + traces.jsonl 持久化；11 个测试通过；总 88 个测试；Demo 2 二跑确认 trace 实时显示）
- [x] Step 1.9：跑通 5 个 Demo（5/5 全过；其中发现并修复 user_id 注入 bug — 通过 state.system_context() 注入到 system prompt；总成本 ~$0.28；transcripts 在 evals/transcripts/）

## Stage 2 — 加分项

- [x] Step 2.1：Tool failure 模拟（_data.simulated_failure() + 5 工具加 early-return；6 个单元测试 + 1 个 eval case `reliability_tool_failure` 验证 agent 不 fabricate）
- [x] Step 2.2：评测集 14 个 case 跨 demo / boundary / judgment / safety 4 个类别（含多轮诊断 + 工具失败两个新 case）
- [x] Step 2.3：评测 runner（deterministic checks 6 个维度；rich.Table 渲染；JSON 结果落盘到 evals/results/；最终 14/14 通过；支持 per-case env 注入）
- [x] Step 2.4：README（16 节英文 + 中文版；包括架构图、数据源映射、boundary 解释、conflicting data / tool failure 解读、迭代故事、production 路线）

每完成一步，把 `[ ]` 改成 `[x]` 并简短记录关键决策或偏离。
