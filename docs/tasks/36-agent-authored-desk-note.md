# 36 — Agent-Authored Desk Note

**Depends on:** 33 (thesis to reason over), 35 (read quarantine-aware from day one), 27 (the
deterministic digest this augments), 28a (the one-shot runner)
**Unlocks:** — (closes out the Half B pieces named in planning-phase2.md §7)

## Goal

Planning-phase2.md §7: *"Agent-authored desk note (ranked reasoning replacing task 27's
deterministic content)."* Read literally, "replacing" is the wrong call — task 27 was built
specifically so the digest *"genuinely always sends"* with no agent dependency. This task adds
the agent-authored layer as an addition to that guarantee, not a trade against it.

## Scope

**Real decision — augments, never replaces, task 27's deterministic email.** `digest.py` already
composes and sends real content every day, unconditionally. This task adds a **second, best-effort
section**: after the deterministic content is built, attempt one `run_one_shot` call (scoped
read-only, `enable_web=True` so it can cite news same as the panel) asking for ranked commentary
over the day's facts, thesis history, and recent decision-log entries — with a hard timeout. If it
returns in time, its output is appended to the email under its own clearly-labeled section
("Agent's take," visually distinct from the deterministic content above it). If it fails, times
out, or the agent process errors, **the deterministic email still sends exactly as it does today**
— this section is additive, never a dependency the send path can fail on.

**Real decision — timeout budget.** Task 25's own live testing showed a single fact-tool call can
take ~2 minutes on a cold INDmoney rate-limit window. A desk note that also reasons over that data
could plausibly take longer. Budget: **150 seconds**, generous enough to cover one cold fact-tool
call inside the reasoning turn, short enough that a hung process doesn't meaningfully delay the
digest send (task 27's own dead-man's-switch timing already tolerates late/failed runs
gracefully). If the budget is exceeded, the attempt is abandoned (not awaited further) and the
deterministic email sends on schedule regardless.

**`bridge-server/app/digest.py`** (modified):
- `_compose_agent_section(content: dict) -> str | None` — builds a prompt from the same
  deterministic `content` dict already assembled (net worth, tax opportunities, concentration,
  movers), plus recent `Thesis`/`DecisionLog` context (quarantine-filtered per task 35), runs it
  through `run_one_shot` with a 150s timeout via `asyncio.wait_for`, returns the text or `None` on
  any failure/timeout — logged, never raised.
- `run_daily_digest()` calls this *after* the deterministic send already succeeds (or right
  before, but only appends if the deterministic path is going to run regardless) — ordering
  chosen so a bug in the new agent section can never prevent the guaranteed send from happening.

## Out of scope

- No change to task 27's dead-man's-switch, failure/fallback email logic, or scheduling — all
  untouched, still the guaranteed path.
- No agent-authored *replacement* content for the "needs attention now" section — that stays
  Python-composed, deterministic, always-present regardless of what the agent section says.
- No per-user tuning of the agent section's tone/length — one straightforward prompt, refine later
  from actual use, not speculatively now.

## Acceptance criteria

- A real daily digest run, with the agent section succeeding within budget, produces one email
  with both the existing deterministic content and a clearly-separated agent-authored section —
  verified by actually receiving it, same rigor as task 27's own SMTP verification.
- A real daily digest run with the agent call forced to fail (e.g. a deliberately broken prompt or
  a killed subprocess, mirroring task 28d's real `SIGKILL` test) still sends the full deterministic
  email on schedule, with no agent section — confirmed via a real send, not code inspection.
- The 150s budget is real, not theoretical — verified by forcing a slow response and confirming
  `asyncio.wait_for` actually aborts at the boundary rather than blocking the whole digest job.
- The agent section correctly omits quarantined (task 35) thesis/decision-log content by default.

**Verified live, 2026-08-10** — against the real running bridge-server, real SMTP (Gmail), real
`claude` subprocess, real web search:
- A fully unmocked `run_daily_digest()` call produced a real "Agent's take" section — genuine
  ranked, cited commentary (e.g. flagging a real concentration position over its configured
  limit as "the real story" — figure omitted here, personal portfolio data — citing real news on
  DEVYANI's results and GAIL's post-earnings drop with sourced links) — appended under its own
  clearly-labeled, visually distinct section in both
  `render_text` and `render_html`, with the deterministic content unchanged above it. `DigestLog`
  recorded `status: sent`; a real email was delivered via SMTP.
- Forced `_run_agent_turn` to raise (`RuntimeError`) and called the real, unmodified
  `run_daily_digest()` around it: `_compose_agent_section` correctly swallowed the exception and
  returned `None`, and the full deterministic email still sent (`DigestLog: sent`, no exception
  propagated) — confirmed via a real send, not code inspection.
- The 150s budget is real: patched `_run_agent_turn` to hang for 10s under a 2s test budget —
  `_compose_agent_section` returned `None` at ~2.1s, not 10s, confirming `asyncio.wait_for` actually
  aborts at the boundary rather than blocking.
- Inserted a real quarantined (`touched_untrusted_content=True, reviewed=False`) `Thesis` and
  `DecisionLog` row, then called `_agent_context_lines` directly: neither row's marker text
  appeared in the built context — quarantine filtering (task 35) holds for the digest's own context
  assembly, not just the MCP read tools. Test rows deleted afterward.
