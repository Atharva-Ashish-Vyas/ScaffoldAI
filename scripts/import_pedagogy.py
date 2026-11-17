import argparse
from app.storage import init
from app.pedagogy import import_dataset

p = argparse.ArgumentParser()
p.add_argument("dataset", choices=["mathdial", "kele", "socrateach"])
p.add_argument("path")
a = p.parse_args()
init()
print(import_dataset(a.path, a.dataset))
