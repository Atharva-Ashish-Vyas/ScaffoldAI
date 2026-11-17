# ScaffoldAI - ML Research MVP

**Windows users:** See [WINDOWS_SETUP.md](WINDOWS_SETUP.md) and run `setup_windows.bat`, then `start_windows.bat`. The app is cross-platform; the `.sh` scripts below are for macOS/Linux only.

Educational research prototype. No claim of validated learning improvement. University Machine Learning course is the initial domain; MathDial is a teaching-style source only.

## Mac setup

1. Unzip into a new folder. Leave any previous ScaffoldAI folder untouched.
2. Open Terminal and `cd` into `ScaffoldAI_Research_MVP`.
3. `chmod +x setup_mac.sh start_mac.sh`
4. `./setup_mac.sh`
5. Edit `.env` and change `SCAFFOLD_ADMIN_PASSWORD` from the example value. Keep it private.
6. `./start_mac.sh`
7. Student dashboard: http://127.0.0.1:8000 ; Faculty: http://127.0.0.1:8000/faculty

Default `SCAFFOLD_MODE=mock` tests wiring but is not actual AI. For local Ollama, run `ollama pull llama3.2` and set `SCAFFOLD_MODE=live` in `.env` before restarting. You need Ollama running separately. Never add a real API key to shared files.

## ML slides and faculty approval

The supplied `unit1_slides.pdf` is placed in `data/course_notes/raw/` as an **unapproved source**. It does NOT automatically become factual evidence. In the faculty dashboard, upload it if not already indexed, review its contents, then approve it. You can alternatively index from Terminal with `PYTHONPATH=. .venv/bin/python scripts/ingest_notes.py data/course_notes/raw/unit1_slides.pdf --course ML --topic General` and approve in the faculty dashboard. Ingesting all 373 pages can take some time. A scanned slide without extracted text requires OCR, which is not included. Other supported types are PDF, PPTX, DOCX and TXT.

Retrieval uses an offline hashed lexical-vector index stored in SQLite, not a pretrained semantic embedding model. It is transparent and testable but weaker than modern semantic retrieval. Questions with no sufficiently matching approved note evidence are refused.

## Add and approve a question

Open `/faculty`, enter the password from `.env`, paste a question JSON in the provided editor and save it as a draft. Review the rubric and exam hints, then click Approve. Students can select the approved question in the dashboard. For Normal Chat, students can also enter their own question, but scoring requires an approved faculty rubric.

## Three student modes

- Normal Chat: retrieve approved ML notes, diagnose student state, generate a guided question or progressively requested hint. On final submission, display provisional rubric results and ideal answer if a faculty question was selected.
- Exam Mode: faculty-approved question and preapproved hints only. The implementation withholds score, answer, correction and rubric from the student at all times. The final submission returns only a confirmation.
- Independent QnA: no AI agent is called during the student's attempt. Final submission returns only a confirmation. Faculty can inspect and grade the result.

## MathDial and other datasets

MathDial original repo: https://github.com/eth-nlped/mathdial ; license: CC BY 4.0 according to its current README. Download its `data/train.jsonl` or `data/example.jsonl` yourself and put it in `data/pedagogy_datasets/mathdial/`. Import: `PYTHONPATH=. .venv/bin/python scripts/import_pedagogy.py mathdial data/pedagogy_datasets/mathdial/example.jsonl`. For KELE and SocraTeach, obtain the datasets from the authors, review their license, put them in their respective directories, then use the same importer with their dataset name. Parsers work best with MathDial-style teacher turns; unfamiliar KELE/SocraTeach schemas may produce zero examples and require an adapter. No public dataset is used as an ML factual source. The filtered example bank is deliberately conservative and may retain very few prompts.

### Optional actual fine-tuning with MathDial

MathDial is a mathematics tutoring dataset, not ML course knowledge. The repository contains an optional LoRA script for learning its dialogue-teaching style. This model has **not been trained or evaluated by this project**. First prepare examples:

`python scripts/prepare_mathdial_sft.py data/pedagogy_datasets/mathdial/train.jsonl`

On a compatible CUDA machine, install `torch>=2.3,<3 transformers>=4.45,<5 datasets>=3,<4 peft>=0.13,<1 accelerate>=1,<2`, then run:

`python scripts/train_mathdial_lora.py --examples data/pedagogy_datasets/processed/mathdial_style_sft.jsonl`

The output is a PEFT adapter that requires a compatible inference server; setting `SCAFFOLD_MODEL` to the adapter path alone does **not** automatically make Ollama load it. Perform held-out validation, review MathDial license/attribution, serve the resulting model through an OpenAI-compatible endpoint, and then point `.env` to that serving endpoint. The Mac default uses the already downloaded `llama3.2` without fine-tuning.

## KELE baseline runner

`PYTHONPATH=. .venv/bin/python -m kele_baseline.run_baseline --dataset data/pedagogy_datasets/kele/SocratDataset.json --limit 5`

This provides audit logs for a simplified Consultant/Teacher flow, not a reproduction of KELE's trained SocratTeachLLM results. For paper-level reproduction, reproduce model weights, splits, Chinese-language conditions and reported evaluation metrics separately.

## Faculty operations

View and approve notes and question rubrics, inspect anonymous student sessions, view internal traces, grade submissions by submission ID, save feedback, and export CSV. Admin access is a shared development-only password. This is **not production-grade authentication**. Student IDs are pseudonyms but not verified identities, and the app must be used only on a trusted local computer.

## Testing

`PYTHONPATH=. .venv/bin/python -m pytest -q`

Tests use a mock LLM and do not require Ollama. Results here must not be described as proof of learning gains. Rubric scoring uses aliases and hashed lexical similarity, not a validated semantic grader. The response validator is heuristic and cannot guarantee factual entailment or prevent every type of leakage. Faculty review and a held-out test set are required.

## Research evaluation next

Run identical ML problems with: (1) direct-answer LLM, (2) prompt-only Socratic LLM, (3) three-role ScaffoldAI. Blindly annotate misconception correctness, action appropriateness, repetition, answer leakage and human-assessed student learning on new questions. Report latency and uncertainty. No comparative experiment is claimed yet.
