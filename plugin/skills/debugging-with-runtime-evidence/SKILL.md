---
name: debugging-with-runtime-evidence
description: "Use when a bug's cause is not evident from existing output. Finds the cause from runtime logs before any fix. Skip for a compile error or a stack trace that names the cause."
---

# Debugging With Runtime Evidence

## Role

This skill owns diagnosis by runtime evidence. Never fix from code reading alone.

## Workflow

1. State 3 to 5 hypotheses. Give each an ID such as A, B, or C.
2. Add 3 to 8 probes. Each probe writes one NDJSON line with `hypothesisId`,
   `location`, `message`, `data`, and `timestamp` to
   `<tmpdir>/refract-debug/<slug>.ndjson`. Resolve the OS temp directory once.
   Never use a hard-coded `/tmp`. Use the symptom in kebab case for `<slug>`.
   Create the `refract-debug/` directory. Write the absolute log path into each probe.
   Append with the language's standard file I/O
   in a snippet of one to three lines. Cover function entry and exit, values
   before and after critical operations, the branch taken, and suspect values.
   Wrap each probe in a foldable region marked `refract-debug`. For a language
   without regions, wrap it in comment lines carrying `refract-debug` at the
   start and end. Never log a secret or personal data. Log the value's type
   or length instead.
3. Clear the log file before each run. Clearing the file does not remove probes.
4. End the turn with numbered reproduction steps. Remind the user to restart
   any service the change touches. The user reproduces the bug and replies.
   The agent does not run the reproduction.
5. Read the log. Mark each hypothesis CONFIRMED, REJECTED, or INCONCLUSIVE
   and cite the log lines. If the log is empty or missing, treat reproduction
   as failed or the probes as unreached. Ask for another run. Do not guess.
   If every hypothesis is rejected, form new hypotheses from different
   subsystems and add probes. Do not fix.
6. Fix only when a cited log line proves the cause. Keep the fix minimal and
   reuse existing patterns. Never use a sleep or delay as a fix.
7. Keep every probe until the user confirms the fix.
   Ask for a verification run and compare the before and after log lines.
   If the run still fails, revert the fix. Keep the probes until the new log
   is analyzed. Return to step 1 with new hypotheses. Reuse or replace probes
   so the total stays at 8 or fewer.
8. After the user confirms the fix, remove every probe and the log file.
   State the cause and the fix in two lines.

## Routing the Fix

Once the cause is proven, classify the fix under `using-refract`.
Make a direct fix in place. For a coordinated fix, hand the proven cause and
the cited log lines to `coordinating-multi-model-work`.

## Each Handoff Message

Every turn that passes control to the user states the leading hypotheses with
confidence, what the logs showed, and the next reproduction steps.

## Edge Cases

- A probe can change timing. Note this when a race or concurrency bug is suspected.
- If the user abandons the session, tell the user that probes remain and give
  the search for `refract-debug` that finds them. Never remove probes unprompted.
- Code that runs in a container or on a remote host is out of scope because
  the agent cannot read a local temp file there.
