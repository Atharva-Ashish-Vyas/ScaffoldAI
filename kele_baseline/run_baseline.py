import argparse
import json
import time
from pathlib import Path
from app.agents import Provider

p = argparse.ArgumentParser()
p.add_argument("--dataset", required=True)
p.add_argument("--output", default="results/kele_baseline.jsonl")
p.add_argument("--limit", type=int, default=5)
a = p.parse_args()
data = json.loads(Path(a.dataset).read_text(encoding="utf-8"))
if isinstance(data, dict):
    data = data.get("data", data.get("dialogues", [data]))
provider = Provider()
out = Path(a.output)
out.parent.mkdir(parents=True, exist_ok=True)
with out.open("w", encoding="utf-8") as stream:
    for i, record in enumerate(data[:a.limit]):
        start = time.perf_counter()
        prompt = json.dumps(record, ensure_ascii=False)[:1500]
        consultant = provider.generate("Return JSON for Socratic teaching state and recommended teaching action. Do not solve problem.", prompt)
        teacher = provider.generate("Follow consultant action. Ask one Socratic question without giving an answer.", consultant + "\n" + prompt)
        stream.write(json.dumps({"dialogue_id": str(record.get("id", record.get("qid", i))), "consultant": consultant, "teacher": teacher, "latency_ms": round((time.perf_counter()-start)*1000, 1), "model": provider.model, "mode": "live" if provider.live else "mock"}, ensure_ascii=False) + "\n")
print(f"Saved {out}. Simplified baseline only; not official KELE reproduction or published scores.")
