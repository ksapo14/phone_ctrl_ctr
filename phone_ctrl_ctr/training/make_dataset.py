import json
import random
from pathlib import Path

SEED = 42
random.seed(SEED)

OUTPUT_FILE = "desktop_commands.jsonl"
EVAL_FILE = "desktop_commands_eval.jsonl"

INCLUDE_CLARIFY_TOOL = True

DEVELOPER_MESSAGE = (
    "You are a model that can do function calling with the following functions. "
    "Convert the user's desktop command into the correct function call. "
    "Do not invent argument values."
)

# ============================================================
# TOOL DEFINITIONS
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
                        "description": "Canonical identifier of the application."
                    }
                },
                "required": ["app"]
            }
        }
    },

    {
        "type": "function",
        "function": {
            "name": "set_volume",
            "description": "Set system audio volume to an absolute percentage.",
            "parameters": {
                "type": "object",
                "properties": {
                    "level": {
                        "type": "integer",
                        "minimum": 0,
                        "maximum": 100,
                        "description": "Volume percentage from 0 to 100."
                    }
                },
                "required": ["level"]
            }
        }
    },

    {
        "type": "function",
        "function": {
            "name": "set_brightness",
            "description": "Set screen brightness to an absolute percentage.",
            "parameters": {
                "type": "object",
                "properties": {
                    "level": {
                        "type": "integer",
                        "minimum": 0,
                        "maximum": 100,
                        "description": "Brightness percentage from 0 to 100."
                    }
                },
                "required": ["level"]
            }
        }
    },

    {
        "type": "function",
        "function": {
            "name": "pause_media",
            "description": "Pause the currently playing media.",
            "parameters": {
                "type": "object",
                "properties": {}
            }
        }
    },

    {
        "type": "function",
        "function": {
            "name": "play_media",
            "description": "Play or resume the current media.",
            "parameters": {
                "type": "object",
                "properties": {}
            }
        }
    },

    {
        "type": "function",
        "function": {
            "name": "skip_media",
            "description": "Skip to the next media track or item.",
            "parameters": {
                "type": "object",
                "properties": {}
            }
        }
    },

    {
        "type": "function",
        "function": {
            "name": "open_website",
            "description": "Open a supported website in Google Chrome.",
            "parameters": {
                "type": "object",
                "properties": {
                    "site": {
                        "type": "string",
                        "enum": [
                            "google_drive",
                            "github",
                            "google_docs",
                            "youtube"
                        ],
                        "description": "Canonical identifier of the website."
                    }
                },
                "required": ["site"]
            }
        }
    }
]

if INCLUDE_CLARIFY_TOOL:
    TOOLS.append({
        "type": "function",
        "function": {
            "name": "clarify",
            "description": (
                "Indicate that the user's command cannot safely be executed "
                "because required information is missing or ambiguous."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "issue": {
                        "type": "string",
                        "enum": [
                            "missing_volume",
                            "missing_brightness",
                            "ambiguous_target",
                            "unsupported_app",
                            "unsupported_website",
                            "unsupported_command"
                        ]
                    }
                },
                "required": ["issue"]
            }
        }
    })


# ============================================================
# DATA HELPERS
# ============================================================

examples = []


def tool_call(name, **arguments):
    return {
        "type": "function",
        "function": {
            "name": name,
            "arguments": arguments
        }
    }


def add(user, *calls, category=None):
    examples.append({
        "user": user,
        "calls": list(calls),
        "category": category
    })


# ============================================================
# START APPLICATION
# ============================================================

APP_ALIASES = {
    "chrome": [
        "Chrome",
        "Google Chrome",
        "the Chrome browser",
        "my Chrome browser"
    ],

    "chatgpt": [
        "ChatGPT",
        "Chat GPT",
        "the ChatGPT app",
        "the Chat GPT app"
    ],

    "spotify": [
        "Spotify",
        "the Spotify app",
        "my Spotify",
        "Spotify desktop"
    ],

    "vscode": [
        "VS Code",
        "VSCode",
        "Visual Studio Code",
        "the VS Code editor"
    ],

    "command_prompt": [
        "Command Prompt",
        "cmd",
        "CMD",
        "the command prompt"
    ],

    "file_explorer": [
        "File Explorer",
        "Windows File Explorer",
        "the file explorer",
        "Explorer"
    ],

    "notion": [
        "Notion",
        "the Notion app",
        "my Notion",
        "Notion desktop"
    ],

    "settings": [
        "Settings",
        "Windows Settings",
        "the settings app",
        "system settings"
    ]
}

APP_TEMPLATES = [
    "Start {app}",
    "Open {app}",
    "Launch {app}",
    "Bring up {app}",
    "Can you start {app}?",
    "Can you open {app}?",
    "Pull up {app}",
    "Get {app} running",
    "I need {app}",
    "Switch me over to {app}",
    "Bring {app} to the front",
    "I'd like to use {app}",
]

for canonical, aliases in APP_ALIASES.items():
    for alias in aliases:
        for template in APP_TEMPLATES:
            add(
                template.format(app=alias),
                tool_call("start_app", app=canonical),
                category="start_app"
            )


# ============================================================
# VOLUME
# ============================================================

VOLUME_VALUES = [
    0, 1, 5, 10, 15, 20, 25, 30,
    35, 40, 45, 50, 55, 60, 65,
    70, 75, 80, 85, 90, 95, 99, 100
]

VOLUME_TEMPLATES = [
    "Set the volume to {n}",
    "Volume {n}",
    "Make the volume {n}%",
    "Set audio volume to {n} percent",
    "Put the sound at {n}",
    "Change my volume to {n}",
    "Can you set the volume to {n}?",
    "I want the volume at {n} percent",
    "Bring the volume to {n}",
]

for n in VOLUME_VALUES:
    for template in VOLUME_TEMPLATES:
        add(
            template.format(n=n),
            tool_call("set_volume", level=n),
            category="volume"
        )


# Numbers expressed naturally instead of as digits.

NUMBER_WORDS = {
    0: "zero",
    5: "five",
    10: "ten",
    15: "fifteen",
    20: "twenty",
    25: "twenty five",
    30: "thirty",
    40: "forty",
    50: "fifty",
    60: "sixty",
    70: "seventy",
    75: "seventy five",
    80: "eighty",
    90: "ninety",
    100: "one hundred",
}

for number, word in NUMBER_WORDS.items():
    add(
        f"Set my volume to {word} percent",
        tool_call("set_volume", level=number),
        category="volume_words"
    )

    add(
        f"Volume {word}",
        tool_call("set_volume", level=number),
        category="volume_words"
    )


# Useful semantic variants.

add("Mute the computer",
    tool_call("set_volume", level=0),
    category="volume_special")

add("Mute the sound",
    tool_call("set_volume", level=0),
    category="volume_special")

add("Set volume all the way down",
    tool_call("set_volume", level=0),
    category="volume_special")

add("Set the volume to max",
    tool_call("set_volume", level=100),
    category="volume_special")

add("Maximum volume",
    tool_call("set_volume", level=100),
    category="volume_special")

add("Put the sound at full volume",
    tool_call("set_volume", level=100),
    category="volume_special")

add("Set the audio halfway",
    tool_call("set_volume", level=50),
    category="volume_special")

add("Put the volume halfway",
    tool_call("set_volume", level=50),
    category="volume_special")


# ============================================================
# BRIGHTNESS
# ============================================================

BRIGHTNESS_VALUES = [
    0, 1, 5, 10, 15, 20, 25, 30,
    35, 40, 45, 50, 55, 60, 65,
    70, 75, 80, 85, 90, 95, 99, 100
]

BRIGHTNESS_TEMPLATES = [
    "Set brightness to {n}",
    "Brightness {n}",
    "Set screen brightness to {n}%",
    "Make my brightness {n} percent",
    "Put the screen brightness at {n}",
    "Change brightness to {n}",
    "Can you set the brightness to {n}?",
    "I want screen brightness at {n} percent",
    "Bring brightness to {n}",
]

for n in BRIGHTNESS_VALUES:
    for template in BRIGHTNESS_TEMPLATES:
        add(
            template.format(n=n),
            tool_call("set_brightness", level=n),
            category="brightness"
        )


for number, word in NUMBER_WORDS.items():
    add(
        f"Set brightness to {word} percent",
        tool_call("set_brightness", level=number),
        category="brightness_words"
    )

    add(
        f"Brightness {word}",
        tool_call("set_brightness", level=number),
        category="brightness_words"
    )


add("Maximum brightness",
    tool_call("set_brightness", level=100),
    category="brightness_special")

add("Set the screen brightness to max",
    tool_call("set_brightness", level=100),
    category="brightness_special")

add("Make the screen as bright as possible",
    tool_call("set_brightness", level=100),
    category="brightness_special")

add("Set brightness halfway",
    tool_call("set_brightness", level=50),
    category="brightness_special")

add("Put the screen brightness halfway",
    tool_call("set_brightness", level=50),
    category="brightness_special")


# ============================================================
# PAUSE
# ============================================================

PAUSE_PROMPTS = [
    "Pause",
    "Pause it",
    "Pause the music",
    "Pause my music",
    "Pause playback",
    "Pause the song",
    "Pause this song",
    "Pause the video",
    "Pause this video",
    "Hold the music",
    "Hold playback",
    "Stop playback for now",
    "Can you pause this?",
    "Can you pause the music?",
    "Please pause",
    "Pause whatever is playing",
    "Pause what's playing",
    "Hold this track",
    "Freeze playback",
    "I need to pause this",
    "Pause Spotify playback",
    "Pause the current track",
    "Pause the current media",
    "Pause what I'm listening to",
    "Pause what I'm watching",
]

for prompt in PAUSE_PROMPTS:
    add(prompt, tool_call("pause_media"), category="pause")


# ============================================================
# PLAY / RESUME
# ============================================================

PLAY_PROMPTS = [
    "Play",
    "Play it",
    "Resume",
    "Resume it",
    "Resume playback",
    "Resume the music",
    "Continue",
    "Continue playing",
    "Continue playback",
    "Keep playing",
    "Start playback",
    "Play the music",
    "Play my music",
    "Play the song",
    "Play this song",
    "Play the video",
    "Resume this video",
    "Can you resume it?",
    "Can you play this?",
    "Please resume",
    "Continue the current track",
    "Resume the current media",
    "Start the music again",
    "Continue what I was listening to",
    "Continue what I was watching",
]

for prompt in PLAY_PROMPTS:
    add(prompt, tool_call("play_media"), category="play")


# ============================================================
# SKIP
# ============================================================

SKIP_PROMPTS = [
    "Skip",
    "Skip it",
    "Skip this",
    "Skip this song",
    "Skip this track",
    "Skip the song",
    "Next song",
    "Next track",
    "Go to the next song",
    "Go to the next track",
    "Play the next song",
    "Move to the next track",
    "Can you skip this?",
    "Please skip this song",
    "I don't want this song",
    "Get rid of this song",
    "Move past this track",
    "Next please",
    "Skip whatever is playing",
    "Skip the current track",
    "Advance to the next track",
    "Go forward one song",
    "Switch songs",
    "Give me the next track",
    "Let's hear the next one",
]

for prompt in SKIP_PROMPTS:
    add(prompt, tool_call("skip_media"), category="skip")


# ============================================================
# WEBSITES
# ============================================================

WEBSITE_ALIASES = {
    "google_drive": [
        "Google Drive",
        "Drive",
        "my Google Drive",
        "drive.google.com",
    ],

    "github": [
        "GitHub",
        "Github",
        "git hub",
        "github.com",
    ],

    "google_docs": [
        "Google Docs",
        "Docs",
        "my Google Docs",
        "docs.google.com",
    ],

    "youtube": [
        "YouTube",
        "Youtube",
        "you tube",
        "youtube.com",
    ]
}

WEBSITE_TEMPLATES = [
    "Open {site}",
    "Go to {site}",
    "Take me to {site}",
    "Open {site} in Chrome",
    "Can you open {site}?",
    "Pull up {site}",
    "Navigate to {site}",
    "Launch {site} in the browser",
    "Bring up {site}",
    "I want to go to {site}",
    "Load {site}",
    "Visit {site}",
]

for canonical, aliases in WEBSITE_ALIASES.items():
    for alias in aliases:
        for template in WEBSITE_TEMPLATES:
            add(
                template.format(site=alias),
                tool_call("open_website", site=canonical),
                category="website"
            )


# ============================================================
# HARD / SEMANTIC DISAMBIGUATION EXAMPLES
# ============================================================

hard_examples = [

    (
        "I need to fix some code, bring up Visual Studio Code.",
        [tool_call("start_app", app="vscode")]
    ),

    (
        "I need my browser, use Chrome.",
        [tool_call("start_app", app="chrome")]
    ),

    (
        "Don't open GitHub, just launch Chrome.",
        [tool_call("start_app", app="chrome")]
    ),

    (
        "Open GitHub in my browser.",
        [tool_call("open_website", site="github")]
    ),

    (
        "Take me to GitHub, not the code editor.",
        [tool_call("open_website", site="github")]
    ),

    (
        "Launch VS Code, not GitHub.",
        [tool_call("start_app", app="vscode")]
    ),

    (
        "I need the actual Windows settings app.",
        [tool_call("start_app", app="settings")]
    ),

    (
        "Bring up my files, use File Explorer.",
        [tool_call("start_app", app="file_explorer")]
    ),

    (
        "Open Explorer so I can find a file.",
        [tool_call("start_app", app="file_explorer")]
    ),

    (
        "I need a command line. Open Command Prompt.",
        [tool_call("start_app", app="command_prompt")]
    ),

    (
        "Use cmd, not VS Code.",
        [tool_call("start_app", app="command_prompt")]
    ),

    (
        "Start Spotify but don't start playing anything yet.",
        [tool_call("start_app", app="spotify")]
    ),

    (
        "Open Spotify. Don't resume my music.",
        [tool_call("start_app", app="spotify")]
    ),

    (
        "Start Chrome, but don't go to YouTube.",
        [tool_call("start_app", app="chrome")]
    ),

    (
        "Open YouTube in Chrome. Don't launch Spotify.",
        [tool_call("open_website", site="youtube")]
    ),

    (
        "Open the YouTube website.",
        [tool_call("open_website", site="youtube")]
    ),

    (
        "Take me to Docs, not Drive.",
        [tool_call("open_website", site="google_docs")]
    ),

    (
        "Open Google Drive, not Google Docs.",
        [tool_call("open_website", site="google_drive")]
    ),

    (
        "I need my Drive files in Chrome.",
        [tool_call("open_website", site="google_drive")]
    ),

    (
        "Take me to the Google document site.",
        [tool_call("open_website", site="google_docs")]
    ),

    (
        "Set my volume to 30 and don't touch brightness.",
        [tool_call("set_volume", level=30)]
    ),

    (
        "Brightness to 30, leave my audio alone.",
        [tool_call("set_brightness", level=30)]
    ),

    (
        "Make the sound exactly 67 percent.",
        [tool_call("set_volume", level=67)]
    ),

    (
        "Make the screen exactly 67 percent brightness.",
        [tool_call("set_brightness", level=67)]
    ),

    (
        "The audio should be at 12%.",
        [tool_call("set_volume", level=12)]
    ),

    (
        "Screen brightness should be 12%.",
        [tool_call("set_brightness", level=12)]
    ),

    (
        "Could you put my sound at eighty percent?",
        [tool_call("set_volume", level=80)]
    ),

    (
        "Could you put my display at eighty percent brightness?",
        [tool_call("set_brightness", level=80)]
    ),

    (
        "Pause this one, don't skip it.",
        [tool_call("pause_media")]
    ),

    (
        "Skip this one, don't just pause it.",
        [tool_call("skip_media")]
    ),

    (
        "Continue playback, don't skip the track.",
        [tool_call("play_media")]
    ),

    (
        "Resume the song from where it stopped.",
        [tool_call("play_media")]
    ),

    (
        "Hold the current track where it is.",
        [tool_call("pause_media")]
    ),

    (
        "Move on from this track.",
        [tool_call("skip_media")]
    ),

    (
        "I'm done with this song, give me the next one.",
        [tool_call("skip_media")]
    ),

    (
        "The song is fine, just pause it for a second.",
        [tool_call("pause_media")]
    ),

    (
        "Start my code editor.",
        [tool_call("start_app", app="vscode")]
    ),

    (
        "Bring up the Windows file browser.",
        [tool_call("start_app", app="file_explorer")]
    ),

    (
        "Open the Windows configuration panel.",
        [tool_call("start_app", app="settings")]
    ),

    (
        "Pull up the Chat GPT desktop app.",
        [tool_call("start_app", app="chatgpt")]
    ),

    (
        "I want the browser itself, not a specific website.",
        [tool_call("start_app", app="chrome")]
    ),
]

for prompt, calls in hard_examples:
    add(prompt, *calls, category="hard")


# ============================================================
# MULTIPLE COMMANDS IN ONE UTTERANCE
#
# FunctionGemma can emit more than one tool call in a turn.
# ============================================================

multi_examples = [

    (
        "Set volume to 30 and brightness to 70.",
        [
            tool_call("set_volume", level=30),
            tool_call("set_brightness", level=70),
        ]
    ),

    (
        "Brightness 80 and volume 20.",
        [
            tool_call("set_brightness", level=80),
            tool_call("set_volume", level=20),
        ]
    ),

    (
        "Set my screen to 50 percent and my sound to 25 percent.",
        [
            tool_call("set_brightness", level=50),
            tool_call("set_volume", level=25),
        ]
    ),

    (
        "Pause the music and lower the volume to 15.",
        [
            tool_call("pause_media"),
            tool_call("set_volume", level=15),
        ]
    ),

    (
        "Set volume to 40 then resume playback.",
        [
            tool_call("set_volume", level=40),
            tool_call("play_media"),
        ]
    ),

    (
        "Skip this song and set volume to 60.",
        [
            tool_call("skip_media"),
            tool_call("set_volume", level=60),
        ]
    ),

    (
        "Open Spotify and set my volume to 35.",
        [
            tool_call("start_app", app="spotify"),
            tool_call("set_volume", level=35),
        ]
    ),

    (
        "Launch Chrome and make the screen brightness 70.",
        [
            tool_call("start_app", app="chrome"),
            tool_call("set_brightness", level=70),
        ]
    ),

    (
        "Open VS Code and set brightness to 40.",
        [
            tool_call("start_app", app="vscode"),
            tool_call("set_brightness", level=40),
        ]
    ),

    (
        "Start Notion and turn my volume down to 20.",
        [
            tool_call("start_app", app="notion"),
            tool_call("set_volume", level=20),
        ]
    ),

    (
        "Pause what's playing and open Google Drive.",
        [
            tool_call("pause_media"),
            tool_call("open_website", site="google_drive"),
        ]
    ),

    (
        "Open GitHub and set brightness to 65.",
        [
            tool_call("open_website", site="github"),
            tool_call("set_brightness", level=65),
        ]
    ),

    (
        "Take me to YouTube and set volume to 25.",
        [
            tool_call("open_website", site="youtube"),
            tool_call("set_volume", level=25),
        ]
    ),

    (
        "Open Google Docs and mute the computer.",
        [
            tool_call("open_website", site="google_docs"),
            tool_call("set_volume", level=0),
        ]
    ),

    (
        "Skip the song and bring up VS Code.",
        [
            tool_call("skip_media"),
            tool_call("start_app", app="vscode"),
        ]
    ),

    (
        "Start Spotify then play the music.",
        [
            tool_call("start_app", app="spotify"),
            tool_call("play_media"),
        ]
    ),

    (
        "Pause playback and bring up File Explorer.",
        [
            tool_call("pause_media"),
            tool_call("start_app", app="file_explorer"),
        ]
    ),

    (
        "Brightness 90, volume 50, and open GitHub.",
        [
            tool_call("set_brightness", level=90),
            tool_call("set_volume", level=50),
            tool_call("open_website", site="github"),
        ]
    ),

    (
        "Set volume to 10, set brightness to 80, then open YouTube.",
        [
            tool_call("set_volume", level=10),
            tool_call("set_brightness", level=80),
            tool_call("open_website", site="youtube"),
        ]
    ),
]

for prompt, calls in multi_examples:
    add(prompt, *calls, category="multi")


# ============================================================
# ASR / SPEECH-LIKE INPUTS
#
# These are particularly important if Deepgram / voice input is
# feeding FunctionGemma.
# ============================================================

speech_examples = [

    (
        "hey can you open chrome for me",
        [tool_call("start_app", app="chrome")]
    ),

    (
        "uh start spotify",
        [tool_call("start_app", app="spotify")]
    ),

    (
        "okay open visual studio code",
        [tool_call("start_app", app="vscode")]
    ),

    (
        "can you pull up command prompt",
        [tool_call("start_app", app="command_prompt")]
    ),

    (
        "open chat gpt",
        [tool_call("start_app", app="chatgpt")]
    ),

    (
        "pull up file explorer please",
        [tool_call("start_app", app="file_explorer")]
    ),

    (
        "open the settings thing",
        [tool_call("start_app", app="settings")]
    ),

    (
        "take me to git hub",
        [tool_call("open_website", site="github")]
    ),

    (
        "go to you tube",
        [tool_call("open_website", site="youtube")]
    ),

    (
        "open google docs real quick",
        [tool_call("open_website", site="google_docs")]
    ),

    (
        "pull up my google drive",
        [tool_call("open_website", site="google_drive")]
    ),

    (
        "volume uh fifty",
        [tool_call("set_volume", level=50)]
    ),

    (
        "set volume to like thirty percent",
        [tool_call("set_volume", level=30)]
    ),

    (
        "make the volume exactly twenty five",
        [tool_call("set_volume", level=25)]
    ),

    (
        "brightness um seventy",
        [tool_call("set_brightness", level=70)]
    ),

    (
        "set screen brightness to like forty percent",
        [tool_call("set_brightness", level=40)]
    ),

    (
        "pause pause the music",
        [tool_call("pause_media")]
    ),

    (
        "yeah skip this song",
        [tool_call("skip_media")]
    ),

    (
        "okay resume it",
        [tool_call("play_media")]
    ),

    (
        "can you just pause whatever's playing",
        [tool_call("pause_media")]
    ),

    (
        "next song please",
        [tool_call("skip_media")]
    ),

    (
        "resume the music please",
        [tool_call("play_media")]
    ),
]

for prompt, calls in speech_examples:
    add(prompt, *calls, category="speech")


# ============================================================
# CLARIFICATION / NEGATIVE EXAMPLES
# ============================================================

if INCLUDE_CLARIFY_TOOL:

    clarify_examples = [

        (
            "Turn the volume up.",
            "missing_volume"
        ),

        (
            "Make it louder.",
            "missing_volume"
        ),

        (
            "Change the sound.",
            "missing_volume"
        ),

        (
            "Set the volume.",
            "missing_volume"
        ),

        (
            "Lower the volume.",
            "missing_volume"
        ),

        (
            "Make the screen brighter.",
            "missing_brightness"
        ),

        (
            "Turn brightness down.",
            "missing_brightness"
        ),

        (
            "Change my brightness.",
            "missing_brightness"
        ),

        (
            "Set the brightness.",
            "missing_brightness"
        ),

        (
            "Make the display darker.",
            "missing_brightness"
        ),

        (
            "Set it to 50.",
            "ambiguous_target"
        ),

        (
            "Make it 25 percent.",
            "ambiguous_target"
        ),

        (
            "Put it at 70.",
            "ambiguous_target"
        ),

        (
            "Change that to 30.",
            "ambiguous_target"
        ),

        (
            "Set that to one hundred.",
            "ambiguous_target"
        ),

        (
            "Start Discord.",
            "unsupported_app"
        ),

        (
            "Open Steam.",
            "unsupported_app"
        ),

        (
            "Launch Excel.",
            "unsupported_app"
        ),

        (
            "Start Word.",
            "unsupported_app"
        ),

        (
            "Open PowerPoint.",
            "unsupported_app"
        ),

        (
            "Open Reddit.",
            "unsupported_website"
        ),

        (
            "Go to Twitter.",
            "unsupported_website"
        ),

        (
            "Open Wikipedia.",
            "unsupported_website"
        ),

        (
            "Take me to Stack Overflow.",
            "unsupported_website"
        ),

        (
            "Open Gmail.",
            "unsupported_website"
        ),

        (
            "What's the weather?",
            "unsupported_command"
        ),

        (
            "What time is it?",
            "unsupported_command"
        ),

        (
            "Tell me a joke.",
            "unsupported_command"
        ),

        (
            "Write some Python code.",
            "unsupported_command"
        ),

        (
            "Search the internet for laptops.",
            "unsupported_command"
        ),
    ]

    for prompt, issue in clarify_examples:
        add(
            prompt,
            tool_call("clarify", issue=issue),
            category="clarify"
        )


# ============================================================
# EXTRA DIFFICULT EXAMPLES
# ============================================================

difficult_examples = [

    (
        "I don't want VS Code right now; give me Command Prompt instead.",
        [tool_call("start_app", app="command_prompt")]
    ),

    (
        "Not Drive. I meant Google Docs.",
        [tool_call("open_website", site="google_docs")]
    ),

    (
        "I said Drive, not Docs.",
        [tool_call("open_website", site="google_drive")]
    ),

    (
        "Don't pause it. Skip the track.",
        [tool_call("skip_media")]
    ),

    (
        "Don't skip it. Just pause.",
        [tool_call("pause_media")]
    ),

    (
        "Don't start Spotify; open Chrome.",
        [tool_call("start_app", app="chrome")]
    ),

    (
        "Instead of Chrome, start ChatGPT.",
        [tool_call("start_app", app="chatgpt")]
    ),

    (
        "Forget GitHub. Open YouTube.",
        [tool_call("open_website", site="youtube")]
    ),

    (
        "Actually, make volume 42.",
        [tool_call("set_volume", level=42)]
    ),

    (
        "No, brightness should be 42.",
        [tool_call("set_brightness", level=42)]
    ),

    (
        "Sound at 73 percent please.",
        [tool_call("set_volume", level=73)]
    ),

    (
        "Display at 73 percent please.",
        [tool_call("set_brightness", level=73)]
    ),

    (
        "Audio fifty five, screen eighty.",
        [
            tool_call("set_volume", level=55),
            tool_call("set_brightness", level=80)
        ]
    ),

    (
        "Screen twenty and sound ninety.",
        [
            tool_call("set_brightness", level=20),
            tool_call("set_volume", level=90)
        ]
    ),

    (
        "Pause this and open Docs.",
        [
            tool_call("pause_media"),
            tool_call("open_website", site="google_docs")
        ]
    ),

    (
        "Next song, then pull up GitHub.",
        [
            tool_call("skip_media"),
            tool_call("open_website", site="github")
        ]
    ),

    (
        "Resume playback and bring Notion up.",
        [
            tool_call("play_media"),
            tool_call("start_app", app="notion")
        ]
    ),

    (
        "Open the browser itself.",
        [tool_call("start_app", app="chrome")]
    ),

    (
        "Open the GitHub site in the browser.",
        [tool_call("open_website", site="github")]
    ),

    (
        "Start the desktop Spotify application.",
        [tool_call("start_app", app="spotify")]
    ),

    (
        "Go to YouTube's website.",
        [tool_call("open_website", site="youtube")]
    ),

    (
        "I need Microsoft's file manager.",
        [tool_call("start_app", app="file_explorer")]
    ),

    (
        "I need Microsoft's settings screen.",
        [tool_call("start_app", app="settings")]
    ),

    (
        "Open my editor — VS Code.",
        [tool_call("start_app", app="vscode")]
    ),

    (
        "Open my terminal — specifically cmd.",
        [tool_call("start_app", app="command_prompt")]
    ),

    (
        "Bring the screen down to 17 percent brightness.",
        [tool_call("set_brightness", level=17)]
    ),

    (
        "Bring the speakers down to 17 percent.",
        [tool_call("set_volume", level=17)]
    ),

    (
        "Music is playing; hold it where it is.",
        [tool_call("pause_media")]
    ),

    (
        "Music is paused; continue from there.",
        [tool_call("play_media")]
    ),

    (
        "I'm tired of this track. Move on.",
        [tool_call("skip_media")]
    ),
]

for prompt, calls in difficult_examples:
    add(prompt, *calls, category="difficult")


# ============================================================
# DEDUPLICATE
# ============================================================

unique = []
seen = set()

for item in examples:
    key = item["user"].strip().lower()

    if key not in seen:
        seen.add(key)
        unique.append(item)

examples = unique


# ============================================================
# CONVERT TO FUNCTIONGEMMA CONVERSATION FORMAT
# ============================================================

def convert(example):
    return {
        "messages": [
            {
                "role": "developer",
                "content": DEVELOPER_MESSAGE
            },
            {
                "role": "user",
                "content": example["user"]
            },
            {
                "role": "assistant",
                "tool_calls": example["calls"]
            }
        ],
        "tools": TOOLS
    }


# ============================================================
# HELD-OUT EVALUATION SET
#
# Keep these OUT of training.
# ============================================================

eval_examples = [

    (
        "Could you get Google's browser running?",
        [tool_call("start_app", app="chrome")]
    ),

    (
        "Bring the code editor up for me.",
        [tool_call("start_app", app="vscode")]
    ),

    (
        "I need to poke around my files.",
        [tool_call("start_app", app="file_explorer")]
    ),

    (
        "Give me a cmd window.",
        [tool_call("start_app", app="command_prompt")]
    ),

    (
        "Bring up the Windows configuration app.",
        [tool_call("start_app", app="settings")]
    ),

    (
        "I need Chat GPT on screen.",
        [tool_call("start_app", app="chatgpt")]
    ),

    (
        "Fire up Spotify.",
        [tool_call("start_app", app="spotify")]
    ),

    (
        "Bring my Notion workspace up.",
        [tool_call("start_app", app="notion")]
    ),

    (
        "Audio at thirty-seven percent.",
        [tool_call("set_volume", level=37)]
    ),

    (
        "Set my speakers to 82.",
        [tool_call("set_volume", level=82)]
    ),

    (
        "Display brightness at thirty-seven percent.",
        [tool_call("set_brightness", level=37)]
    ),

    (
        "Put my screen at 82.",
        [tool_call("set_brightness", level=82)]
    ),

    (
        "Hold whatever I'm listening to.",
        [tool_call("pause_media")]
    ),

    (
        "Carry on with the music.",
        [tool_call("play_media")]
    ),

    (
        "I'm over this song.",
        [tool_call("skip_media")]
    ),

    (
        "Pull up the code hosting site.",
        [tool_call("open_website", site="github")]
    ),

    (
        "Take me to Google's document editor.",
        [tool_call("open_website", site="google_docs")]
    ),

    (
        "Take me to my Drive files.",
        [tool_call("open_website", site="google_drive")]
    ),

    (
        "Bring up the YouTube site.",
        [tool_call("open_website", site="youtube")]
    ),

    (
        "Set audio to 22 and the display to 71.",
        [
            tool_call("set_volume", level=22),
            tool_call("set_brightness", level=71)
        ]
    ),

    (
        "Pause this track and bring up my files.",
        [
            tool_call("pause_media"),
            tool_call("start_app", app="file_explorer")
        ]
    ),

    (
        "Next track and take me to GitHub.",
        [
            tool_call("skip_media"),
            tool_call("open_website", site="github")
        ]
    ),
]


# Add eval-only guard examples.

if INCLUDE_CLARIFY_TOOL:
    eval_examples.extend([
        (
            "Turn that down.",
            [tool_call("clarify", issue="ambiguous_target")]
        ),
        (
            "Make my speakers quieter.",
            [tool_call("clarify", issue="missing_volume")]
        ),
        (
            "Make my display brighter.",
            [tool_call("clarify", issue="missing_brightness")]
        ),
        (
            "Launch Photoshop.",
            [tool_call("clarify", issue="unsupported_app")]
        ),
        (
            "Go to Amazon.",
            [tool_call("clarify", issue="unsupported_website")]
        ),
    ])


eval_rows = []

for prompt, calls in eval_examples:
    eval_rows.append(
        convert({
            "user": prompt,
            "calls": calls,
            "category": "evaluation"
        })
    )


# ============================================================
# SHUFFLE + WRITE JSONL
# ============================================================

random.shuffle(examples)

train_rows = [convert(example) for example in examples]

with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
    for row in train_rows:
        f.write(json.dumps(row, ensure_ascii=False) + "\n")

with open(EVAL_FILE, "w", encoding="utf-8") as f:
    for row in eval_rows:
        f.write(json.dumps(row, ensure_ascii=False) + "\n")


print(f"Training examples: {len(train_rows)}")
print(f"Evaluation examples: {len(eval_rows)}")
print(f"Saved training data -> {Path(OUTPUT_FILE).resolve()}")
print(f"Saved evaluation data -> {Path(EVAL_FILE).resolve()}")