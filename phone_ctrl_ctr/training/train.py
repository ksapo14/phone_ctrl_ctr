"""Full BF16 FunctionGemma fine-tuning on one or many H200s via torchrun."""
import argparse
import hashlib
import json
import os
import platform
import random
from collections import defaultdict
from pathlib import Path
from functions import TOOLS, SYSTEM, to_command

ROOT = Path(__file__).resolve().parent


def balance_rows(rows, seed):
    """Deterministically repeat rare functions for DDP's ordinary distributed sampler."""
    buckets = defaultdict(list)
    for row in rows: buckets[row["messages"][-1]["tool_calls"][0]["function"]["name"]].append(row)
    size = max(map(len, buckets.values()))
    rng = random.Random(seed)
    result = []
    for bucket in buckets.values():
        shuffled = bucket.copy(); rng.shuffle(shuffled)
        result.extend(shuffled[i % len(shuffled)] for i in range(size))
    rng.shuffle(result)
    return result


def load_data(directory):
    splits = {}
    texts, groups = set(), set()
    manifest = json.loads((directory / "manifest.json").read_text(encoding="utf-8"))
    tools = json.loads((directory / "tools.json").read_text(encoding="utf-8"))
    if tools != TOOLS: raise ValueError("tools.json differs from functions.py; rebuild data")
    for split in ("train", "validation", "test"):
        raw = (directory / f"{split}.jsonl").read_bytes()
        if hashlib.sha256(raw).hexdigest() != manifest["splits"][split]["sha256"]:
            raise ValueError(f"{split} checksum mismatch; regenerate/update the manifest")
        rows = [json.loads(line) for line in raw.decode("utf-8").splitlines() if line.strip()]
        if len(rows) != manifest["splits"][split]["count"]: raise ValueError("Manifest row count mismatch")
        if not rows: raise ValueError(f"Empty {split} split")
        split_groups = set()
        for row in rows:
            messages = row["messages"]
            if len(messages) != 3 or messages[0] != {"role": "developer", "content": SYSTEM}:
                raise ValueError("Expected developer, user, assistant conversation")
            if messages[1] != {"role": "user", "content": row["utterance"]} or messages[2]["role"] != "assistant":
                raise ValueError("Invalid conversation roles/content")
            calls = messages[2]["tool_calls"]
            if len(calls) != 1 or calls[0]["type"] != "function": raise ValueError("One call required")
            call = calls[0]["function"]
            if to_command(call["name"], call["arguments"]) != row["expected_command"]: raise ValueError("Packet mismatch")
            text = row["utterance"].casefold().strip()
            if text in texts: raise ValueError("Duplicate utterance or split leakage")
            texts.add(text)
            if row["group"] in groups: raise ValueError("Phrasing family split leakage")
            split_groups.add(row["group"])
        groups.update(split_groups)
        splits[split] = rows
    return splits


def encode_row(tokenizer, row, max_length):
    prompt = tokenizer.apply_chat_template(row["messages"][:-1], tools=TOOLS, tokenize=True, add_generation_prompt=True)
    full = tokenizer.apply_chat_template(row["messages"], tools=TOOLS, tokenize=True, add_generation_prompt=False)
    if full[:len(prompt)] != prompt: raise ValueError("Chat template prompt is not an exact prefix; refuse incorrect masking")
    if len(full) > max_length: raise ValueError(f"Example {row['id']} has {len(full)} tokens, exceeding --max-length; no silent truncation")
    if len(full) <= len(prompt): raise ValueError("No assistant target tokens")
    return {"input_ids": full, "attention_mask": [1] * len(full), "labels": [-100] * len(prompt) + full[len(prompt):]}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model", default="google/functiongemma-270m-it")
    parser.add_argument("--revision", default="main", help="Pin a Hub commit hash for exact reproducibility")
    parser.add_argument("--data", type=Path, default=ROOT / "data")
    parser.add_argument("--output", type=Path, default=ROOT / "output")
    parser.add_argument("--epochs", type=float, default=5)
    parser.add_argument("--batch-size", type=int, default=4)
    parser.add_argument("--grad-accum", type=int, default=4)
    parser.add_argument("--learning-rate", type=float, default=2e-5)
    parser.add_argument("--max-length", type=int, default=4096)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--balance-functions", action=argparse.BooleanOptionalAction, default=True,
                        help="Repeat rare function examples so percentages do not dominate training")
    parser.add_argument("--max-steps", type=int, default=-1, help="Set to 2 for a cluster smoke test")
    parser.add_argument("--resume", help="Path to checkpoint-N")
    parser.add_argument("--check-data", action="store_true", help="Validate data without ML dependencies or a GPU")
    parser.add_argument("--check-tokenization", action="store_true", help="Download tokenizer only and validate loss masks/lengths")
    args = parser.parse_args()
    splits = load_data(args.data)
    if args.check_data:
        print(json.dumps({key: len(rows) for key, rows in splits.items()})); return

    import torch
    import transformers
    from transformers import AutoTokenizer, AutoModelForCausalLM, Trainer, TrainingArguments, DataCollatorForSeq2Seq, set_seed
    set_seed(args.seed)
    tokenizer = AutoTokenizer.from_pretrained(args.model, revision=args.revision)
    if tokenizer.pad_token_id is None: tokenizer.pad_token = tokenizer.eos_token
    tokenizer.padding_side = "right"
    encoded = {key: [encode_row(tokenizer, row, args.max_length) for row in rows] for key, rows in splits.items()}
    if args.check_tokenization:
        print(json.dumps({key: {"count": len(rows), "max_tokens": max(len(row["input_ids"]) for row in rows)} for key, rows in encoded.items()})); return
    if not torch.cuda.is_available() or not torch.cuda.is_bf16_supported():
        raise RuntimeError("Training requires CUDA with BF16 support; run on the H200 cluster")
    local_rank = int(os.environ.get("LOCAL_RANK", "0"))
    torch.cuda.set_device(local_rank)
    distributed = int(os.environ.get("WORLD_SIZE", "1")) > 1
    if distributed: torch.distributed.init_process_group(backend="nccl")
    occupied = [args.output.exists() and any(args.output.iterdir()) and not args.resume]
    if distributed: torch.distributed.broadcast_object_list(occupied, src=0)
    if occupied[0]:
        raise ValueError("Output is nonempty; use a new --output directory or --resume checkpoint")
    if args.balance_functions:
        encoded["train"] = [encode_row(tokenizer, row, args.max_length) for row in balance_rows(splits["train"], args.seed)]
    # DDP owns device placement. Never use device_map='auto' for torchrun training.
    model = AutoModelForCausalLM.from_pretrained(args.model, revision=args.revision,
        dtype=torch.bfloat16, attn_implementation="sdpa")
    model.config.use_cache = False
    training_args = TrainingArguments(
        output_dir=str(args.output), num_train_epochs=args.epochs, max_steps=args.max_steps,
        per_device_train_batch_size=args.batch_size, per_device_eval_batch_size=args.batch_size,
        gradient_accumulation_steps=args.grad_accum, learning_rate=args.learning_rate,
        bf16=True, tf32=True, optim="adamw_torch_fused", weight_decay=0.01,
        warmup_ratio=0.05, lr_scheduler_type="cosine", max_grad_norm=1.0,
        gradient_checkpointing=True, gradient_checkpointing_kwargs={"use_reentrant": False},
        ddp_find_unused_parameters=False, ddp_timeout=1800,
        eval_strategy="epoch", save_strategy="epoch", save_total_limit=2,
        load_best_model_at_end=True, metric_for_best_model="eval_loss", greater_is_better=False,
        logging_steps=5, report_to="none", seed=args.seed, data_seed=args.seed,
        dataloader_num_workers=0, remove_unused_columns=False,
    )
    trainer = Trainer(model=model, args=training_args, processing_class=tokenizer,
        train_dataset=encoded["train"], eval_dataset=encoded["validation"],
        data_collator=DataCollatorForSeq2Seq(tokenizer, padding=True, pad_to_multiple_of=8, label_pad_token_id=-100))
    result = trainer.train(resume_from_checkpoint=args.resume)
    trainer.save_model(str(args.output / "final"))
    trainer.save_state()
    trainer.save_metrics("train", result.metrics)
    trainer.save_metrics("validation", trainer.evaluate())
    if trainer.is_world_process_zero():
        tokenizer.save_pretrained(args.output / "final")
        (args.output / "final" / "tools.json").write_text(json.dumps(TOOLS, indent=2), encoding="utf-8")
        metadata = {**vars(args), "world_size": int(os.environ.get("WORLD_SIZE", "1")),
            "global_batch_size": args.batch_size * args.grad_accum * int(os.environ.get("WORLD_SIZE", "1")),
            "torch": torch.__version__, "transformers": transformers.__version__, "python": platform.python_version(),
            "model_commit": getattr(model.config, "_commit_hash", None),
            "dataset_manifest": json.loads((args.data / "manifest.json").read_text(encoding="utf-8"))}
        (args.output / "run.json").write_text(json.dumps(metadata, indent=2, default=str), encoding="utf-8")
    if distributed: torch.distributed.destroy_process_group()


if __name__ == "__main__": main()
