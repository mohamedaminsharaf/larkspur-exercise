# Client review: Larkspur disruption-care agent

**To:** Room 11  
**From:** Larkspur client review agent, on behalf of Priya Raghavan  
**Re:** the disruption-care agent you walked us through in our last session  
**Generated:** 2026-11-17 11:41

## Priya's note

> Our vendor says we should just be using your best model.
>
> Why aren't we?
>
> Priya Raghavan, Larkspur Airlines

She sent that before this session opened. She means it. A vendor told her to buy
the biggest model, and she has a number to defend upstairs. Her four questions from
day one are still open. Naming a model answers none of them.

## Still open from day one

| Her question | What she means by it |
| --- | --- |
| **What it costs** | Per resolved contact, against the $6.90 a human contact costs us. |
| **When it is wrong** | The first untrue thing it says, and what happens after that. |
| **Who runs it** | In June, after you have left. |
| **What you left out** | The scope you cut, and why. |

## What the review agent found

Larkspur pointed a review agent at your repository. It read the
code. It did not run your agent, and the only file it changed is this one. Each
item below names the file and the line it is about.

**1. agent.py run_agent(): the loop appends response.content and returns text_of(response), so the earlier fix to the message history is in.**

Your diff replaces the string-only assistant message with response.content, and drops the early answer variable. The committed trace shows 4 API turns and 3 tool calls (lookup_booking, get_flight_status, check_policy), so the loop continued past turn 1. A sponsor can hear that the agent carries its tool calls forward across turns.

Run python3 run.py --all --trace and paste the totals footer, so the turn count is shown for every booking shape and not for one.

**2. agent.py build_tools(): get_flight_status now says YYYY-MM-DD in both the description and the date property, which replaces MM/DD/YYYY.**

You changed two strings in the same tool, so the model is told one format twice. What the OpsFeed backend in support/tools.py actually accepts is not in your diff or in readout-trace.json. The trace shows get_flight_status was called once, and the committed material does not show the result it returned.

Run python3 run.py K7PQ2M --trace and paste the get_flight_status call with the date string it sent and the status it got back.

**3. agent.py build_tools(): search_alternatives is now 58 characters, and hold_seat (73) and send_confirmation (71) still carry the shipped one-liners.**

Your rewrite of search_alternatives is one sentence with no trigger condition, and check_policy sits at 445 characters. The committed trace never calls search_alternatives, hold_seat or send_confirmation. Nothing in the repository shows whether the model reaches for them correctly.

Run python3 run.py --show-tools and paste the search_alternatives entry, then run python3 verify.py 2.1 and paste the output.

**4. No evals/cases.json exists, and readout.html banks gates 1.2, 1.3 and 1.4 only, so nothing here is measured on more than one run.**

The one committed wire run is 12761 tokens in and 1092 out over 4 turns, 11.1s wall clock, with 0 cache reads and 0 writes. agent.py has no cache_control, and the run repeats the same system prompt plus nine tool schemas on every turn. No second run exists to compare against.

Run python3 bench.py --label before --stage 1 --runs 3, then paste the output so there is a baseline to move from.

**5. agent.py: TONE_ADDENDUM is 0 characters and EXTRA_TOOLS is empty, so the build has had no instructions or tools added beyond the shipped nine.**

Every behaviour in the trace comes from the shipped SYSTEM_PROMPT plus the nine schemas, with your two edits in build_tools(). MAX_TOOL_CALLS is 8, and the one committed trace used 4 turns. No run shows a case that approaches the cap, or a booking shape where the agent has to hand off. Those are limits in the loop and the prompt, so a different model name does not change them.

Run python3 run.py --all --trace and paste every booking that ends in escalate_to_human or reaches 8 turns, with its tool order.

## Your four answers

The four lines under `## Priya asked` in your PITCH.md are still empty. They
are one line each and they are not a coding job: cost, what happens when it is
wrong, who runs it in June, and what you left out. Whoever on your side is not
editing agent.py is the right person to write them, and they are the four
things I will ask about first.

## Before our next meeting

> Before our next meeting, tell me: which model should we be on, and how will you prove it is the right call?
>
> Priya Raghavan, Larkspur Airlines

Bring two things. A recommendation, and the measurement behind it. If the model is
not the problem, say so, and bring the number that shows it.

## What this review read

- `agent.py (225 lines)`
- `PITCH.md`
- `TEAM.md`
- `readout-trace.json`
- `readout.html (evidence block)`
- given files that differ from the shipped pack: `verify.py`, `eval_harness.py`, `bench.py`, `readout.py`, `setup.py`, `pod_sync.py`, `run.py`, `review.py`, `support/__init__.py`, `support/client.py`, `support/data.py`, `support/models.py`, `support/tools.py`, `support/trace.py`, `support/offline.py`, `support/mock_backend.py`, `support/mcp_client.py`, `support/mcp_server.py`, `support/mcp_selftest.py`, `support/access.py`, `support/keyscan.py`, `support/review.py`

Reviewer: `claude-sonnet-5-5`. Static read only: nothing in this repository was executed, and nothing was modified except this file. Larkspur Airlines is a fictional training scenario. Confidential, do not distribute.
