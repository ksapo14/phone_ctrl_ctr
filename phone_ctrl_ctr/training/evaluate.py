"""Generate strict function calls and score held-out commands. Never executes them."""
import argparse
import json
from collections import Counter
from pathlib import Path
from functions import SYSTEM, TOOLS, parse_output, to_command
from train import load_data


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model", required=True, help="output/final, checkpoint directory, or base model ID")
    parser.add_argument("--revision", default="main")
    parser.add_argument("--data", type=Path, default=Path(__file__).resolve().parent / "data")
    parser.add_argument("--text", help="Route one transcript instead of evaluating the test split")
    parser.add_argument("--report", type=Path, default=Path("evaluation.json"))
    args = parser.parse_args()
    import torch
    from transformers import AutoModelForCausalLM, AutoTokenizer
    device = "cuda" if torch.cuda.is_available() else "cpu"
    tokenizer = AutoTokenizer.from_pretrained(args.model, revision=args.revision)
    tokenizer.padding_side = "left"
    model = AutoModelForCausalLM.from_pretrained(args.model, revision=args.revision,
        dtype=torch.bfloat16 if device == "cuda" else torch.float32).to(device).eval()
    saved_tools = Path(args.model) / "tools.json"
    if saved_tools.exists() and json.loads(saved_tools.read_text(encoding="utf-8")) != TOOLS:
        raise ValueError("Model tool schema differs from the current adapter")
    stop_ids = [tokenizer.eos_token_id]
    for token in ("<start_function_response>", "<end_of_turn>"):
        token_id = tokenizer.convert_tokens_to_ids(token)
        if token_id is not None and token_id != tokenizer.unk_token_id: stop_ids.append(token_id)

    def route(text):
        messages = [{"role": "developer", "content": SYSTEM}, {"role": "user", "content": text}]
        inputs = tokenizer.apply_chat_template(messages, tools=TOOLS, add_generation_prompt=True,
            return_dict=True, return_tensors="pt").to(device)
        with torch.inference_mode():
            output = model.generate(**inputs, do_sample=False, max_new_tokens=160,
                eos_token_id=list(set(stop_ids)), pad_token_id=tokenizer.pad_token_id or tokenizer.eos_token_id)
        raw = tokenizer.decode(output[0][inputs["input_ids"].shape[-1]:], skip_special_tokens=False)
        try:
            call = parse_output(raw)
            return {"raw": raw, "function": call, "command": to_command(call["name"], call["arguments"]), "valid": True}
        except ValueError as error:
            return {"raw": raw, "valid": False, "error": str(error), "command": None}

    if args.text is not None:
        print(json.dumps(route(args.text), indent=2)); return
    rows = load_data(args.data)["test"]
    counts = Counter()
    by_function = {}
    predictions = []
    for row in rows:
        prediction = route(row["utterance"])
        expected = row["messages"][-1]["tool_calls"][0]["function"]
        exact = prediction.get("function") == expected
        named = prediction.get("function", {}).get("name") == expected["name"]
        counts["total"] += 1; counts["valid"] += prediction["valid"]
        counts["exact"] += exact; counts["function_name"] += named
        counts["unsafe_action_on_no_action"] += expected["name"] == "no_action" and prediction["command"] is not None
        bucket = by_function.setdefault(expected["name"], {"total": 0, "exact": 0})
        bucket["total"] += 1; bucket["exact"] += exact
        predictions.append({"utterance": row["utterance"], "expected": expected, "exact": exact, **prediction})
    metrics = {**counts, "exact_accuracy": counts["exact"] / counts["total"],
               "valid_rate": counts["valid"] / counts["total"], "by_function": by_function,
               "macro_function_accuracy": sum(b["exact"] / b["total"] for b in by_function.values()) / len(by_function)}
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps({"model": args.model, "metrics": metrics, "predictions": predictions}, indent=2), encoding="utf-8")
    print(json.dumps(metrics, indent=2))


if __name__ == "__main__": main()
