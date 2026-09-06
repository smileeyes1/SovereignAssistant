# HAKIM Ω — Local Sovereign Mode

This mode makes ChatGPT/OpenAI/Gemini/GitHub/cloud memory optional rather than structural dependencies.

## Owned root of trust

1. A device you control.
2. Local Python 3.11+ runtime (core uses only the standard library).
3. Local SQLite database under the workspace `.omega/` directory.
4. Optional local model weights (GGUF) and a local inference engine such as llama.cpp.

The core state/queue/evidence/checkpoints/backups continue to work with no model and no internet. AI reasoning requires a local model, but no account or API key.

## Local model

`llama.cpp` can run GGUF models locally and exposes an OpenAI-compatible local server. Example:

```sh
llama-server -m ~/models/model.gguf --host 127.0.0.1 --port 8080
```

Then:

```sh
python -m app.hakim.run_local_sovereign --root ~/hakim-workspace --model local-model doctor
python -m app.hakim.run_local_sovereign --root ~/hakim-workspace --model local-model enqueue "راجع هذا المشروع وأصلح أعلى خلل قابل للإثبات"
python -m app.hakim.run_local_sovereign --root ~/hakim-workspace --model local-model run-once
```

## Independence properties

- No ChatGPT account required.
- No cloud memory required: state is SQLite.
- No GitHub required at runtime.
- No remote model provider required.
- Remote model URLs are rejected by default.
- Work is idempotent and lease/restart safe.
- A candidate checkpoint cannot replace the last verified baseline until explicitly verified.
- Writes are workspace-confined and create an undo copy when replacing a file.
- Arbitrary shell commands are not enabled; only a small local allowlist is accepted without new authority.
- Backups are SQLite-consistent, ZIP-integrity checked, and member-hash verified.

## Android / Termux

The Python runtime is portable. On Android, Termux is only a host; it is not part of HAKIM's identity. Install Termux from one consistent source, install Python, clone/copy this repository, and use a locally built llama.cpp binary. Once the repository, Python environment, model weights, and llama.cpp binary are present locally, normal operation does not require ChatGPT, GitHub, or internet connectivity.

## Disaster recovery

Keep at least two offline copies on physically distinct storage when possible. A backup is not trusted until `VerifiedBackupManager.verify()` succeeds. Restore into a new directory first; overwriting a non-empty target is denied by default.

## Boundary

Absolute independence is physically impossible: execution still needs hardware, power, an OS/runtime, and model files. The engineering objective is therefore **provider/platform independence with user-owned state, inference, recovery, and artifacts**.
