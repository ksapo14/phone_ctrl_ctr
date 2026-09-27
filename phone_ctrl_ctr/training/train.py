import os
import json
from pathlib import Path

import torch
import transformers
import datasets
import trl

from datasets import load_dataset
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
# CONFIG
# ============================================================

MODEL_ID = "google/functiongemma-270m-it"

TRAIN_FILE = "desktop_commands_train.jsonl"
EVAL_FILE = "desktop_commands_eval.jsonl"

CHECKPOINT_DIR = "./functiongemma-desktop-checkpoints"
FINAL_MODEL_DIR = "./functiongemma-desktop-model"

SEED = 42

# Good starting values for your H200 + ~thousands of examples.
NUM_EPOCHS = 4
LEARNING_RATE = 5e-5

TRAIN_BATCH_SIZE = 16
EVAL_BATCH_SIZE = 16

GRADIENT_ACCUMULATION_STEPS = 1

MAX_LENGTH = 1024


# ============================================================
# REPRODUCIBILITY
# ============================================================

set_seed(SEED)


# ============================================================
# BANNER
# ============================================================

print("=" * 72)
print("FUNCTIONGEMMA DESKTOP ROUTER TRAINING")
print("=" * 72)

print("\nLibrary versions:")
print("  PyTorch:     ", torch.__version__)
print("  Transformers:", transformers.__version__)
print("  Datasets:    ", datasets.__version__)
print("  TRL:         ", trl.__version__)


# ============================================================
# CHECK DATASET FILES
# ============================================================

for path in [TRAIN_FILE, EVAL_FILE]:

    if not Path(path).exists():

        raise FileNotFoundError(
            f"\nMissing dataset file:\n"
            f"  {path}\n\n"
            f"Run:\n"
            f"  python make_dataset.py\n"
        )

    if Path(path).stat().st_size == 0:

        raise RuntimeError(
            f"\nDataset file is empty:\n"
            f"  {path}\n\n"
            f"Run make_dataset.py again before training.\n"
        )


# ============================================================
# LOAD DATA
# ============================================================

print("\nLoading datasets...")

dataset = load_dataset(
    "json",
    data_files={
        "train": TRAIN_FILE,
        "validation": EVAL_FILE,
    },
)

train_dataset = dataset["train"]
eval_dataset = dataset["validation"]

print(
    f"Training examples:   {len(train_dataset)}"
)

print(
    f"Evaluation examples: {len(eval_dataset)}"
)


if len(train_dataset) == 0:

    raise RuntimeError(
        "Training dataset is empty."
    )


if len(eval_dataset) == 0:

    raise RuntimeError(
        "Evaluation dataset is empty."
    )


# ============================================================
# BASIC DATASET VALIDATION
# ============================================================

ALLOWED_FUNCTIONS = {
    "start_app",
    "set_volume",
    "set_brightness",
    "pause_media",
    "play_media",
    "skip_media",
    "open_website",
}

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


def validate_call(call_data):

    if "function" not in call_data:
        raise ValueError(
            f"Malformed tool call: {call_data}"
        )

    function = call_data["function"]

    name = function.get("name")
    arguments = function.get(
        "arguments",
        {},
    )

    if name not in ALLOWED_FUNCTIONS:

        raise ValueError(
            f"Unsupported function: {name}"
        )

    if not isinstance(arguments, dict):

        raise ValueError(
            f"Arguments must be dict: {arguments}"
        )

    if name == "start_app":

        if set(arguments.keys()) != {"app"}:

            raise ValueError(
                f"Invalid start_app args: {arguments}"
            )

        if arguments["app"] not in ALLOWED_APPS:

            raise ValueError(
                f"Unsupported app: {arguments['app']}"
            )

    elif name in {
        "set_volume",
        "set_brightness",
    }:

        if set(arguments.keys()) != {"level"}:

            raise ValueError(
                f"Invalid {name} args: {arguments}"
            )

        level = arguments["level"]

        if type(level) is not int:

            raise ValueError(
                f"{name} level must be int: {level}"
            )

        if not 0 <= level <= 100:

            raise ValueError(
                f"{name} level out of range: {level}"
            )

    elif name == "open_website":

        if set(arguments.keys()) != {"site"}:

            raise ValueError(
                f"Invalid open_website args: {arguments}"
            )

        if arguments["site"] not in ALLOWED_SITES:

            raise ValueError(
                f"Unsupported site: {arguments['site']}"
            )

    else:

        # pause/play/skip take zero arguments.
        if arguments:

            raise ValueError(
                f"{name} should have no args: {arguments}"
            )


def validate_dataset(split, split_name):

    for index, row in enumerate(split):

        if "messages" not in row:

            raise ValueError(
                f"{split_name}[{index}] has no messages"
            )

        if "tools" not in row:

            raise ValueError(
                f"{split_name}[{index}] has no tools"
            )

        messages = row["messages"]

        if len(messages) < 3:

            raise ValueError(
                f"{split_name}[{index}] has too few messages"
            )

        assistant = messages[-1]

        if assistant["role"] != "assistant":

            raise ValueError(
                f"{split_name}[{index}] does not end "
                f"with an assistant response"
            )

        calls = assistant.get(
            "tool_calls",
            [],
        )

        if not calls:

            raise ValueError(
                f"{split_name}[{index}] contains "
                f"no tool calls"
            )

        for call_data in calls:

            validate_call(call_data)


print("\nValidating datasets...")

validate_dataset(
    train_dataset,
    "train",
)

validate_dataset(
    eval_dataset,
    "validation",
)

print("Dataset validation: PASSED")


# ============================================================
# VERIFY TOOL DEFINITIONS MATCH ACROSS ALL EXAMPLES
# ============================================================

def canonical_json(value):

    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
    )


expected_tools = canonical_json(
    train_dataset[0]["tools"]
)


for split_name, split in [
    ("train", train_dataset),
    ("validation", eval_dataset),
]:

    for index, row in enumerate(split):

        if canonical_json(
            row["tools"]
        ) != expected_tools:

            raise RuntimeError(
                f"{split_name}[{index}] has a "
                f"different tool schema."
            )


print("Tool schemas: consistent")


# ============================================================
# HARD TRAIN/EVAL LEAKAGE CHECK
# ============================================================

def get_user_text(row):

    for message in row["messages"]:

        if message["role"] == "user":

            return " ".join(
                message["content"]
                .lower()
                .strip()
                .split()
            )

    raise ValueError(
        "Example has no user message."
    )


train_prompts = {
    get_user_text(row)
    for row in train_dataset
}

eval_prompts = {
    get_user_text(row)
    for row in eval_dataset
}

overlap = (
    train_prompts
    & eval_prompts
)


if overlap:

    raise RuntimeError(
        "Train/eval leakage found:\n"
        + "\n".join(
            sorted(overlap)
        )
    )


print("Train/eval exact leakage: none")


# ============================================================
# CHECK GPU
# ============================================================

print("\nHardware:")

if not torch.cuda.is_available():

    raise RuntimeError(
        "\nCUDA is NOT available.\n"
        "Do not train until you are inside the GPU allocation."
    )


gpu_name = torch.cuda.get_device_name(0)

gpu_memory_gb = (
    torch.cuda.get_device_properties(0)
    .total_memory
    / 1024**3
)

bf16_supported = (
    torch.cuda.is_bf16_supported()
)


print(
    f"  GPU:  {gpu_name}"
)

print(
    f"  VRAM: {gpu_memory_gb:.2f} GB"
)

print(
    f"  BF16: {bf16_supported}"
)


if not bf16_supported:

    print(
        "\nWARNING: BF16 is not reported as supported."
    )


# ============================================================
# LOAD TOKENIZER
# ============================================================

print("\nLoading tokenizer...")

tokenizer = AutoTokenizer.from_pretrained(
    MODEL_ID,
)


# FunctionGemma should already have the correct tokenizer
# configuration, but provide a safe padding fallback.
if tokenizer.pad_token is None:

    tokenizer.pad_token = tokenizer.eos_token


# ============================================================
# LOAD MODEL
# ============================================================

print("Loading FunctionGemma...")

dtype = (
    torch.bfloat16
    if bf16_supported
    else torch.float16
)


model = AutoModelForCausalLM.from_pretrained(
    MODEL_ID,

    dtype=dtype,

    # Google's FunctionGemma fine-tuning example
    # uses eager attention.
    attn_implementation="eager",
)


# Trainer will place the model on the H200.
#
# Don't use device_map="auto" here because we're training on
# one GPU and letting Trainer/Accelerate manage placement.
model.config.use_cache = False


print(
    f"Model dtype: {model.dtype}"
)


# ============================================================
# VERIFY FUNCTIONGEMMA CHAT TEMPLATE
# ============================================================

print("\n" + "=" * 72)
print("FORMATTED TRAINING EXAMPLE")
print("=" * 72)

first_example = train_dataset[0]

formatted = tokenizer.apply_chat_template(
    first_example["messages"],
    tools=first_example["tools"],
    add_generation_prompt=False,
    tokenize=False,
)

print(
    formatted[:6000]
)

print("\n" + "=" * 72)


# ============================================================
# SFT CONFIG
#
# IMPORTANT:
#
# We intentionally DO NOT manually tokenize/mask the dataset.
#
# TRL receives the raw conversational dataset containing:
#
#     messages
#     tools
#
# and applies FunctionGemma's chat template itself.
# ============================================================

training_args = SFTConfig(

    # --------------------------------------------------------
    # OUTPUT
    # --------------------------------------------------------

    output_dir=CHECKPOINT_DIR,

    overwrite_output_dir=True,


    # --------------------------------------------------------
    # TRAINING
    # --------------------------------------------------------

    num_train_epochs=NUM_EPOCHS,

    learning_rate=LEARNING_RATE,

    per_device_train_batch_size=(
        TRAIN_BATCH_SIZE
    ),

    per_device_eval_batch_size=(
        EVAL_BATCH_SIZE
    ),

    gradient_accumulation_steps=(
        GRADIENT_ACCUMULATION_STEPS
    ),


    # --------------------------------------------------------
    # SEQUENCE LENGTH
    # --------------------------------------------------------

    max_length=MAX_LENGTH,

    packing=False,


    # --------------------------------------------------------
    # OPTIMIZATION
    # --------------------------------------------------------

    optim="adamw_torch_fused",

    weight_decay=0.01,

    lr_scheduler_type="constant",

    max_grad_norm=1.0,


    # --------------------------------------------------------
    # H200 PRECISION
    # --------------------------------------------------------

    bf16=bf16_supported,

    fp16=(
        not bf16_supported
    ),

    gradient_checkpointing=False,


    # --------------------------------------------------------
    # EVALUATION
    # --------------------------------------------------------

    eval_strategy="epoch",


    # --------------------------------------------------------
    # CHECKPOINT SAVING
    # --------------------------------------------------------

    save_strategy="epoch",

    save_total_limit=2,

    load_best_model_at_end=True,

    metric_for_best_model="eval_loss",

    greater_is_better=False,


    # --------------------------------------------------------
    # LOGGING
    # --------------------------------------------------------

    logging_strategy="steps",

    logging_steps=10,

    logging_first_step=True,

    report_to="tensorboard",


    # --------------------------------------------------------
    # REPRODUCIBILITY
    # --------------------------------------------------------

    seed=SEED,

    data_seed=SEED,


    # --------------------------------------------------------
    # DATASET
    # --------------------------------------------------------

    remove_unused_columns=True,
)


# ============================================================
# CREATE TRAINER
# ============================================================

print("\nCreating SFTTrainer...")

trainer = SFTTrainer(

    model=model,

    args=training_args,

    train_dataset=train_dataset,

    eval_dataset=eval_dataset,

    processing_class=tokenizer,
)


# ============================================================
# TRAIN
# ============================================================

print("\n" + "=" * 72)
print("STARTING FULL FUNCTIONGEMMA FINE-TUNE")
print("=" * 72)

train_result = trainer.train()


# ============================================================
# TRAINING FINISHED
# ============================================================

print("\n" + "=" * 72)
print("TRAINING COMPLETE")
print("=" * 72)

print("\nTraining metrics:")

for key, value in train_result.metrics.items():

    print(
        f"  {key}: {value}"
    )


# ============================================================
# EVALUATE BEST CHECKPOINT
# ============================================================

print("\nEvaluating best checkpoint...")

eval_metrics = trainer.evaluate()


print("\nEvaluation metrics:")

for key, value in eval_metrics.items():

    print(
        f"  {key}: {value}"
    )


# ============================================================
# SAVE FINAL FULL MODEL
# ============================================================

print("\nSaving final model...")

os.makedirs(
    FINAL_MODEL_DIR,
    exist_ok=True,
)


# Re-enable KV cache for inference.
trainer.model.config.use_cache = True


trainer.save_model(
    FINAL_MODEL_DIR
)

tokenizer.save_pretrained(
    FINAL_MODEL_DIR
)


# ============================================================
# SAVE METRICS
# ============================================================

metrics = {
    "model": MODEL_ID,

    "training_examples": len(
        train_dataset
    ),

    "evaluation_examples": len(
        eval_dataset
    ),

    "epochs": NUM_EPOCHS,

    "learning_rate": LEARNING_RATE,

    "train_batch_size": (
        TRAIN_BATCH_SIZE
    ),

    "eval_batch_size": (
        EVAL_BATCH_SIZE
    ),

    "gradient_accumulation_steps": (
        GRADIENT_ACCUMULATION_STEPS
    ),

    "max_length": MAX_LENGTH,

    "gpu": gpu_name,

    "gpu_vram_gb": (
        gpu_memory_gb
    ),

    "train_metrics": (
        train_result.metrics
    ),

    "eval_metrics": (
        eval_metrics
    ),
}


metrics_file = os.path.join(
    FINAL_MODEL_DIR,
    "training_metrics.json",
)


with open(
    metrics_file,
    "w",
    encoding="utf-8",
) as f:

    json.dump(
        metrics,
        f,
        indent=2,
        default=str,
    )


# ============================================================
# SMOKE TESTS
#
# These do NOT execute anything on the computer.
#
# They simply test model generation after training.
# ============================================================

print("\n" + "=" * 72)
print("POST-TRAINING SMOKE TESTS")
print("=" * 72)


tools = train_dataset[0]["tools"]

developer_message = (
    "You are a model that can do function calling "
    "with the following functions"
)


TEST_PROMPTS = [
    "Open VS Code",

    "Set volume to 47",

    "Brightness 72",

    "Pause the music",

    "Resume playback",

    "Skip this song",

    "Take me to GitHub",

    "Open Google Docs",

    "Don't open GitHub, launch Chrome",

    "Set the speakers to thirty seven percent",

    "Put my display at 83 percent",

    "Open Spotify and set volume to 35",

    "Pause the music and open Google Drive",

    "Volume 22 and brightness 71",
]


smoke_results = []


trainer.model.eval()


for prompt in TEST_PROMPTS:

    messages = [
        {
            "role": "developer",
            "content": developer_message,
        },
        {
            "role": "user",
            "content": prompt,
        },
    ]


    inputs = tokenizer.apply_chat_template(
        messages,

        tools=tools,

        add_generation_prompt=True,

        tokenize=True,

        return_dict=True,

        return_tensors="pt",
    )


    inputs = {
        key: value.to(
            trainer.model.device
        )

        for key, value
        in inputs.items()
    }


    with torch.inference_mode():

        generated = trainer.model.generate(
            **inputs,

            max_new_tokens=128,

            do_sample=False,

            pad_token_id=(
                tokenizer.pad_token_id
            ),

            eos_token_id=(
                tokenizer.eos_token_id
            ),
        )


    # Only decode newly generated tokens,
    # not the original prompt.
    generated_tokens = generated[0][
        inputs["input_ids"].shape[1]:
    ]


    response = tokenizer.decode(
        generated_tokens,

        skip_special_tokens=False,
    )


    result = {
        "prompt": prompt,
        "output": response,
    }


    smoke_results.append(
        result
    )


    print("\nUSER:")
    print(
        prompt
    )

    print("MODEL:")
    print(
        response
    )


# ============================================================
# SAVE SMOKE TEST OUTPUTS
# ============================================================

smoke_file = os.path.join(
    FINAL_MODEL_DIR,
    "smoke_test_outputs.json",
)


with open(
    smoke_file,
    "w",
    encoding="utf-8",
) as f:

    json.dump(
        smoke_results,
        f,
        indent=2,
        ensure_ascii=False,
    )


# ============================================================
# FINAL SUMMARY
# ============================================================

print("\n" + "=" * 72)
print("DONE")
print("=" * 72)

print(
    f"""
Fine-tuned model directory:

    {Path(FINAL_MODEL_DIR).resolve()}

The important output files are:

    {FINAL_MODEL_DIR}/model.safetensors
    {FINAL_MODEL_DIR}/config.json
    {FINAL_MODEL_DIR}/tokenizer.json
    {FINAL_MODEL_DIR}/training_metrics.json
    {FINAL_MODEL_DIR}/smoke_test_outputs.json

Intermediate checkpoints are in:

    {Path(CHECKPOINT_DIR).resolve()}

To package the model for transfer back to your app:

    tar -czf functiongemma-desktop-model.tar.gz functiongemma-desktop-model

Then download that .tar.gz from the cluster.
"""
)