# Agent memory: 15-minute presenter runbook

Teach one story: the adviser uses this conversation’s history, recalls a fact
on a later visit, and keeps different shoppers’ memories separate.

For installation and the exact messages, use the
[beginner quickstart](../guides/agent-memory-quickstart.md). This page is the timed
presenter version. Use fictional details and run the app locally.

## Prepare before the audience arrives

1. Complete the quickstart with Alex and a fresh `SHOP_OWNER_PREFIX`.
2. Verify that the Sony ZV-E10 ownership fact appears in **Long-term memory**.
   Keep that prefix for the presentation. Tell the audience the fact was learned
   in an earlier conversation.
3. Verify that Jordan has no Alex facts. Leave Jordan unused for the main demo.
4. Start a new conversation as Alex. Confirm the backend is running and the
   adviser can reply. Use the default [shop address](http://127.0.0.1:8000/), or
   the port you chose at setup.

Preparation and background extraction are outside the 15-minute presentation.
On a dedicated demo service, you can set a one-minute extraction interval as in
[Redis’s quickstart](https://redis.io/docs/latest/develop/ai/context-engine/agent-memory/python-sdk-quickstart/).
That interval does not guarantee completion in exactly one minute.

## Walkthrough

Open **⋯ Chat settings** beside the message box for the memory mode, new
conversation, shopper selector and memory inspector.

| Time | Action | What to show |
| --- | --- | --- |
| 0–2 min | Explain session memory and long-term memory using Alex’s camera. | Session = one conversation; shopper = the same person across conversations. The app supplies context to the model. |
| 2–5 min | As Alex, choose **Short-term: this session only**. Say “I own a Sony ZV-E10 and film walking tours.” Then ask “What camera do I own?” | In **What the model saw**, earlier conversation contains the ownership message; no long-term memories were supplied. |
| 5–7 min | Choose **No conversation memory** and repeat the ownership question. | The new reply’s captured request has no earlier turns or long-term facts. Judge the context, not whether the model happens to guess correctly. |
| 7–10 min | Show Alex’s saved ownership fact in the memory inspector. Choose **Short-term + long-term**, start **New conversation**, then ask the ownership question. | Earlier conversation is empty; the retrieved long-term fact supplies the camera. Explain that the saved fact came from rehearsal. |
| 10–12 min | Switch to Jordan, start **New conversation**, choose **Short-term + long-term**, and ask the same question. | Alex’s ownership fact is absent from Jordan’s retrieved memories. This is an owner-scoping demonstration, not authentication. |
| 12–15 min | Return to Alex and ask for lightweight gear for walking tours. Inspect one reply. | Connect remembered preferences to useful advice, show actual catalogue results if returned, and recap which context reached the model. |

Changing the mode affects the next reply; it does not change past request captures.
Every turn still saves session events for background extraction, including when
memory context is off.

If a long-term fact is missing, show the pending state and explain the delay.
Continue the within-session example or show previously captured, clearly labelled
rehearsal evidence. Do not substitute a manual write for automatic extraction.

## Keep extensions optional

Playbook publishing, purchase-tool sequences, custom memory types and corrections
are in the [advanced guide](../guides/agent-memory-advanced.md). They are useful
follow-ups after the core lesson.

Keep sensitive-data exclusion testing out of the promised live sequence: its
behaviour was unresolved in the earlier rehearsal. See the advanced guide for the
recorded limitation and a separate fictional test.

To reset or troubleshoot, use the quickstart’s
[restart instructions](../guides/agent-memory-quickstart.md#5-stop-restart-or-start-fresh)
and [troubleshooting table](../guides/agent-memory-quickstart.md#if-something-does-not-work).
