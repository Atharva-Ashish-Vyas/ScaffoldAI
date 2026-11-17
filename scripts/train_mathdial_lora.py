import argparse
import json
from pathlib import Path

p = argparse.ArgumentParser()
p.add_argument("--examples", default="data/pedagogy_datasets/processed/mathdial_style_sft.jsonl")
p.add_argument("--model", default="Qwen/Qwen2.5-1.5B-Instruct")
p.add_argument("--output", default="results/mathdial_lora")
p.add_argument("--epochs", type=int, default=1)
a = p.parse_args()

import torch
if not torch.cuda.is_available():
    raise SystemExit("LoRA fine-tuning requires a CUDA GPU in this script. On a Mac, prepare the data locally and train on a compatible GPU machine; Ollama inference still works on Mac.")

from datasets import Dataset
from peft import LoraConfig, get_peft_model
from transformers import AutoModelForCausalLM, AutoTokenizer, Trainer, TrainingArguments, DataCollatorForLanguageModeling

items = [json.loads(line) for line in Path(a.examples).read_text(encoding="utf-8").splitlines() if line.strip()]
if not items:
    raise SystemExit("No training examples")
tokenizer = AutoTokenizer.from_pretrained(a.model)
if tokenizer.pad_token is None:
    tokenizer.pad_token = tokenizer.eos_token
model = AutoModelForCausalLM.from_pretrained(a.model, torch_dtype=torch.float16, device_map="auto")
model = get_peft_model(model, LoraConfig(r=8, lora_alpha=16, lora_dropout=0.05, target_modules=["q_proj", "v_proj"], task_type="CAUSAL_LM"))

def encode(item):
    prompt = tokenizer.apply_chat_template([{"role": "system", "content": item["system"]}, {"role": "user", "content": item["user"]}], tokenize=False, add_generation_prompt=True)
    full = prompt + item["assistant"] + tokenizer.eos_token
    all_tokens = tokenizer(full, truncation=True, max_length=512)
    prefix = tokenizer(prompt, truncation=True, max_length=512)["input_ids"]
    all_tokens["labels"] = [-100] * min(len(prefix), len(all_tokens["input_ids"])) + all_tokens["input_ids"][len(prefix):]
    return all_tokens

dataset = Dataset.from_list(items).map(encode, remove_columns=list(items[0]))
training = TrainingArguments(output_dir=a.output, num_train_epochs=a.epochs, per_device_train_batch_size=1, gradient_accumulation_steps=8, learning_rate=2e-4, logging_steps=10, save_strategy="epoch", fp16=True, report_to="none")
trainer = Trainer(model=model, args=training, train_dataset=dataset)
trainer.train()
trainer.save_model(a.output)
tokenizer.save_pretrained(a.output)
print("Saved LoRA adapter:", a.output)
