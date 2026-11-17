# ScaffoldAI Research MVP - Windows 10/11 Setup Guide

This is the **Machine Learning** version of ScaffoldAI. It includes the 373-slide ML PDF and its unapproved local course-note index, student and faculty dashboards, three runtime roles, three learning modes, a SQLite database, and an optional Ollama connection. This is a local educational research prototype, **not** a production-grade application or a proven learning intervention.

## 1. Prerequisites

- Windows 10 or 11, 64-bit.
- Python **3.10.x** from https://www.python.org/downloads/ (recommended for this package). During installation, enable the **Python Launcher**. Keeping a different Python version installed is okay; the commands explicitly select 3.10.
- Internet access for Python dependencies and, if you want live AI, for downloading an Ollama model.
- Enough disk space for a Python virtual environment, the 43 MB slide PDF, and your Ollama model (several GB).
- Optional: Ollama for Windows from https://ollama.com/download . You do not need Ollama for the mock-mode software tests.

Open **PowerShell** (Windows key, type `PowerShell`, press Enter), then check:

```powershell
py -3.10 --version
```

Expected: `Python 3.10.x`. If it says Python cannot be found, install Python 3.10 with the launcher, reopen PowerShell, and run the command again.

## 2. Extract the ZIP

1. Download the shared `ScaffoldAI_ML_Windows_Ready.zip`.
2. In File Explorer, right-click the ZIP and choose **Extract All**.
3. Open the extracted **ScaffoldAI_Research_MVP** folder. You should see `app`, `data`, `static`, `setup_windows.bat`, and `start_windows.bat` directly inside it.
4. Click the File Explorer address bar, type `powershell`, and press Enter. PowerShell opens in that exact folder.

**Do not run the project from inside the ZIP viewer.** Extract it first.

## 3. Install Python dependencies without changing your other Python installations

In that PowerShell window, run:

```powershell
.\setup_windows.bat
```

The script creates `.venv` **inside this project only**, installs dependencies there, creates `.env` if it is missing, and runs the automated tests. It does not uninstall or replace any existing Python installation.

Expected final messages include `7 passed` (or more tests in later versions) and `Setup completed`.

If PowerShell cannot find the script, check that you're inside the folder containing `setup_windows.bat` with `Get-ChildItem`.

If the Python launcher is unavailable but Python 3.10 is installed, use these manual commands instead:

```powershell
python --version
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
Copy-Item .env.example .env
.\.venv\Scripts\python.exe -m pytest -q
```

Only use this fallback when `python --version` shows 3.10.x. You do not need to activate the environment with `Activate.ps1`.

## 4. Configure the faculty password and choose mock/live model

Run:

```powershell
notepad .env
```

For your first **mock-mode** test, edit it to resemble this (replace the password with your own private password):

```dotenv
SCAFFOLD_MODE=mock
SCAFFOLD_MODEL=llama3.2
SCAFFOLD_API_BASE=http://127.0.0.1:11434/v1
SCAFFOLD_API_KEY=ollama
SCAFFOLD_ADMIN_PASSWORD=ReplaceThisWithYourPrivatePassword
```

Save and close Notepad. **Never put the real `.env` on GitHub or share it in screenshots.**

In mock mode, the software flow works but replies are canned and don't represent real AI performance.

### To enable real AI using Ollama

1. Install and open Ollama for Windows.
2. In a second PowerShell window, run `ollama pull llama3.2` (or `ollama pull qwen3.5:4b` if preferred).
3. Test: `ollama run llama3.2` and ask a short question, then exit with `/bye`.
4. Edit `.env` to set `SCAFFOLD_MODE=live`. Set `SCAFFOLD_MODEL=llama3.2` or exactly `qwen3.5:4b`, matching what you downloaded.
5. Keep Ollama running. No paid API key is needed for local Ollama.

**Note:** Three sequential roles are orchestrated per turn; two can call the language model, with a possible rewrite call. On slower computers, replies can take a while. Wait for the current response; do not click Send repeatedly. The UI in this version does not yet have a full request-in-progress lock.

## 5. Start ScaffoldAI

Back in the project folder's PowerShell window:

```powershell
.\start_windows.bat
```

Expected output includes `Uvicorn running on http://127.0.0.1:8000`.

Open these addresses on the **same Windows computer**:

- Student dashboard: http://127.0.0.1:8000
- Faculty dashboard: http://127.0.0.1:8000/faculty
- Backend health: http://127.0.0.1:8000/api/health

The health page should report `status: ok`, `course: ML`, and the chosen model mode. `live` confirms configuration, **not** that Ollama successfully generated a response.

To stop the backend, return to the PowerShell window running Uvicorn and press **Ctrl+C**.

If port 8000 is already in use, stop the earlier ScaffoldAI backend before starting this version.

## 6. Faculty login and approve ML notes

1. Open `/faculty`.
2. In **Local faculty access**, enter the password you set in `.env`.
3. Click **Load data**. You should see `Loaded`.
4. Scroll to **Course notes** and locate `unit1_slides.pdf`, `ML / General`, approximately `375 chunks`, marked `UNAPPROVED`.
5. Confirm that this is the correct Machine Learning material; click **Approve**.
6. Verify its status changes to `APPROVED`.

If the PDF isn't listed, use the **Course notes** upload form with Course `ML`, Topic `General`, and select `data/course_notes/raw/unit1_slides.pdf`. Click **Upload and index**, then approve it. Do not reupload when it is already listed.

The PDF is an educational source, **not a trained model**. It is indexed locally; approval lets the retrieval component cite relevant slide text.

## 7. Create a faculty-approved question

In `/faculty`, find **Question bank / rubric**. Replace the example JSON with the following, click **Save question draft**, then click **Approve** next to its entry:

```json
{
  "id": "ml-workflow-001",
  "course": "ML",
  "topic": "General",
  "question": "What are the seven main steps in the machine learning workflow?",
  "ideal_answer": "The steps are data collection, data preparation, choosing a model, training, evaluation, parameter tuning, and prediction.",
  "rubric_points": [
    {"criterion": "Data collection and preparation", "weight": 30, "accepted_concepts": ["data collection", "data preparation"]},
    {"criterion": "Choosing and training a model", "weight": 30, "accepted_concepts": ["choosing a model", "model selection", "training"]},
    {"criterion": "Evaluation and tuning", "weight": 25, "accepted_concepts": ["evaluation", "parameter tuning", "hyperparameter tuning"]},
    {"criterion": "Prediction", "weight": 15, "accepted_concepts": ["prediction", "predict"]}
  ],
  "allowed_exam_hints": {
    "level_1": "What should happen before a model can be trained?",
    "level_2": "Think about data, model choice, and training.",
    "level_3": "After training, consider evaluation, parameter tuning, and prediction."
  },
  "approved": false
}
```

This rubric is illustrative and the automated score is provisional. Check with faculty before using grades for research conclusions.

## 8. Test as a student

1. Open `/`.
2. Anonymous student ID: `student001`.
3. Course: `ML`; Topic: `General`.
4. Mode: **Normal Chat / Guided Learning**.
5. Select `ml-workflow-001` in **Faculty-approved question**. Leave the custom question blank.
6. Click **Start session**.
7. Enter: `I think we collect data, train a model, then predict. Do we need to evaluate it?`
8. Set Hint level to `Probe (no hint)` and click **Send / request hint** once.
9. Wait for the response. Check whether a source such as `unit1_slides.pdf, p./slide N` appears.
10. For progressive hints use Level 1, then Level 2, then Level 3 **in order**. You cannot skip directly to Level 3.
11. Submit a full answer using **Final submission**. A completed study session is locked; start a new session for more testing.

### Mode differences

- **Normal Chat:** AI tutoring plus provisional study feedback after final submission.
- **Exam Mode:** An approved question is required; only faculty-approved hints are shown. Scores, model diagnoses, solutions and rubric coverage are hidden from students.
- **Independent QnA:** No AI agent runs during the student's attempt. Only a submission confirmation appears; faculty can inspect the answer afterward.

## 9. Faculty grading and progress

- In `/faculty`, **Student sessions and grading** lists anonymous student IDs. Click **Inspect** to see a session and its submission ID.
- Enter the submission ID, faculty score (0–100), and feedback; click **Save faculty evaluation**.
- Use **Export CSV** to download anonymized research data. Keep it private.
- Students can select **Refresh progress** in their dashboard.

## 10. Run the tests later

Stop the server or open another PowerShell in the project folder. Run:

```powershell
.\test_windows.bat
```

The tests run with mocked LLM responses and require no Ollama connection.

## 11. Optional MathDial import, KELE baseline and training

MathDial: https://github.com/eth-nlped/mathdial . Obtain the source dataset separately under its license. Put `train.jsonl` in `data/pedagogy_datasets/mathdial/`.

```powershell
$env:PYTHONPATH = "."
.\.venv\Scripts\python.exe scripts\import_pedagogy.py mathdial data\pedagogy_datasets\mathdial\train.jsonl
.\.venv\Scripts\python.exe scripts\prepare_mathdial_sft.py data\pedagogy_datasets\mathdial\train.jsonl
```

The first command imports conservative, short tutor-style examples; it does not use math facts as ML evidence. The second creates examples for **optional LoRA fine-tuning**. Fine-tuning has **not** been run. The supplied training script requires a compatible CUDA GPU and additional ML packages; use the main README for the details. The three-agent application works without fine-tuning.

For the simplified KELE Consultant/Teacher baseline, put the original `SocratDataset.json` under `data/pedagogy_datasets/kele/` and run:

```powershell
$env:PYTHONPATH = "."
.\.venv\Scripts\python.exe -m kele_baseline.run_baseline --dataset data\pedagogy_datasets\kele\SocratDataset.json --limit 5
```

This baseline is a simplified reproduction scaffold, **not** the published KELE experiment or its results.

## 12. Troubleshooting

| Problem | What to check |
|---|---|
| `py` isn't recognized | Install the Python Launcher with Python 3.10; reopen PowerShell |
| `start_windows.bat` says virtual environment missing | Run `setup_windows.bat` first |
| `Faculty access denied` | Match `SCAFFOLD_ADMIN_PASSWORD` in `.env` |
| Approved notes not found | Check `/faculty` Course notes, `APPROVED`, and exact `ML / General` topic |
| No model response | Verify Ollama is running and the `.env` model matches `ollama list` |
| Slow response | Try a smaller model; wait for server logs; don't repeatedly click Send |
| Port 8000 in use | Stop any existing ScaffoldAI server with Ctrl+C |
| PowerShell blocks activation | This setup does not require `Activate.ps1`; use the provided `.bat` scripts |
| Independent mode has no hints | Expected by design |
| Exam mode hides grades | Expected by design |

## 13. Scope and limitations

This project currently uses a basic hashed lexical-vector retriever, not state-of-the-art pretrained semantic embeddings; grading uses rubric concept matches and lexical similarity, not validated semantic assessment. The answer-leakage filter is heuristic. Student IDs are not authenticated. The faculty shared password is suitable only for a private local development demo. It is **not** verified as production-secure, pedagogically effective, or capable of reproducing paper-level benchmark scores.

### What has and hasn't been verified

- Verified in the development environment: Python unit/integration tests and JavaScript syntax; note ingestion and the ZIP archive.
- Not verified on a physical Windows PC in this environment: Windows shell execution, local Ollama performance, or the full GUI workflow. Your friend should run the smoke test above and report errors if any.
