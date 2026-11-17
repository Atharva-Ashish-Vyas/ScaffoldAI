import argparse
import csv
import json
import re
from pathlib import Path

p = argparse.ArgumentParser()
p.add_argument("input")
p.add_argument("--output", default="data/pedagogy_datasets/processed/mathdial_style_sft.jsonl")
a = p.parse_args()
source = Path(a.input)
if source.suffix == ".csv":
    with source.open(encoding="utf-8", newline="") as f:
        records = list(csv.DictReader(f))
else:
    records = [json.loads(x) for x in source.read_text(encoding="utf-8").splitlines() if x.strip()]
output = Path(a.output)
output.parent.mkdir(parents=True, exist_ok=True)
count = 0
with output.open("w", encoding="utf-8") as stream:
    for record in records:
        history = []
        for turn in record.get("conversation", "").split("|EOM|"):
            match = re.match(r"(Teacher|Student):\s*(?:\(([^)]+)\))?\s*(.*)", turn.strip(), re.I | re.S)
            if not match:
                continue
            role, action, text = match.groups()
            text = re.sub(r"\s+", " ", text).strip()
            if role.lower() == "teacher" and history and text and text.endswith("?") and len(text) <= 240:
                item = {"system": "You are a Socratic teacher. Use the student's reasoning to select a targeted pedagogical question. Do not give a direct answer.", "user": "\n".join(history[-4:]), "assistant": text, "dataset": "mathdial", "question_id": str(record.get("qid", ""))}
                stream.write(json.dumps(item, ensure_ascii=False) + "\n")
                count += 1
            if text:
                history.append(f"{role}: {text}")
print(f"Prepared {count} MathDial tutor-style supervised examples: {output}. They contain math-context training text, so do NOT treat the trained model as an ML factual source.")
