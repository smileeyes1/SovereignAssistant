# HAKIM Ω — RESUME STATE

Status: **ACTIVE DEVELOPMENT CHECKPOINT**
Branch: `end-user-release-v1`
Base verified commit: `d0c6fbe34c0055d8dbfbbaf76b5231f3b3159d37`

## CURRENT STATE
The verified `main` baseline already contains:
- free-first provider policy;
- paid providers disabled by default with zero budget;
- durable runtime/service foundation;
- governance tests, autonomy arena, Docker smoke test and reality gate passing on the base commit.

The end-user release branch has been created from that verified baseline.

## LAST KNOWN GOOD
`main@d0c6fbe34c0055d8dbfbbaf76b5231f3b3159d37`

Evidence already obtained on that baseline:
- governance regression suite: 153 passed;
- autonomy arena: certified L7, 18/18 scenarios, pass_rate 1.0;
- production Docker build: PASS;
- live runtime smoke test: PASS;
- reality gate live runtime/restart continuity/health check: PASS.

## OPEN GAP
The project is not yet a finished end-user assistant.

Current user-facing `index.html` is only a static mock interface with local JavaScript responses and is not connected to the real autonomy runtime.

The real runtime currently exposes health/event/webhook ingress but does not yet provide a complete end-user task journey:
`SUBMIT -> STATUS -> RESULT -> ARTIFACT`.

## CURRENT MISSION
Build **HAKIM Ω End-User Release v1** so the user can type a natural request and receive the final result/file without seeing code, choosing providers, managing infrastructure, or manually repairing failures.

## REQUIRED END-USER CONTRACT
Example acceptance command:
`أنشئ درس الجمع ضمن ١٠ كملف PDF`

Expected behavior:
1. Accept natural-language task.
2. Create durable task id/state.
3. Execute through free-first/local-first routing.
4. Generate the requested real artifact, never code in place of the artifact.
5. Verify the final artifact itself.
6. Repair/retry automatically when safe.
7. Return status and final downloadable artifact.
8. Preserve restart continuity and idempotency.
9. Never silently use paid services.
10. Never claim VERIFIED without evidence.

## OPEN P0/P1
P0:
- No end-user task API yet.
- No real connection between current UI and runtime.
- No end-user artifact delivery path yet.

P1:
- No final mobile-first end-user UX.
- No end-to-end acceptance test for natural request -> final artifact.
- No release evidence specific to end-user flow.

## NEXT SAFE ACTION
Implement the smallest vertical slice on `end-user-release-v1`:
1. durable task model;
2. authenticated/controlled `POST /tasks` submit endpoint;
3. `GET /tasks/{id}` status/result endpoint;
4. artifact reference/download contract;
5. replace static `index.html` with a mobile Arabic UI connected to those endpoints;
6. tests for submit/status/restart/idempotency/free-first/no-paid-fallback;
7. run governance + reality gates before merge.

## STOP / RELEASE RULE
Do not merge to `main` until the end-user vertical slice passes its tests and existing governance/reality gates without regression.

## ROLLBACK POINTER
Rollback to:
`d0c6fbe34c0055d8dbfbbaf76b5231f3b3159d37`

## HOW TO RESUME
For future sessions, read this file first, then verify the branch head and CI. Resume using:
`LAST VERIFIED STATE -> OPEN GAP -> NEXT SAFE ACTION`.
Never invent progress that is not present in GitHub or test evidence.
