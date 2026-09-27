import os
import json
import inspect
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
from trl import SFTTrainer, SFTConfig


# ============================================================
# CONFIG
# ============================================================

MODEL_ID = "google/functiongemma-270m-it"

TRAIN_FILE = "desktop_commands_train.jsonl"
EVAL_FILE = "desktop_commands_eval.jsonl"

CHECKPOINT_DIR = "./functiongemma-desktop-checkpoints"
FINAL_MODEL_DIR = "./functiongemma-desktop-model"

SEED = 42

NUM_EPOCHS = 4
LEARNING_RATE = 5e-5

TRAIN_BATCH_SIZE = 16
EVAL_BATCH_SIZE = 16
GRADIENT_ACCUMULATION_STEPS = 1

MAX_LENGTH = 1024
MAX_NEW_TOKENS = 128


# ============================================================
# SETUP
# ============================================================

set_seed(SEED)

print("=" * 72)
print("FUNCTIONGEMMA DESKTOP ROUTER TRAINING")
print("=" * 72)

print("\nVersions:")
print("  PyTorch:     ", torch.__version__)
print("  Transformers:", transformers.__version__)
print("  Datasets:    ", datasets.__version__)
print("  TRL:         ", trl.__version__)


# ============================================================
# CHECK FILES
# ============================================================

for file_path in [TRAIN_FILE, EVAL_FILE]:

    path = Path(file_path)

    if not path.exists():
        raise FileNotFoundError(
            f"\nMissing file:\n"
            f"  {file_path}\n\n"
            f"Run:\n"
            f"  python make_dataset.py\n"
        )

    if path.stat().st_size == 0:
        raise RuntimeError(
            f"\nDataset file is empty:\n"
            f"  {file_path}\n"
        )


# ============================================================
# LOAD DATASET
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

print(f"Training examples:   {len(train_dataset)}")
print(f"Evaluation examples: {len(eval_dataset)}")

if len(train_dataset) == 0:
    raise RuntimeError("Training dataset is empty.")

if len(eval_dataset) == 0:
    raise RuntimeError("Evaluation dataset is empty.")


# ============================================================
# VALIDATION CONSTANTS
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


# ============================================================
# DATASET VALIDATION
# ============================================================

def validate_call(call_data):

    if "function" not in call_data:
        raise ValueError(
            f"Malformed tool call: {call_data}"
        )

    function = call_data["function"]

    name = function.get("name")
    arguments = function.get("arguments", {})

    if name not in ALLOWED_FUNCTIONS:
        raise ValueError(
            f"Unsupported function: {name}"
        )

    if not isinstance(arguments, dict):
        raise ValueError(
            f"Arguments for {name} must be a dictionary."
        )

    # --------------------------------------------
    # start_app
    # --------------------------------------------

    if name == "start_app":

        if set(arguments.keys()) != {"app"}:
            raise ValueError(
                f"Invalid start_app arguments: {arguments}"
            )

        if arguments["app"] not in ALLOWED_APPS:
            raise ValueError(
                f"Unsupported application: {arguments['app']}"
            )

    # --------------------------------------------
    # volume / brightness
    # --------------------------------------------

    elif name in {
        "set_volume",
        "set_brightness",
    }:

        if set(arguments.keys()) != {"level"}:
            raise ValueError(
                f"Invalid {name} arguments: {arguments}"
            )

        level = arguments["level"]

        if type(level) is not int:
            raise ValueError(
                f"{name} level must be an int. "
                f"Got: {level!r}"
            )

        if not 0 <= level <= 100:
            raise ValueError(
                f"{name} level out of range: {level}"
            )

    # --------------------------------------------
    # website
    # --------------------------------------------

    elif name == "open_website":

        if set(arguments.keys()) != {"site"}:
            raise ValueError(
                f"Invalid open_website arguments: {arguments}"
            )

        if arguments["site"] not in ALLOWED_SITES:
            raise ValueError(
                f"Unsupported website: {arguments['site']}"
            )

    # --------------------------------------------
    # no-argument media calls
    # --------------------------------------------

    else:

        if arguments != {}:
            raise ValueError(
                f"{name} should not have arguments: {arguments}"
            )


def validate_split(split, split_name):

    for index, row in enumerate(split):

        if "messages" not in row:
            raise ValueError(
                f"{split_name}[{index}] missing messages"
            )

        if "tools" not in row:
            raise ValueError(
                f"{split_name}[{index}] missing tools"
            )

        messages = row["messages"]

        if len(messages) < 3:
            raise ValueError(
                f"{split_name}[{index}] has too few messages"
            )

        assistant = messages[-1]

        if assistant["role"] != "assistant":
            raise ValueError(
                f"{split_name}[{index}] must end "
                f"with assistant message"
            )

        calls = assistant.get("tool_calls", [])

        if not calls:
            raise ValueError(
                f"{split_name}[{index}] has no tool calls"
            )

        for call_data in calls:
            validate_call(call_data)


print("\nValidating dataset...")

validate_split(
    train_dataset,
    "train",
)

validate_split(
    eval_dataset,
    "validation",
)

print("Dataset validation: PASSED")


# ============================================================
# VERIFY IDENTICAL TOOL SCHEMAS
# ============================================================

def canonical_json(value):

    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
    )


expected_tools_json = canonical_json(
    train_dataset[0]["tools"]
)

for split_name, split in [
    ("train", train_dataset),
    ("validation", eval_dataset),
]:

    for index, row in enumerate(split):

        current_tools = canonical_json(
            row["tools"]
        )

        if current_tools != expected_tools_json:
            raise RuntimeError(
                f"{split_name}[{index}] contains "
                f"different tool definitions."
            )


print("Tool schemas: consistent")


# ============================================================
# TRAIN/EVAL LEAKAGE CHECK
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
        "Example contains no user message."
    )


train_prompts = {
    get_user_text(row)
    for row in train_dataset
}

eval_prompts = {
    get_user_text(row)
    for row in eval_dataset
}

overlap = train_prompts & eval_prompts

if overlap:

    raise RuntimeError(
        "\nTrain/eval exact leakage detected:\n"
        + "\n".join(sorted(overlap))
    )


print("Train/eval exact leakage: none")


# ============================================================
# GPU CHECK
# ============================================================

print("\nHardware:")

if not torch.cuda.is_available():

    raise RuntimeError(
        "\nCUDA is not available.\n"
        "Make sure you are running inside your H200 allocation."
    )


GPU_NAME = torch.cuda.get_device_name(0)

GPU_MEMORY_GB = (
    torch.cuda.get_device_properties(0).total_memory
    / 1024**3
)

BF16_SUPPORTED = torch.cuda.is_bf16_supported()


print(f"  GPU:  {GPU_NAME}")
print(f"  VRAM: {GPU_MEMORY_GB:.2f} GB")
print(f"  BF16: {BF16_SUPPORTED}")


# ============================================================
# LOAD TOKENIZER
# ============================================================

print("\nLoading tokenizer...")

tokenizer = AutoTokenizer.from_pretrained(
    MODEL_ID
)

if tokenizer.pad_token is None:
    tokenizer.pad_token = tokenizer.eos_token

tokenizer.padding_side = "right"


# ============================================================
# LOAD MODEL
# ============================================================

print("Loading FunctionGemma...")

MODEL_DTYPE = (
    torch.bfloat16
    if BF16_SUPPORTED
    else torch.float16
)

model = AutoModelForCausalLM.from_pretrained(
    MODEL_ID,
    dtype=MODEL_DTYPE,
    attn_implementation="eager",
)

model.config.use_cache = False

print(f"Model dtype: {model.dtype}")


# ============================================================
# SHOW CHAT TEMPLATE EXAMPLE
# ============================================================

print("\n" + "=" * 72)
print("FORMATTED TRAINING EXAMPLE")
print("=" * 72)

sample = train_dataset[0]

formatted = tokenizer.apply_chat_template(
    sample["messages"],
    tools=sample["tools"],
    add_generation_prompt=False,
    tokenize=False,
)

print(formatted[:6000])

print("=" * 72)


# ============================================================
# VERSION-ADAPTIVE SFT CONFIG
#
# Different TRL versions expose slightly different keyword
# arguments.
#
# Instead of assuming your installed version supports every
# option, we inspect its constructor and only pass supported
# arguments.
# ============================================================

print("\nConfiguring SFTTrainer...")

sft_config_signature = inspect.signature(
    SFTConfig.__init__
)

SUPPORTED_CONFIG_ARGS = set(
    sft_config_signature.parameters.keys()
)


def config_supports(name):
    return name in SUPPORTED_CONFIG_ARGS


config_kwargs = {}


# ------------------------------------------------------------
# Core output directory
# ------------------------------------------------------------

if config_supports("output_dir"):
    config_kwargs["output_dir"] = CHECKPOINT_DIR


# ------------------------------------------------------------
# Training settings
# ------------------------------------------------------------

if config_supports("num_train_epochs"):
    config_kwargs["num_train_epochs"] = NUM_EPOCHS

if config_supports("learning_rate"):
    config_kwargs["learning_rate"] = LEARNING_RATE

if config_supports("per_device_train_batch_size"):
    config_kwargs[
        "per_device_train_batch_size"
    ] = TRAIN_BATCH_SIZE

if config_supports("per_device_eval_batch_size"):
    config_kwargs[
        "per_device_eval_batch_size"
    ] = EVAL_BATCH_SIZE

if config_supports("gradient_accumulation_steps"):
    config_kwargs[
        "gradient_accumulation_steps"
    ] = GRADIENT_ACCUMULATION_STEPS


# ------------------------------------------------------------
# Sequence length
#
# TRL versions have used both:
#
# max_length
# max_seq_length
# ------------------------------------------------------------

if config_supports("max_length"):

    config_kwargs["max_length"] = MAX_LENGTH

elif config_supports("max_seq_length"):

    config_kwargs[
        "max_seq_length"
    ] = MAX_LENGTH


# ------------------------------------------------------------
# Packing
# ------------------------------------------------------------

if config_supports("packing"):
    config_kwargs["packing"] = False


# ------------------------------------------------------------
# Optimizer
# ------------------------------------------------------------

if config_supports("optim"):

    config_kwargs[
        "optim"
    ] = "adamw_torch_fused"


if config_supports("weight_decay"):

    config_kwargs[
        "weight_decay"
    ] = 0.01


if config_supports("lr_scheduler_type"):

    config_kwargs[
        "lr_scheduler_type"
    ] = "constant"


if config_supports("max_grad_norm"):

    config_kwargs[
        "max_grad_norm"
    ] = 1.0


# ------------------------------------------------------------
# Precision
# ------------------------------------------------------------

if config_supports("bf16"):

    config_kwargs[
        "bf16"
    ] = BF16_SUPPORTED


if config_supports("fp16"):

    config_kwargs[
        "fp16"
    ] = (
        not BF16_SUPPORTED
    )


# ------------------------------------------------------------
# Gradient checkpointing
# ------------------------------------------------------------

if config_supports(
    "gradient_checkpointing"
):

    config_kwargs[
        "gradient_checkpointing"
    ] = False


# ------------------------------------------------------------
# Evaluation strategy
#
# Transformers/TRL has used both:
#
# eval_strategy
# evaluation_strategy
# ------------------------------------------------------------

if config_supports("eval_strategy"):

    config_kwargs[
        "eval_strategy"
    ] = "epoch"

elif config_supports("evaluation_strategy"):

    config_kwargs[
        "evaluation_strategy"
    ] = "epoch"


# ------------------------------------------------------------
# Saving
# ------------------------------------------------------------

if config_supports("save_strategy"):

    config_kwargs[
        "save_strategy"
    ] = "epoch"


if config_supports("save_total_limit"):

    config_kwargs[
        "save_total_limit"
    ] = 2


if config_supports(
    "load_best_model_at_end"
):

    config_kwargs[
        "load_best_model_at_end"
    ] = True


if config_supports(
    "metric_for_best_model"
):

    config_kwargs[
        "metric_for_best_model"
    ] = "eval_loss"


if config_supports(
    "greater_is_better"
):

    config_kwargs[
        "greater_is_better"
    ] = False


# ------------------------------------------------------------
# Logging
# ------------------------------------------------------------

if config_supports(
    "logging_strategy"
):

    config_kwargs[
        "logging_strategy"
    ] = "steps"


if config_supports(
    "logging_steps"
):

    config_kwargs[
        "logging_steps"
    ] = 10


if config_supports(
    "logging_first_step"
):

    config_kwargs[
        "logging_first_step"
    ] = True


if config_supports("report_to"):

    config_kwargs[
        "report_to"
    ] = "tensorboard"


# ------------------------------------------------------------
# Reproducibility
# ------------------------------------------------------------

if config_supports("seed"):

    config_kwargs["seed"] = SEED


if config_supports("data_seed"):

    config_kwargs[
        "data_seed"
    ] = SEED


# ------------------------------------------------------------
# Dataset handling
# ------------------------------------------------------------

if config_supports(
    "remove_unused_columns"
):

    config_kwargs[
        "remove_unused_columns"
    ] = True


# ------------------------------------------------------------
# IMPORTANT:
#
# Do NOT add:
#
# overwrite_output_dir
#
# Your installed SFTConfig explicitly does not support it.
#
# We simply create the checkpoint folder ourselves.
# ------------------------------------------------------------

Path(CHECKPOINT_DIR).mkdir(
    parents=True,
    exist_ok=True,
)


# ============================================================
# SHOW EXACT CONFIG BEING USED
# ============================================================

print("\nSupported SFTConfig parameters detected.")

print("\nUsing configuration:")

for key, value in config_kwargs.items():

    print(
        f"  {key}: {value}"
    )


# ============================================================
# CREATE CONFIG
# ============================================================

training_args = SFTConfig(
    **config_kwargs
)


# ============================================================
# VERSION-ADAPTIVE TRAINER CREATION
# ============================================================

trainer_signature = inspect.signature(
    SFTTrainer.__init__
)

SUPPORTED_TRAINER_ARGS = set(
    trainer_signature.parameters.keys()
)


trainer_kwargs = {
    "model": model,
    "args": training_args,
    "train_dataset": train_dataset,
    "eval_dataset": eval_dataset,
}


# ------------------------------------------------------------
# Newer TRL uses processing_class.
# Older TRL often uses tokenizer.
# ------------------------------------------------------------

if "processing_class" in SUPPORTED_TRAINER_ARGS:

    trainer_kwargs[
        "processing_class"
    ] = tokenizer

elif "tokenizer" in SUPPORTED_TRAINER_ARGS:

    trainer_kwargs[
        "tokenizer"
    ] = tokenizer

else:

    print(
        "\nWARNING: Neither processing_class nor tokenizer "
        "appears in SFTTrainer signature."
    )


# ============================================================
# CREATE TRAINER
# ============================================================

print("\nCreating SFTTrainer...")

trainer = SFTTrainer(
    **trainer_kwargs
)


# ============================================================
# TRAIN
# ============================================================

print("\n" + "=" * 72)
print("STARTING FULL FUNCTIONGEMMA FINE-TUNE")
print("=" * 72)

train_result = trainer.train()


# ============================================================
# TRAINING METRICS
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
# EVALUATION
# ============================================================

print("\nEvaluating model...")

eval_metrics = trainer.evaluate()

print("\nEvaluation metrics:")

for key, value in eval_metrics.items():

    print(
        f"  {key}: {value}"
    )


# ============================================================
# SAVE FINAL MODEL
# ============================================================

print("\nSaving final model...")

Path(FINAL_MODEL_DIR).mkdir(
    parents=True,
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
# SAVE TRAINING METRICS
# ============================================================

training_summary = {

    "base_model": MODEL_ID,

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

    "max_length_requested": (
        MAX_LENGTH
    ),

    "gpu": GPU_NAME,

    "gpu_vram_gb": (
        GPU_MEMORY_GB
    ),

    "bf16": (
        BF16_SUPPORTED
    ),

    "torch_version": (
        torch.__version__
    ),

    "transformers_version": (
        transformers.__version__
    ),

    "trl_version": (
        trl.__version__
    ),

    "datasets_version": (
        datasets.__version__
    ),

    "actual_sft_config": (
        config_kwargs
    ),

    "train_metrics": (
        train_result.metrics
    ),

    "eval_metrics": (
        eval_metrics
    ),
}


metrics_path = (
    Path(FINAL_MODEL_DIR)
    / "training_metrics.json"
)


with open(
    metrics_path,
    "w",
    encoding="utf-8",
) as f:

    json.dump(
        training_summary,
        f,
        indent=2,
        default=str,
    )


# ============================================================
# POST-TRAINING SMOKE TESTS
# ============================================================

print("\n" + "=" * 72)
print("POST-TRAINING SMOKE TESTS")
print("=" * 72)


TOOLS = train_dataset[0]["tools"]

DEVELOPER_MESSAGE = (
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


trainer.model.eval()

smoke_results = []


for prompt in TEST_PROMPTS:

    messages = [
        {
            "role": "developer",
            "content": DEVELOPER_MESSAGE,
        },

        {
            "role": "user",
            "content": prompt,
        },
    ]


    inputs = tokenizer.apply_chat_template(
        messages,
        tools=TOOLS,
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

            max_new_tokens=(
                MAX_NEW_TOKENS
            ),

            do_sample=False,

            pad_token_id=(
                tokenizer.pad_token_id
            ),

            eos_token_id=(
                tokenizer.eos_token_id
            ),
        )


    generated_tokens = generated[0][
        inputs["input_ids"].shape[1]:
    ]


    output_text = tokenizer.decode(
        generated_tokens,
        skip_special_tokens=False,
    )


    print("\nUSER:")
    print(prompt)

    print("MODEL:")
    print(output_text)


    smoke_results.append({
        "prompt": prompt,
        "output": output_text,
    })


# ============================================================
# SAVE SMOKE TESTS
# ============================================================

smoke_test_path = (
    Path(FINAL_MODEL_DIR)
    / "smoke_test_outputs.json"
)


with open(
    smoke_test_path,
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
print("SUCCESS")
print("=" * 72)

print(
    f"""
Fine-tuned model:

    {Path(FINAL_MODEL_DIR).resolve()}

Actual trained parameters:

    {Path(FINAL_MODEL_DIR).resolve()}/model.safetensors

Training metrics:

    {metrics_path.resolve()}

Smoke tests:

    {smoke_test_path.resolve()}

Checkpoints:

    {Path(CHECKPOINT_DIR).resolve()}

To package the model:

    tar -czf functiongemma-desktop-model.tar.gz functiongemma-desktop-model
"""
)