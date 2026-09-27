import os
import re
import json
import argparse
from pathlib import Path

import torch

from datasets import Dataset
from transformers import (
    AutoTokenizer,
    AutoModelForCausalLM,
    set_seed,
)

from trl import (
    SFTTrainer,
    SFTConfig,
)


# ============================================================
# DEFAULT CONFIG
# ============================================================

MODEL_ID = "google/functiongemma-270m-it"

DEFAULT_TRAIN_FILE = "desktop_commands_train.jsonl"
DEFAULT_EVAL_FILE = "desktop_commands_eval.jsonl"

DEFAULT_OUTPUT_DIR = "./functiongemma-desktop-checkpoints"
DEFAULT_FINAL_DIR = "./functiongemma-desktop-model"

SEED = 42

LEARNING_RATE = 5e-5

# Dataset is much larger than Google's tiny demonstration,
# so start more conservatively than blindly doing 8 epochs.
DEFAULT_EPOCHS = 4

TRAIN_BATCH_SIZE = 16
EVAL_BATCH_SIZE = 16

GRADIENT_ACCUMULATION_STEPS = 1

# 7 tool schemas take significant context.
MAX_LENGTH = 1024

MAX_NEW_TOKENS = 128


# ============================================================
# ARGUMENTS
# ============================================================

parser = argparse.ArgumentParser()

parser.add_argument(
    "--train-file",
    default=DEFAULT_TRAIN_FILE,
)

parser.add_argument(
    "--eval-file",
    default=DEFAULT_EVAL_FILE,
)

parser.add_argument(
    "--output-dir",
    default=DEFAULT_OUTPUT_DIR,
)

parser.add_argument(
    "--final-dir",
    default=DEFAULT_FINAL_DIR,
)

parser.add_argument(
    "--epochs",
    type=int,
    default=DEFAULT_EPOCHS,
)

parser.add_argument(
    "--resume",
    default=None,
    help=(
        "Optional Trainer checkpoint directory "
        "to resume from."
    ),
)

args = parser.parse_args()


TRAIN_FILE = args.train_file
EVAL_FILE = args.eval_file

OUTPUT_DIR = args.output_dir
FINAL_MODEL_DIR = args.final_dir

NUM_EPOCHS = args.epochs


# ============================================================
# SEED
# ============================================================

set_seed(SEED)


# ============================================================
# HELPERS
# ============================================================

def load_jsonl(path):

    rows = []

    with open(
        path,
        "r",
        encoding="utf-8",
    ) as f:

        for line_number, line in enumerate(
            f,
            start=1,
        ):

            if not line.strip():
                continue

            try:
                rows.append(
                    json.loads(line)
                )

            except json.JSONDecodeError as e:

                raise ValueError(
                    f"Invalid JSON in "
                    f"{path}:{line_number}"
                ) from e

    return rows


def canonical_json(value):
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
    )


# ============================================================
# FILE CHECKS
# ============================================================

for path in [
    TRAIN_FILE,
    EVAL_FILE,
]:

    if not Path(path).exists():

        raise FileNotFoundError(
            f"{path} does not exist.\n"
            "Run make_dataset.py first."
        )


# ============================================================
# LOAD RAW DATA
# ============================================================

print("=" * 72)
print("FUNCTIONGEMMA DESKTOP ROUTER TRAINING")
print("=" * 72)

print("\nLoading datasets...")

raw_train = load_jsonl(TRAIN_FILE)
raw_eval = load_jsonl(EVAL_FILE)

print(
    f"Training examples: {len(raw_train)}"
)

print(
    f"Evaluation examples: {len(raw_eval)}"
)


# ============================================================
# VERIFY TOOL SCHEMAS ARE IDENTICAL
#
# You do NOT want some examples silently giving the model a
# different API surface.
# ============================================================

if len(raw_train) == 0:
    raise ValueError(
        "Training dataset is empty."
    )

EXPECTED_TOOLS = raw_train[0]["tools"]

expected_tools_json = canonical_json(
    EXPECTED_TOOLS
)


def verify_tool_schemas(rows, name):

    for i, row in enumerate(rows):

        if canonical_json(
            row["tools"]
        ) != expected_tools_json:

            raise ValueError(
                f"{name}[{i}] has different "
                f"tool definitions."
            )


verify_tool_schemas(
    raw_train,
    "train",
)

verify_tool_schemas(
    raw_eval,
    "eval",
)

print("Tool schemas: consistent")


# ============================================================
# RUNTIME CALL VALIDATION
# ============================================================

ALLOWED_APPS = {
    "chrome",
    "chatgpt",
    "spotify",
    "vscode",
    "command_prompt",
    "file_explorer",
    "notion",
    "settings",
}

ALLOWED_SITES = {
    "google_drive",
    "github",
    "google_docs",
    "youtube",
}

ALLOWED_FUNCTIONS = {
    "start_app",
    "set_volume",
    "set_brightness",
    "pause_media",
    "play_media",
    "skip_media",
    "open_website",
}


def validate_function_call(
    name,
    arguments,
):

    if name not in ALLOWED_FUNCTIONS:

        return (
            False,
            f"Unknown function: {name}",
        )

    if not isinstance(arguments, dict):

        return (
            False,
            "Arguments must be an object",
        )

    if name == "start_app":

        if set(arguments.keys()) != {"app"}:

            return (
                False,
                "start_app requires only app",
            )

        if arguments["app"] not in ALLOWED_APPS:

            return (
                False,
                "Unsupported app",
            )

    elif name in {
        "set_volume",
        "set_brightness",
    }:

        if set(arguments.keys()) != {"level"}:

            return (
                False,
                f"{name} requires only level",
            )

        level = arguments["level"]

        if type(level) is not int:

            return (
                False,
                "level must be an integer",
            )

        if not 0 <= level <= 100:

            return (
                False,
                "level must be between 0 and 100",
            )

    elif name == "open_website":

        if set(arguments.keys()) != {"site"}:

            return (
                False,
                "open_website requires only site",
            )

        if arguments["site"] not in ALLOWED_SITES:

            return (
                False,
                "Unsupported website",
            )

    else:

        if arguments:

            return (
                False,
                f"{name} does not accept arguments",
            )

    return True, None


def validate_dataset_calls(
    rows,
    name,
):

    for row_index, row in enumerate(rows):

        assistant = row["messages"][-1]

        if assistant["role"] != "assistant":

            raise ValueError(
                f"{name}[{row_index}] "
                "doesn't end with assistant"
            )

        calls = assistant.get(
            "tool_calls",
            [],
        )

        if not calls:

            raise ValueError(
                f"{name}[{row_index}] "
                "contains no tool calls"
            )

        for call in calls:

            function = call["function"]

            valid, error = validate_function_call(
                function["name"],
                function.get(
                    "arguments",
                    {},
                ),
            )

            if not valid:

                raise ValueError(
                    f"{name}[{row_index}] "
                    f"has invalid call: {error}"
                )


validate_dataset_calls(
    raw_train,
    "train",
)

validate_dataset_calls(
    raw_eval,
    "eval",
)

print("Dataset calls: valid")


# ============================================================
# HARD TRAIN / EVAL LEAKAGE CHECK
# ============================================================

def normalized_prompt(row):

    for message in row["messages"]:

        if message["role"] == "user":

            return " ".join(
                message["content"]
                .lower()
                .strip()
                .split()
            )

    raise ValueError(
        "Example contains no user message"
    )


train_prompts = {
    normalized_prompt(row)
    for row in raw_train
}

eval_prompts = {
    normalized_prompt(row)
    for row in raw_eval
}

overlap = train_prompts & eval_prompts

if overlap:

    raise ValueError(
        "Train/eval leakage detected:\n"
        + "\n".join(sorted(overlap))
    )

print("Train/eval leakage: none")


# ============================================================
# DEVICE / PRECISION
# ============================================================

print("\nHardware:")

if torch.cuda.is_available():

    print(
        "  GPU:",
        torch.cuda.get_device_name(0),
    )

    BF16 = torch.cuda.is_bf16_supported()

    if BF16:
        MODEL_DTYPE = torch.bfloat16
        print("  Precision: BF16")

    else:
        MODEL_DTYPE = torch.float16
        print("  Precision: FP16")

else:

    MODEL_DTYPE = torch.float32
    BF16 = True

    print("  GPU: none")
    print("  Precision: FP32")


# ============================================================
# LOAD TOKENIZER
# ============================================================

print("\nLoading tokenizer...")

tokenizer = AutoTokenizer.from_pretrained(
    MODEL_ID,
)

if tokenizer.pad_token_id is None:

    tokenizer.pad_token = tokenizer.eos_token

tokenizer.padding_side = "right"


# ============================================================
# LOAD MODEL
#
# Do NOT use device_map="auto" here.
# Trainer/Accelerate should manage placement during training.
# ============================================================

print("Loading model...")

model = AutoModelForCausalLM.from_pretrained(
    MODEL_ID,
    dtype=MODEL_DTYPE,
    attn_implementation="eager",
)

model.config.use_cache = False


# ============================================================
# VERIFY CHAT TEMPLATE VISUALLY
# ============================================================

print("\nExample formatted training conversation:\n")

example_text = tokenizer.apply_chat_template(
    raw_train[0]["messages"],
    tools=raw_train[0]["tools"],
    add_generation_prompt=False,
    tokenize=False,
)

print(example_text[:5000])


# ============================================================
# COMPLETION-ONLY TOKENIZATION
#
# This is one of the biggest improvements over the old script.
#
# We create:
#
# PROMPT:
#   developer + tools + user + model-start token
#
# FULL:
#   developer + tools + user + model function call
#
# labels:
#   -100 for every prompt token
#   real token IDs ONLY for the function-call completion
#
# CrossEntropy ignores -100.
# ============================================================

def common_prefix_length(a, b):

    length = min(
        len(a),
        len(b),
    )

    i = 0

    while (
        i < length
        and a[i] == b[i]
    ):
        i += 1

    return i


def tokenize_training_example(row):

    messages = row["messages"]
    tools = row["tools"]

    if (
        messages[-1]["role"]
        != "assistant"
    ):

        raise ValueError(
            "Final message must be assistant."
        )

    prompt_messages = messages[:-1]

    # Prompt ending directly before the assistant's output.
    prompt_ids = tokenizer.apply_chat_template(
        prompt_messages,
        tools=tools,
        add_generation_prompt=True,
        tokenize=True,
    )

    # Complete training conversation.
    full_ids = tokenizer.apply_chat_template(
        messages,
        tools=tools,
        add_generation_prompt=False,
        tokenize=True,
    )

    prefix_len = common_prefix_length(
        prompt_ids,
        full_ids,
    )

    # Normally these should be either identical
    # through the entire prompt or extremely close.
    prefix_ratio = (
        prefix_len
        / max(1, len(prompt_ids))
    )

    if prefix_ratio < 0.95:

        raise RuntimeError(
            "\nFunctionGemma prompt/full template "
            "mismatch detected.\n"
            f"Prompt tokens: {len(prompt_ids)}\n"
            f"Common prefix: {prefix_len}\n"
            f"Ratio: {prefix_ratio:.3f}\n"
            "\nRefusing to train because this could "
            "produce the wrong loss mask."
        )

    if len(full_ids) > MAX_LENGTH:

        raise RuntimeError(
            "\nExample exceeds MAX_LENGTH.\n"
            f"Length: {len(full_ids)}\n"
            f"MAX_LENGTH: {MAX_LENGTH}\n"
            "\nIncrease MAX_LENGTH rather than "
            "silently truncating function calls."
        )

    labels = (
        [-100] * prefix_len
        + full_ids[prefix_len:]
    )

    if len(labels) != len(full_ids):

        raise RuntimeError(
            "Label/input length mismatch."
        )

    target_tokens = sum(
        label != -100
        for label in labels
    )

    if target_tokens == 0:

        raise RuntimeError(
            "Training example has no target tokens."
        )

    return {
        "input_ids": full_ids,

        "attention_mask": [
            1
        ] * len(full_ids),

        "labels": labels,
    }


# ============================================================
# TOKENIZE ENTIRE DATASET
# ============================================================

print("\nTokenizing and masking datasets...")

tokenized_train = [
    tokenize_training_example(row)
    for row in raw_train
]

tokenized_eval = [
    tokenize_training_example(row)
    for row in raw_eval
]


train_lengths = [
    len(x["input_ids"])
    for x in tokenized_train
]

eval_lengths = [
    len(x["input_ids"])
    for x in tokenized_eval
]


print(
    f"Longest training sequence: "
    f"{max(train_lengths)} tokens"
)

print(
    f"Longest evaluation sequence: "
    f"{max(eval_lengths)} tokens"
)


train_dataset = Dataset.from_list(
    tokenized_train
)

eval_dataset = Dataset.from_list(
    tokenized_eval
)


# ============================================================
# VERIFY THAT MASKING WORKED
# ============================================================

sample = tokenized_train[0]

target_ids = [
    token_id
    for token_id, label
    in zip(
        sample["input_ids"],
        sample["labels"],
    )
    if label != -100
]

print("\nMODEL IS BEING TRAINED ON THIS TARGET:\n")

print(
    tokenizer.decode(
        target_ids,
        skip_special_tokens=False,
    )
)


# ============================================================
# CUSTOM COLLATOR
#
# Pads:
#
# input_ids -> tokenizer pad ID
# masks     -> 0
# labels    -> -100
#
# This ensures padded labels do not contribute to loss.
# ============================================================

class FunctionCallCollator:

    def __init__(
        self,
        tokenizer,
        pad_to_multiple_of=8,
    ):

        self.tokenizer = tokenizer

        self.pad_to_multiple_of = (
            pad_to_multiple_of
        )

    def __call__(self, features):

        max_len = max(
            len(x["input_ids"])
            for x in features
        )

        if self.pad_to_multiple_of:

            multiple = (
                self.pad_to_multiple_of
            )

            max_len = (
                (
                    max_len
                    + multiple
                    - 1
                )
                // multiple
            ) * multiple

        batch_input_ids = []
        batch_attention = []
        batch_labels = []

        for feature in features:

            length = len(
                feature["input_ids"]
            )

            padding = (
                max_len - length
            )

            batch_input_ids.append(
                feature["input_ids"]
                + [
                    self.tokenizer.pad_token_id
                ] * padding
            )

            batch_attention.append(
                feature["attention_mask"]
                + [0] * padding
            )

            batch_labels.append(
                feature["labels"]
                + [-100] * padding
            )

        return {
            "input_ids": torch.tensor(
                batch_input_ids,
                dtype=torch.long,
            ),

            "attention_mask": torch.tensor(
                batch_attention,
                dtype=torch.long,
            ),

            "labels": torch.tensor(
                batch_labels,
                dtype=torch.long,
            ),
        }


collator = FunctionCallCollator(
    tokenizer
)


# ============================================================
# TRAINING CONFIG
# ============================================================

optimizer = (
    "adamw_torch_fused"
    if torch.cuda.is_available()
    else "adamw_torch"
)


training_args = SFTConfig(

    output_dir=OUTPUT_DIR,

    overwrite_output_dir=True,

    # ----------------------------------------
    # Epochs / batch
    # ----------------------------------------

    num_train_epochs=NUM_EPOCHS,

    per_device_train_batch_size=(
        TRAIN_BATCH_SIZE
    ),

    per_device_eval_batch_size=(
        EVAL_BATCH_SIZE
    ),

    gradient_accumulation_steps=(
        GRADIENT_ACCUMULATION_STEPS
    ),

    # ----------------------------------------
    # Learning rate
    # ----------------------------------------

    learning_rate=LEARNING_RATE,

    lr_scheduler_type="constant",

    weight_decay=0.01,

    # ----------------------------------------
    # Precision
    # ----------------------------------------

    bf16=BF16,

    fp16=(
        torch.cuda.is_available()
        and not BF16
    ),

    # ----------------------------------------
    # Data
    # ----------------------------------------

    max_length=MAX_LENGTH,

    packing=False,

    # Already manually masked/tokenized.
    completion_only_loss=False,

    assistant_only_loss=False,

    # ----------------------------------------
    # Optimization
    # ----------------------------------------

    optim=optimizer,

    gradient_checkpointing=False,

    max_grad_norm=1.0,

    # ----------------------------------------
    # Evaluation
    # ----------------------------------------

    eval_strategy="epoch",

    # ----------------------------------------
    # Saving
    # ----------------------------------------

    save_strategy="epoch",

    save_total_limit=2,

    load_best_model_at_end=True,

    metric_for_best_model="eval_loss",

    greater_is_better=False,

    # ----------------------------------------
    # Logging
    # ----------------------------------------

    logging_strategy="steps",

    logging_steps=10,

    logging_first_step=True,

    report_to="tensorboard",

    # ----------------------------------------
    # Reproducibility
    # ----------------------------------------

    seed=SEED,

    data_seed=SEED,

    # Dataset is already prepared.
    remove_unused_columns=False,
)


# ============================================================
# TRAINER
# ============================================================

trainer = SFTTrainer(
    model=model,

    args=training_args,

    train_dataset=train_dataset,

    eval_dataset=eval_dataset,

    processing_class=tokenizer,

    data_collator=collator,
)


# ============================================================
# TRAIN
# ============================================================

print("\n" + "=" * 72)
print("STARTING FULL FINE-TUNE")
print("=" * 72)


train_result = trainer.train(
    resume_from_checkpoint=args.resume
)


print("\n" + "=" * 72)
print("TRAINING COMPLETE")
print("=" * 72)


for key, value in (
    train_result.metrics.items()
):
    print(
        f"{key}: {value}"
    )


# ============================================================
# FINAL LOSS EVALUATION
# ============================================================

print("\nEvaluating best checkpoint...")

eval_loss_metrics = trainer.evaluate()

for key, value in (
    eval_loss_metrics.items()
):
    print(
        f"{key}: {value}"
    )


# ============================================================
# SAVE ACTUAL FINE-TUNED PARAMETERS
# ============================================================

print("\nSaving final model...")

os.makedirs(
    FINAL_MODEL_DIR,
    exist_ok=True,
)

trainer.model.config.use_cache = True

trainer.save_model(
    FINAL_MODEL_DIR
)

tokenizer.save_pretrained(
    FINAL_MODEL_DIR
)


# ============================================================
# FUNCTIONGEMMA OUTPUT PARSER
#
# Example:
#
# <start_function_call>
# call:set_volume{level:42}
# <end_function_call>
# ============================================================

CALL_PATTERN = re.compile(
    r"<start_function_call>"
    r"call:(\w+)"
    r"\{(.*?)\}"
    r"<end_function_call>",
    re.DOTALL,
)

ARG_PATTERN = re.compile(
    r"(\w+):"
    r"(?:"
    r"<escape>(.*?)<escape>"
    r"|"
    r"([^,}]*)"
    r")"
)


def cast_argument(value):

    value = value.strip()

    if (
        len(value) >= 2
        and value[0] == value[-1]
        and value[0] in {"'", '"'}
    ):
        value = value[1:-1]

    if value.lower() == "true":
        return True

    if value.lower() == "false":
        return False

    try:
        return int(value)

    except ValueError:
        pass

    try:
        return float(value)

    except ValueError:
        pass

    return value


def parse_tool_calls(text):

    calls = []

    for (
        function_name,
        raw_arguments,
    ) in CALL_PATTERN.findall(text):

        arguments = {}

        for (
            key,
            escaped_value,
            plain_value,
        ) in ARG_PATTERN.findall(
            raw_arguments
        ):

            raw_value = (
                escaped_value
                if escaped_value != ""
                else plain_value
            )

            arguments[key] = cast_argument(
                raw_value
            )

        calls.append({
            "name": function_name,
            "arguments": arguments,
        })

    return calls


# ============================================================
# EXPECTED CALL NORMALIZATION
# ============================================================

def expected_calls(row):

    assistant = row["messages"][-1]

    output = []

    for call_data in assistant[
        "tool_calls"
    ]:

        function = call_data[
            "function"
        ]

        output.append({
            "name": function["name"],
            "arguments": function.get(
                "arguments",
                {},
            ),
        })

    return output


# ============================================================
# GENERATE ONE ROUTING RESPONSE
# ============================================================

def generate_calls(row):

    messages = row["messages"][:-1]

    tools = row["tools"]

    inputs = tokenizer.apply_chat_template(
        messages,
        tools=tools,
        add_generation_prompt=True,
        return_dict=True,
        return_tensors="pt",
    )

    inputs = {
        key: value.to(
            trainer.model.device
        )
        for key, value in inputs.items()
    }

    with torch.inference_mode():

        output = trainer.model.generate(
            **inputs,

            max_new_tokens=(
                MAX_NEW_TOKENS
            ),

            do_sample=False,

            pad_token_id=(
                tokenizer.eos_token_id
            ),
        )

    generated_tokens = output[0][
        inputs["input_ids"].shape[1]:
    ]

    raw_output = tokenizer.decode(
        generated_tokens,
        skip_special_tokens=False,
    )

    return (
        raw_output,
        parse_tool_calls(raw_output),
    )


# ============================================================
# ROUTING BENCHMARK
# ============================================================

print("\n" + "=" * 72)
print("HELD-OUT FUNCTION CALL BENCHMARK")
print("=" * 72)

trainer.model.eval()


total = len(raw_eval)

exact_correct = 0
tool_sequence_correct = 0
valid_output_count = 0

predictions = []


for index, row in enumerate(
    raw_eval,
    start=1,
):

    expected = expected_calls(row)

    raw_output, predicted = (
        generate_calls(row)
    )

    exact = (
        predicted == expected
    )

    expected_names = [
        x["name"]
        for x in expected
    ]

    predicted_names = [
        x["name"]
        for x in predicted
    ]

    tool_sequence_match = (
        expected_names
        == predicted_names
    )

    all_valid = True

    validation_errors = []

    if not predicted:

        all_valid = False

        validation_errors.append(
            "No function call parsed"
        )

    else:

        for predicted_call in predicted:

            valid, error = (
                validate_function_call(
                    predicted_call["name"],
                    predicted_call[
                        "arguments"
                    ],
                )
            )

            if not valid:

                all_valid = False

                validation_errors.append(
                    error
                )

    exact_correct += int(exact)

    tool_sequence_correct += int(
        tool_sequence_match
    )

    valid_output_count += int(
        all_valid
    )

    user_text = next(
        message["content"]
        for message in row["messages"]
        if message["role"] == "user"
    )

    result = {
        "index": index,
        "user": user_text,
        "expected": expected,
        "predicted": predicted,
        "exact": exact,
        "tool_sequence_match": (
            tool_sequence_match
        ),
        "valid_output": all_valid,
        "validation_errors": (
            validation_errors
        ),
        "raw_output": raw_output,
        "metadata": row.get(
            "metadata",
            {},
        ),
    }

    predictions.append(result)

    symbol = (
        "✅"
        if exact
        else "❌"
    )

    print(
        f"\n{symbol} {index}/{total}"
    )

    print(
        f"USER: {user_text}"
    )

    print(
        f"EXPECTED: {expected}"
    )

    print(
        f"PREDICTED: {predicted}"
    )

    if not exact:

        print(
            f"RAW: {raw_output}"
        )


# ============================================================
# BENCHMARK METRICS
# ============================================================

exact_accuracy = (
    exact_correct / total
    if total
    else 0
)

tool_accuracy = (
    tool_sequence_correct / total
    if total
    else 0
)

valid_rate = (
    valid_output_count / total
    if total
    else 0
)


routing_metrics = {
    "examples": total,

    "exact_function_call_accuracy": (
        exact_accuracy
    ),

    "tool_sequence_accuracy": (
        tool_accuracy
    ),

    "valid_output_rate": (
        valid_rate
    ),

    "exact_correct": (
        exact_correct
    ),

    "tool_sequence_correct": (
        tool_sequence_correct
    ),

    "valid_outputs": (
        valid_output_count
    ),
}


print("\n" + "=" * 72)
print("ROUTING RESULTS")
print("=" * 72)

print(
    f"Exact calls: "
    f"{exact_correct}/{total} "
    f"({exact_accuracy:.2%})"
)

print(
    f"Correct tool sequence: "
    f"{tool_sequence_correct}/{total} "
    f"({tool_accuracy:.2%})"
)

print(
    f"Schema-valid output: "
    f"{valid_output_count}/{total} "
    f"({valid_rate:.2%})"
)


# ============================================================
# SAVE METRICS
# ============================================================

training_metrics_file = os.path.join(
    FINAL_MODEL_DIR,
    "training_metrics.json",
)

routing_metrics_file = os.path.join(
    FINAL_MODEL_DIR,
    "routing_metrics.json",
)

predictions_file = os.path.join(
    FINAL_MODEL_DIR,
    "eval_predictions.jsonl",
)


with open(
    training_metrics_file,
    "w",
    encoding="utf-8",
) as f:

    json.dump(
        {
            "train": train_result.metrics,
            "evaluation": eval_loss_metrics,
        },
        f,
        indent=2,
        default=str,
    )


with open(
    routing_metrics_file,
    "w",
    encoding="utf-8",
) as f:

    json.dump(
        routing_metrics,
        f,
        indent=2,
    )


with open(
    predictions_file,
    "w",
    encoding="utf-8",
) as f:

    for prediction in predictions:

        f.write(
            json.dumps(
                prediction,
                ensure_ascii=False,
            )
            + "\n"
        )


# ============================================================
# CREATE FAILURE FILE
#
# Convenient file containing ONLY failures.
#
# You can examine these, correct them, and move real-world
# cases into real_failures.jsonl for the next training run.
# ============================================================

failure_file = os.path.join(
    FINAL_MODEL_DIR,
    "eval_failures.jsonl",
)


with open(
    failure_file,
    "w",
    encoding="utf-8",
) as f:

    for prediction in predictions:

        if prediction["exact"]:
            continue

        f.write(
            json.dumps(
                prediction,
                ensure_ascii=False,
            )
            + "\n"
        )


# ============================================================
# FINISHED
# ============================================================

print("\n" + "=" * 72)
print("DONE")
print("=" * 72)

print(
    f"""
Fine-tuned model:
    {Path(FINAL_MODEL_DIR).resolve()}

Model parameters:
    {Path(FINAL_MODEL_DIR).resolve()}/model.safetensors

Training metrics:
    {training_metrics_file}

Routing benchmark:
    {routing_metrics_file}

Every held-out prediction:
    {predictions_file}

Only failed evaluation cases:
    {failure_file}
"""
)