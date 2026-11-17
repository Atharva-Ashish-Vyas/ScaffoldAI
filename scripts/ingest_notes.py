import argparse
from pathlib import Path
from app.storage import init
from app.retrieval import ingest

p = argparse.ArgumentParser()
p.add_argument("path", type=Path)
p.add_argument("--course", default="ML")
p.add_argument("--topic", default="General")
p.add_argument("--approve", action="store_true")
a = p.parse_args()
init()
print(ingest(a.path, a.course, a.topic, a.approve))
