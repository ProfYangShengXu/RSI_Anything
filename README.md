# RSI_Anything

[中文](README.zh-CN.md) · English

A procedure for improving an agent you are allowed to modify.

Most "self-improving agent" projects start by asking the model to reflect on what went wrong. That step is where they quietly break: the reflection is generated from a summary, the summary came from a harness that already lost the evidence, and the resulting change cannot be attributed to anything. This repository is the other half of that loop — the part that keeps the evidence, forces a verdict, and makes every change reversible.

Status: research prototype. The scripts have been exercised on one real run (see `examples/`). It is not a production tool, and it will not tell you whether your agent is good. It tells you where a specific failure came from, and whether the change you made to fix it actually helped.

## What this is not

- Not an agent framework. It wraps around one you already have.
- Not an evaluator. You bring the judge; it insists the judge be self-checked first.
- Not a self-improvement loop that runs unattended. Every gate can stop it, and one of them usually does.
- Not applicable to closed systems. If you cannot read, write, and instrument the code, this gives you at most a score, not a diagnosis.

## The shape of it

Five stages, five gates, one directory per run.

```
P1 task      freeze H0, budget, judge, sample size ──► G1
P2 evidence  record what happened, no interpretation ──► G2
P3 translate attribute, pick a fix, plan the rollback ──► G3
P4 verify    same start, same budget, same judge ──► G4
P5 archive   keep it only if all four checks pass ──► G5
```

Each run lives in `runs/<id>/` and carries its own state:

```
STATE.md            the entry point: stage, gate records, open questions, next step
prereg.md           H0, budget, judge, sample size, aggregation rules
hashes/             code / data / judge, frozen before the run
observe/events.jsonl
attribute/findings.json
changes/CU-001.md   the change unit, including the rollback
verify/readout.md
archive/experience.jsonl
```

The rule that matters: **state lives on disk, not in the conversation.** A session with no memory of the previous one reads `STATE.md`, runs `verify_state.py`, and continues from the first gate that is not passed.

## Gates

| Gate | Passes when |
|---|---|
| G1 freeze | prereg has H0, budget, judge, sample size; the judge passes four checks — calibration (reference scores highest, garbage ≤ 0.1x reference, reference beats the original by at least 0.1), an adversarial set of at least five fake answers each scored separately (the best fake must trail the reference by at least half the reference-original gap), sensitivity (a known-good change must move the judge by at least half that gap), and stability (same output three times, and shuffled order, within 0.02); the task text is unique and reachable, and whoever audits the judge did not write it |
| G2 evidence | `check_trace.py` passes: required fields, monotonic `seq`, at least one `model/request`, and every `tool/call` paired with a `tool/result` |
| G3 attribute | every finding names a component, a locator, and a granularity; every candidate has a probe; at most one candidate is applied |
| G4 verify | same start, same budget, same judge (judge hash unchanged), one variable changed, conclusions stated at the strength the sample size allows |
| G5 archive | the entry passed all four admission checks: preflight, benefit, cost, transfer |

Gates are binary. If one fails, the next stage does not start.

## Quick start

Install as a skill (the agent reads `SKILL.md`, not this file):

```bash
# Hermes
cp -r SKILL.md references templates scripts \
  ~/AppData/Local/hermes/skills/software-development/rsi-anything/

# Claude Code
mkdir -p .claude/skills/rsi-anything
cp -r SKILL.md references templates scripts .claude/skills/rsi-anything/

# dsh
mkdir -p ~/.dsh/skills/rsi-anything
cp -r SKILL.md references templates scripts ~/.dsh/skills/rsi-anything/
```

Then, per run:

```bash
RUN=runs/$(date +%Y%m%d-%H%M)-mytarget
mkdir -p $RUN/{hashes,observe,attribute,changes,verify,archive,logs}
cp templates/STATE.md $RUN/STATE.md
cp templates/prereg.md $RUN/prereg.md

python scripts/freeze_hashes.py $RUN --code ./src --judge ./judge.py --data ./tasks
python scripts/import_trace.py trace.jsonl -o $RUN/observe/rebuilt.jsonl --reconstructed
python scripts/check_trace.py $RUN/observe/rebuilt.jsonl
python scripts/verify_state.py $RUN
```

The four scripts use only the standard library.

## Worked example

`examples/replay-bb6-v40/` is a real run, replayed from a recorded trace. The harness under improvement was a multi-block coding agent that spent 26 minutes on a COBOL migration and returned zero. The trace held 38 tool calls; 24 of them touched the same output file.

What came out:

| finding | component | locator |
|---|---|---|
| 24/38 calls circle one deliverable | contract | output path normalization |
| 15 write attempts, alternating between two write paths | tool surface | `shell_run` redirects and `files_write` coexist |
| repeated `pwd`/`ls`/`cat` after writing | tool | write receipt carries no path, size, or hash |

All three landed on the harness, none on model capability — which matches what the code actually contained.

The example also shows the gates refusing to pass. The trace was historical, so it had no tool results: 38 calls, zero receipts. G2 failed, the evidence was marked reconstructed, and the conclusions stayed at hypothesis level. That is the intended behaviour, and it is the reason the example is worth reading: a tool that green-lights a reconstructed trace is worse than no tool.

A second detail from the same example: `verify_state.py` was tested in both directions, including deleting an artifact that a gate claimed had passed. It reports `stale` and exits non-zero.

## Why it is built this way

**Evidence before attribution.** The most common failure in this kind of work is not a wrong fix, it is a fix aimed at a cause that was never observed. Recording first, interpreting later, is the only ordering that keeps the two separable.

**Reconstructed evidence is labelled.** When the run predates instrumentation, you can still rebuild part of the story from logs. That reconstruction is stored separately, tagged `source=reconstructed`, and is allowed to produce hypotheses only. Attribution may cite observed records alone. Without this split, a guess eventually gets quoted as a measurement.

**Every change carries its own undo.** Snapshot, an executable rollback, and the check that must go green again afterwards. "I remember how to revert it" is not a rollback plan.

**Conclusions are bounded by sample size.** Below 50 items per arm you report a direction, not a p-value. Between 100 and a few hundred you use an exact paired test. The repository never reports an error bar it cannot justify.

**Cost is part of the result.** A change that improves the score while tripling the token spend is not obviously an improvement, so `cost per solved task` sits next to the score.

## Known limits

- The gates are only as good as the judge you bring. G1 checks that the judge is consistent and hard to fool; it cannot check that the judge measures the right thing.
- Small runs stay small. With 15 tasks per arm, the most you can honestly report is a direction.
- `import_trace.py` understands request/response trace files. Native message logs with tool results need a different importer.
- Nothing here automates the choice of what to change. Attribution is still the hard part, and it is still done by reading.

## Where the rules come from

Each gate is anchored to published work rather than intuition:

| Rule | Source |
|---|---|
| Evaluation is an experiment; size it before running | 2411.00640 |
| Do not use normal approximations below a few hundred points | 2503.01747 |
| Localization granularity is itself a variable | 2604.00167 |
| Self-correction without external feedback degrades | 2310.01798 |
| Abstention helps, over-abstention does not | 2611.06158, 2402.15610 |
| Localize, repair, validate — plus report cost | 2407.01489 |
| Interface design changes capability | 2405.15793 |
| Select on a held-out set | 2606.28374 |
| A single-surface judge invites gaming | 2605.21384 |
| Audits have their own failure modes | 2607.02586 |

## License

MIT. See `LICENSE`.
