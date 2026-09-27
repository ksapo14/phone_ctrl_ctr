import json
import sys
from pathlib import Path

import torch

from transformers import (
    AutoTokenizer,
    AutoModelForCausalLM,
    StoppingCriteria,
)


MODEL_PATH = Path(__file__).resolve().parent.parent / "models" / "functiongemma-desktop-model"


# ============================================================
# LOAD MODEL
# ============================================================

tokenizer = AutoTokenizer.from_pretrained(
    MODEL_PATH
)

device = "cuda" if torch.cuda.is_available() else "cpu"

print("Using device:", device, file=sys.stderr)

model = AutoModelForCausalLM.from_pretrained(
    MODEL_PATH,
    dtype=torch.float32 if device == "cpu" else torch.float16,
)

model = model.to(device)

model.eval()


class StopAtFunctionResponse(StoppingCriteria):
    def __init__(self):
        self.token_ids = tokenizer.encode("<start_function_response>", add_special_tokens=False)

    def __call__(self, input_ids, scores, **kwargs):
        count = len(self.token_ids)
        return count > 0 and input_ids.shape[1] >= count and input_ids[0, -count:].tolist() == self.token_ids


# ============================================================
# SAME TOOLS USED DURING TRAINING
# ============================================================

TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "start_app",
            "description": "Start or focus a supported desktop application.",
            "parameters": {
                "type": "object",
                "properties": {
                    "app": {
                        "type": "string",
                        "enum": [
                            "chrome",
                            "chatgpt",
                            "spotify",
                            "vscode",
                            "command_prompt",
                            "file_explorer",
                            "notion",
                            "settings",
                        ],
                    }
                },
                "required": ["app"],
            },
        },
    },

    {
        "type": "function",
        "function": {
            "name": "set_volume",
            "description": "Set system audio volume from 0 to 100.",
            "parameters": {
                "type": "object",
                "properties": {
                    "level": {
                        "type": "integer",
                        "minimum": 0,
                        "maximum": 100,
                    }
                },
                "required": ["level"],
            },
        },
    },

    {
        "type": "function",
        "function": {
            "name": "set_brightness",
            "description": "Set display brightness from 0 to 100.",
            "parameters": {
                "type": "object",
                "properties": {
                    "level": {
                        "type": "integer",
                        "minimum": 0,
                        "maximum": 100,
                    }
                },
                "required": ["level"],
            },
        },
    },

    {
        "type": "function",
        "function": {
            "name": "pause_media",
            "description": "Pause currently playing media.",
            "parameters": {
                "type": "object",
                "properties": {},
            },
        },
    },

    {
        "type": "function",
        "function": {
            "name": "play_media",
            "description": "Play or resume media.",
            "parameters": {
                "type": "object",
                "properties": {},
            },
        },
    },

    {
        "type": "function",
        "function": {
            "name": "skip_media",
            "description": "Skip to the next media item.",
            "parameters": {
                "type": "object",
                "properties": {},
            },
        },
    },

    {
        "type": "function",
        "function": {
            "name": "open_website",
            "description": "Open a supported website.",
            "parameters": {
                "type": "object",
                "properties": {
                    "site": {
                        "type": "string",
                        "enum": [
                            "google_drive",
                            "github",
                            "google_docs",
                            "youtube",
                        ],
                    }
                },
                "required": ["site"],
            },
        },
    },
]


# ============================================================
# RUN FUNCTIONGEMMA
# ============================================================

def route_command(user_text):

    messages = [
        {
            "role": "developer",
            "content": (
                "You are a model that can do function calling "
                "with the following functions"
            ),
        },
        {
            "role": "user",
            "content": user_text,
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
        key: value.to(model.device)
        for key, value in inputs.items()
    }


    with torch.inference_mode():

        output = model.generate(
            **inputs,
            max_new_tokens=128,
            do_sample=False,
            stopping_criteria=[StopAtFunctionResponse()],
        )


    generated_tokens = output[0][
        inputs["input_ids"].shape[1]:
    ]


    response = tokenizer.decode(
        generated_tokens,
        skip_special_tokens=False,
    )

    return response


# ============================================================
# TEST
# ============================================================

if __name__ == "__main__":
    if "--serve" in sys.argv:
        for line in sys.stdin:
            request = None
            try:
                request = json.loads(line)
                result = route_command(request["text"])
                reply = {"id": request["id"], "output": result}
            except Exception as error:
                reply = {"id": request.get("id") if isinstance(request, dict) else None, "error": str(error)}
            print(json.dumps(reply), flush=True)
    else:
        while True:
            command = input("\nCommand: ")
            if command.lower() in {"exit", "quit"}:
                break
            print("\nFunctionGemma:")
            print(route_command(command))
