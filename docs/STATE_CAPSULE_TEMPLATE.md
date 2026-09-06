# Ω CURRENT STATE CAPSULE — TEMPLATE

> **Mutable recovery hint, not constitution.** كل قيمة هنا يجب إعادة التحقق منها عند الاستئناف.

## Identity
- project/profile:
- captured_at:
- environment:

## Last Verified Baseline
- baseline/ref:
- evidence:
- verification scope:

## Current Evidence State
- PROVEN:
- NOT_PROVEN:
- FAIL:
- BLOCKED:

## Protected Invariants
- invariant:
- last regression evidence:

## Open Work in Causal Order
1. first provable blocker / next safe action:
2. next dependency:

## External / Human Gates
- required action:
- why automation cannot safely perform it:
- minimum user action:

## Recovery Path
- exact source(s) to re-read:
- checkpoint/state location:
- trigger to resume:

## Staleness Rule
عند كل استئناف: لا تعتمد أي SHA أو PASS أو blocker هنا إذا تعارض مع دليل أحدث. أعد اكتشاف الواقع أولًا، ثم حدّث الكبسولة.
