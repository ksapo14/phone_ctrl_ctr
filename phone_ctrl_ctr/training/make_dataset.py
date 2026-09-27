import json
import random
from pathlib import Path
from collections import Counter


# ============================================================
# CONFIG
# ============================================================

SEED = 42
random.seed(SEED)

TRAIN_FILE = "desktop_commands_train.jsonl"
EVAL_FILE = "desktop_commands_eval.jsonl"
STATS_FILE = "desktop_commands_stats.json"

# Optional.
#
# After deploying/testing the model, you can create:
#
# real_failures.jsonl
#
# with lines like:
#
# {
#   "user": "yo put the sound at like forty two",
#   "calls": [
#     {
#       "name": "set_volume",
#       "arguments": {
#         "level": 42
#       }
#     }
#   ]
# }
#
# These will automatically be added to the NEXT dataset build.
REAL_FAILURES_FILE = "real_failures.jsonl"


# Keep this consistent between dataset generation and inference.
DEVELOPER_MESSAGE = (
    "You are a model that can do function calling with the following functions"
)


# ============================================================
# CANONICAL VALUES
# ============================================================

APPS = [
    "chrome",
    "chatgpt",
    "spotify",
    "vscode",
    "command_prompt",
    "file_explorer",
    "notion",
    "settings",
]

SITES = [
    "google_drive",
    "github",
    "google_docs",
    "youtube",
]


# ============================================================
# TOOL DEFINITIONS
# ============================================================

TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "start_app",
            "description": (
                "Start or focus a supported desktop application."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "app": {
                        "type": "string",
                        "enum": APPS,
                        "description": (
                            "Canonical identifier of the application."
                        ),
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
            "description": (
                "Set the computer's audio volume to an absolute "
                "percentage from 0 to 100."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "level": {
                        "type": "integer",
                        "minimum": 0,
                        "maximum": 100,
                        "description": (
                            "Absolute volume percentage."
                        ),
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
            "description": (
                "Set the computer display brightness to an absolute "
                "percentage from 0 to 100."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "level": {
                        "type": "integer",
                        "minimum": 0,
                        "maximum": 100,
                        "description": (
                            "Absolute brightness percentage."
                        ),
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
            "description": (
                "Pause currently playing media."
            ),
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
            "description": (
                "Play or resume currently paused media."
            ),
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
            "description": (
                "Skip the current media item and advance to the next one."
            ),
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
            "description": (
                "Open a supported website in Google Chrome."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "site": {
                        "type": "string",
                        "enum": SITES,
                        "description": (
                            "Canonical identifier of the website."
                        ),
                    }
                },
                "required": ["site"],
            },
        },
    },
]


# ============================================================
# HELPERS
# ============================================================

def tool_call(name, **arguments):
    return {
        "type": "function",
        "function": {
            "name": name,
            "arguments": arguments,
        },
    }


def normalize_text(text):
    return " ".join(
        text.lower().strip().split()
    )


def canonical_json(value):
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
    )


def number_to_words(n):
    """
    Convert an integer from 0-100 into English words.

    Used for speech-like examples:
        42 -> "forty two"
    """

    ones = [
        "zero",
        "one",
        "two",
        "three",
        "four",
        "five",
        "six",
        "seven",
        "eight",
        "nine",
        "ten",
        "eleven",
        "twelve",
        "thirteen",
        "fourteen",
        "fifteen",
        "sixteen",
        "seventeen",
        "eighteen",
        "nineteen",
    ]

    tens = {
        20: "twenty",
        30: "thirty",
        40: "forty",
        50: "fifty",
        60: "sixty",
        70: "seventy",
        80: "eighty",
        90: "ninety",
    }

    if 0 <= n < 20:
        return ones[n]

    if n == 100:
        return "one hundred"

    tens_value = (n // 10) * 10
    ones_value = n % 10

    if ones_value == 0:
        return tens[tens_value]

    return (
        tens[tens_value]
        + " "
        + ones[ones_value]
    )


# ============================================================
# DATA STORAGE
# ============================================================

train_examples = []
eval_examples = []


def add_train(
    user,
    calls,
    category,
    source="generated",
):

    train_examples.append({
        "user": user.strip(),
        "calls": calls,
        "category": category,
        "source": source,
    })


def add_eval(
    user,
    calls,
    category,
):

    eval_examples.append({
        "user": user.strip(),
        "calls": calls,
        "category": category,
        "source": "held_out",
    })


# ============================================================
# APPLICATION COMMANDS
# ============================================================

APP_ALIASES = {
    "chrome": [
        "Chrome",
        "Google Chrome",
        "the Chrome browser",
        "Google's browser",
        "my browser",
    ],

    "chatgpt": [
        "ChatGPT",
        "Chat GPT",
        "the ChatGPT app",
        "the Chat GPT app",
    ],

    "spotify": [
        "Spotify",
        "the Spotify app",
        "Spotify desktop",
        "my Spotify",
    ],

    "vscode": [
        "VS Code",
        "VSCode",
        "Visual Studio Code",
        "the VS Code editor",
        "my code editor",
    ],

    "command_prompt": [
        "Command Prompt",
        "command prompt",
        "CMD",
        "cmd",
        "a command prompt window",
        "the Windows command prompt",
    ],

    "file_explorer": [
        "File Explorer",
        "Windows File Explorer",
        "Explorer",
        "the file explorer",
        "the Windows file browser",
    ],

    "notion": [
        "Notion",
        "the Notion app",
        "Notion desktop",
        "my Notion",
    ],

    "settings": [
        "Settings",
        "Windows Settings",
        "the settings app",
        "system settings",
        "Windows settings",
    ],
}


APP_TEMPLATES = [
    "Start {app}",
    "Open {app}",
    "Launch {app}",
    "Bring up {app}",
    "Pull up {app}",
    "Get {app} running",
    "Switch me to {app}",
    "Bring {app} to the front",
    "Can you start {app}",
    "Can you open {app}",
    "I need {app}",
    "I'd like to use {app}",
    "Go ahead and launch {app}",
    "Put {app} on screen",
    "Get me into {app}",
]


for canonical_app, aliases in APP_ALIASES.items():

    for alias in aliases:

        for template in APP_TEMPLATES:

            add_train(
                template.format(
                    app=alias
                ),
                [
                    tool_call(
                        "start_app",
                        app=canonical_app,
                    )
                ],
                category="start_app",
            )


# ============================================================
# VOLUME
# ============================================================

VOLUME_TEMPLATES = [
    "Volume {n}",
    "Set volume to {n}",
    "Set my volume to {n}",
    "Set volume to {n} percent",
    "Put the volume at {n}",
    "Audio {n}",
    "Set audio to {n}",
    "Make the sound {n} percent",
    "Set the speakers to {n}",
    "Put my sound at {n}",
]


# Every integer from 0 to 100 appears several times.
for n in range(101):

    chosen = random.sample(
        VOLUME_TEMPLATES,
        k=5,
    )

    for template in chosen:

        add_train(
            template.format(n=n),
            [
                tool_call(
                    "set_volume",
                    level=n,
                )
            ],
            category="volume_numeric",
        )


# Every integer also gets at least one spoken-number form.
for n in range(101):

    words = number_to_words(n)

    add_train(
        f"Set the volume to {words} percent",
        [
            tool_call(
                "set_volume",
                level=n,
            )
        ],
        category="volume_words",
    )

    add_train(
        f"Put my sound at {words}",
        [
            tool_call(
                "set_volume",
                level=n,
            )
        ],
        category="volume_words",
    )


# ============================================================
# BRIGHTNESS
# ============================================================

BRIGHTNESS_TEMPLATES = [
    "Brightness {n}",
    "Set brightness to {n}",
    "Set my brightness to {n}",
    "Set brightness to {n} percent",
    "Put the brightness at {n}",
    "Screen brightness {n}",
    "Display brightness {n}",
    "Make the screen {n} percent brightness",
    "Set the display to {n} percent brightness",
    "Put my screen at {n}",
]


for n in range(101):

    chosen = random.sample(
        BRIGHTNESS_TEMPLATES,
        k=5,
    )

    for template in chosen:

        add_train(
            template.format(n=n),
            [
                tool_call(
                    "set_brightness",
                    level=n,
                )
            ],
            category="brightness_numeric",
        )


for n in range(101):

    words = number_to_words(n)

    add_train(
        f"Set brightness to {words} percent",
        [
            tool_call(
                "set_brightness",
                level=n,
            )
        ],
        category="brightness_words",
    )

    add_train(
        f"Put my display at {words}",
        [
            tool_call(
                "set_brightness",
                level=n,
            )
        ],
        category="brightness_words",
    )


# ============================================================
# SEMANTIC VOLUME / BRIGHTNESS
# ============================================================

SPECIAL_CASES = [
    (
        "Mute",
        [tool_call("set_volume", level=0)],
        "volume_semantic",
    ),

    (
        "Mute the computer",
        [tool_call("set_volume", level=0)],
        "volume_semantic",
    ),

    (
        "Mute the sound",
        [tool_call("set_volume", level=0)],
        "volume_semantic",
    ),

    (
        "Mute the audio",
        [tool_call("set_volume", level=0)],
        "volume_semantic",
    ),

    (
        "Set the volume all the way down",
        [tool_call("set_volume", level=0)],
        "volume_semantic",
    ),

    (
        "Maximum volume",
        [tool_call("set_volume", level=100)],
        "volume_semantic",
    ),

    (
        "Set volume to max",
        [tool_call("set_volume", level=100)],
        "volume_semantic",
    ),

    (
        "Put the speakers at full volume",
        [tool_call("set_volume", level=100)],
        "volume_semantic",
    ),

    (
        "Put the volume halfway",
        [tool_call("set_volume", level=50)],
        "volume_semantic",
    ),

    (
        "Set the audio halfway",
        [tool_call("set_volume", level=50)],
        "volume_semantic",
    ),

    (
        "Maximum brightness",
        [tool_call("set_brightness", level=100)],
        "brightness_semantic",
    ),

    (
        "Set brightness to max",
        [tool_call("set_brightness", level=100)],
        "brightness_semantic",
    ),

    (
        "Make the display as bright as possible",
        [tool_call("set_brightness", level=100)],
        "brightness_semantic",
    ),

    (
        "Put brightness halfway",
        [tool_call("set_brightness", level=50)],
        "brightness_semantic",
    ),

    (
        "Set the screen halfway",
        [tool_call("set_brightness", level=50)],
        "brightness_semantic",
    ),
]


for user, calls, category in SPECIAL_CASES:

    add_train(
        user,
        calls,
        category,
    )


# ============================================================
# MEDIA CONTROLS
# ============================================================

PAUSE_PHRASES = [
    "Pause",
    "Pause it",
    "Pause this",
    "Pause playback",
    "Pause the music",
    "Pause my music",
    "Pause the song",
    "Pause this song",
    "Pause the video",
    "Pause this video",
    "Hold the music",
    "Hold playback",
    "Hold this track",
    "Pause whatever is playing",
    "Pause what's playing",
    "Freeze playback",
    "Stop playback for now",
    "Hold it there",
    "Pause the current media",
    "Pause what I'm listening to",
    "Pause what I'm watching",
    "Can you pause this",
    "Can you pause the music",
    "Please pause playback",
    "Stop the music for a second",
    "Hold this song right here",
]


PLAY_PHRASES = [
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
    "Play this song",
    "Play the video",
    "Resume this video",
    "Continue the current track",
    "Resume the current media",
    "Start the music again",
    "Continue what I was listening to",
    "Continue what I was watching",
    "Can you resume it",
    "Can you play this",
    "Keep it going",
    "Start it again",
    "Continue the song",
]


SKIP_PHRASES = [
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
    "Can you skip this",
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
    "Move on from this one",
    "I'm done with this track",
]


for phrase in PAUSE_PHRASES:

    add_train(
        phrase,
        [tool_call("pause_media")],
        category="pause",
    )


for phrase in PLAY_PHRASES:

    add_train(
        phrase,
        [tool_call("play_media")],
        category="play",
    )


for phrase in SKIP_PHRASES:

    add_train(
        phrase,
        [tool_call("skip_media")],
        category="skip",
    )


# ============================================================
# WEBSITES
# ============================================================

SITE_ALIASES = {
    "google_drive": [
        "Google Drive",
        "Drive",
        "my Google Drive",
        "drive.google.com",
        "the Google Drive site",
    ],

    "github": [
        "GitHub",
        "Github",
        "git hub",
        "github.com",
        "the GitHub site",
    ],

    "google_docs": [
        "Google Docs",
        "Docs",
        "my Google Docs",
        "docs.google.com",
        "the Google Docs site",
    ],

    "youtube": [
        "YouTube",
        "Youtube",
        "you tube",
        "youtube.com",
        "the YouTube site",
    ],
}


SITE_TEMPLATES = [
    "Open {site}",
    "Go to {site}",
    "Take me to {site}",
    "Open {site} in Chrome",
    "Pull up {site}",
    "Navigate to {site}",
    "Launch {site} in the browser",
    "Bring up {site}",
    "I want to go to {site}",
    "Load {site}",
    "Visit {site}",
    "Can you open {site}",
    "Open the website for {site}",
]


for canonical_site, aliases in SITE_ALIASES.items():

    for alias in aliases:

        for template in SITE_TEMPLATES:

            add_train(
                template.format(
                    site=alias
                ),
                [
                    tool_call(
                        "open_website",
                        site=canonical_site,
                    )
                ],
                category="website",
            )


# ============================================================
# HARD / NEGATION / DISAMBIGUATION
# ============================================================

HARD_EXAMPLES = [
    (
        "Don't open GitHub, just launch Chrome",
        [tool_call("start_app", app="chrome")],
    ),

    (
        "Launch VS Code, not GitHub",
        [tool_call("start_app", app="vscode")],
    ),

    (
        "Open GitHub in the browser, not VS Code",
        [tool_call("open_website", site="github")],
    ),

    (
        "I want the browser itself, not a website",
        [tool_call("start_app", app="chrome")],
    ),

    (
        "Open the GitHub website",
        [tool_call("open_website", site="github")],
    ),

    (
        "Start Spotify but don't play anything yet",
        [tool_call("start_app", app="spotify")],
    ),

    (
        "Open Spotify but leave playback alone",
        [tool_call("start_app", app="spotify")],
    ),

    (
        "Don't start Spotify, launch Chrome instead",
        [tool_call("start_app", app="chrome")],
    ),

    (
        "Take me to Docs, not Drive",
        [tool_call("open_website", site="google_docs")],
    ),

    (
        "Open Drive, not Docs",
        [tool_call("open_website", site="google_drive")],
    ),

    (
        "I said Google Drive, not Google Docs",
        [tool_call("open_website", site="google_drive")],
    ),

    (
        "Not Drive, I meant Google Docs",
        [tool_call("open_website", site="google_docs")],
    ),

    (
        "Pause this one, don't skip it",
        [tool_call("pause_media")],
    ),

    (
        "Skip this one, don't pause it",
        [tool_call("skip_media")],
    ),

    (
        "Resume it, don't skip the track",
        [tool_call("play_media")],
    ),

    (
        "Don't resume it, just skip it",
        [tool_call("skip_media")],
    ),

    (
        "Set volume to 31 and don't touch brightness",
        [tool_call("set_volume", level=31)],
    ),

    (
        "Brightness 31, leave the audio alone",
        [tool_call("set_brightness", level=31)],
    ),

    (
        "Make the speakers exactly 67 percent",
        [tool_call("set_volume", level=67)],
    ),

    (
        "Make the display exactly 67 percent",
        [tool_call("set_brightness", level=67)],
    ),

    (
        "The audio should be at 12 percent, not brightness",
        [tool_call("set_volume", level=12)],
    ),

    (
        "Screen brightness should be 12 percent, not volume",
        [tool_call("set_brightness", level=12)],
    ),

    (
        "I need a command line, open cmd",
        [tool_call("start_app", app="command_prompt")],
    ),

    (
        "Open the Windows file browser",
        [tool_call("start_app", app="file_explorer")],
    ),

    (
        "Open the Windows configuration app",
        [tool_call("start_app", app="settings")],
    ),

    (
        "Start my code editor",
        [tool_call("start_app", app="vscode")],
    ),

    (
        "Start Google's browser",
        [tool_call("start_app", app="chrome")],
    ),

    (
        "I'm tired of this song, move on",
        [tool_call("skip_media")],
    ),

    (
        "Hold this song where it is",
        [tool_call("pause_media")],
    ),

    (
        "Continue from where the song stopped",
        [tool_call("play_media")],
    ),

    (
        "I don't want a new song, pause this one",
        [tool_call("pause_media")],
    ),

    (
        "Don't pause, just go to the next song",
        [tool_call("skip_media")],
    ),

    (
        "Open the actual Windows settings application",
        [tool_call("start_app", app="settings")],
    ),

    (
        "Bring up Explorer so I can find a file",
        [tool_call("start_app", app="file_explorer")],
    ),

    (
        "Use cmd, not VS Code",
        [tool_call("start_app", app="command_prompt")],
    ),

    (
        "Use VS Code, not command prompt",
        [tool_call("start_app", app="vscode")],
    ),

    (
        "Open YouTube in Chrome, don't start Spotify",
        [tool_call("open_website", site="youtube")],
    ),

    (
        "Start Chrome, but don't go to YouTube",
        [tool_call("start_app", app="chrome")],
    ),
]


for user, calls in HARD_EXAMPLES:

    add_train(
        user,
        calls,
        category="hard",
    )


# ============================================================
# ASR / DEEPGRAM STYLE EXAMPLES
# ============================================================

ASR_EXAMPLES = [
    (
        "hey can you open chrome for me",
        [tool_call("start_app", app="chrome")],
    ),

    (
        "uh start spotify",
        [tool_call("start_app", app="spotify")],
    ),

    (
        "okay open visual studio code",
        [tool_call("start_app", app="vscode")],
    ),

    (
        "yo pull up command prompt",
        [tool_call("start_app", app="command_prompt")],
    ),

    (
        "open chat g p t",
        [tool_call("start_app", app="chatgpt")],
    ),

    (
        "pull up file explorer real quick",
        [tool_call("start_app", app="file_explorer")],
    ),

    (
        "open settings for me",
        [tool_call("start_app", app="settings")],
    ),

    (
        "take me to git hub",
        [tool_call("open_website", site="github")],
    ),

    (
        "go to you tube",
        [tool_call("open_website", site="youtube")],
    ),

    (
        "open google docs real quick",
        [tool_call("open_website", site="google_docs")],
    ),

    (
        "pull up my google drive",
        [tool_call("open_website", site="google_drive")],
    ),

    (
        "volume uh fifty",
        [tool_call("set_volume", level=50)],
    ),

    (
        "set volume to like thirty percent",
        [tool_call("set_volume", level=30)],
    ),

    (
        "make the sound exactly twenty five",
        [tool_call("set_volume", level=25)],
    ),

    (
        "brightness um seventy",
        [tool_call("set_brightness", level=70)],
    ),

    (
        "set screen brightness to like forty percent",
        [tool_call("set_brightness", level=40)],
    ),

    (
        "pause pause the music",
        [tool_call("pause_media")],
    ),

    (
        "yeah skip this song",
        [tool_call("skip_media")],
    ),

    (
        "okay resume it",
        [tool_call("play_media")],
    ),

    (
        "can you just pause whatever is playing",
        [tool_call("pause_media")],
    ),

    (
        "uh next song please",
        [tool_call("skip_media")],
    ),

    (
        "yeah continue the music",
        [tool_call("play_media")],
    ),

    (
        "hey uh bring up notion",
        [tool_call("start_app", app="notion")],
    ),

    (
        "okay can you put my audio at sixty",
        [tool_call("set_volume", level=60)],
    ),

    (
        "um set the screen to like thirty five",
        [tool_call("set_brightness", level=35)],
    ),
]


for user, calls in ASR_EXAMPLES:

    add_train(
        user,
        calls,
        category="asr",
    )


# ============================================================
# GENERATED ASR NUMERIC EXAMPLES
# ============================================================

ASR_VOLUME_TEMPLATES = [
    "uh volume {words}",
    "okay sound at {words}",
    "hey put the volume at {words}",
    "can you set audio to {words}",
    "yeah make the sound {words} percent",
]


ASR_BRIGHTNESS_TEMPLATES = [
    "uh brightness {words}",
    "okay screen at {words}",
    "hey put the brightness at {words}",
    "can you set display brightness to {words}",
    "yeah make the screen {words} percent",
]


# Generate additional speech-like cases over varying values.
for n in range(0, 101, 2):

    words = number_to_words(n)

    volume_template = random.choice(
        ASR_VOLUME_TEMPLATES
    )

    brightness_template = random.choice(
        ASR_BRIGHTNESS_TEMPLATES
    )

    add_train(
        volume_template.format(
            words=words
        ),
        [
            tool_call(
                "set_volume",
                level=n,
            )
        ],
        category="asr_numeric",
    )

    add_train(
        brightness_template.format(
            words=words
        ),
        [
            tool_call(
                "set_brightness",
                level=n,
            )
        ],
        category="asr_numeric",
    )


# ============================================================
# MULTI-COMMAND EXAMPLES
# ============================================================

MULTI_EXAMPLES = [
    (
        "Set volume to 30 and brightness to 70",
        [
            tool_call("set_volume", level=30),
            tool_call("set_brightness", level=70),
        ],
    ),

    (
        "Brightness 80 and volume 20",
        [
            tool_call("set_brightness", level=80),
            tool_call("set_volume", level=20),
        ],
    ),

    (
        "Pause the music and set volume to 15",
        [
            tool_call("pause_media"),
            tool_call("set_volume", level=15),
        ],
    ),

    (
        "Set volume to 40 then resume playback",
        [
            tool_call("set_volume", level=40),
            tool_call("play_media"),
        ],
    ),

    (
        "Skip this song and set volume to 60",
        [
            tool_call("skip_media"),
            tool_call("set_volume", level=60),
        ],
    ),

    (
        "Open Spotify and set volume to 35",
        [
            tool_call("start_app", app="spotify"),
            tool_call("set_volume", level=35),
        ],
    ),

    (
        "Launch Chrome and set brightness to 70",
        [
            tool_call("start_app", app="chrome"),
            tool_call("set_brightness", level=70),
        ],
    ),

    (
        "Open VS Code and brightness 40",
        [
            tool_call("start_app", app="vscode"),
            tool_call("set_brightness", level=40),
        ],
    ),

    (
        "Start Notion and set volume to 20",
        [
            tool_call("start_app", app="notion"),
            tool_call("set_volume", level=20),
        ],
    ),

    (
        "Pause what's playing and open Google Drive",
        [
            tool_call("pause_media"),
            tool_call("open_website", site="google_drive"),
        ],
    ),

    (
        "Open GitHub and set brightness to 65",
        [
            tool_call("open_website", site="github"),
            tool_call("set_brightness", level=65),
        ],
    ),

    (
        "Take me to YouTube and set volume to 25",
        [
            tool_call("open_website", site="youtube"),
            tool_call("set_volume", level=25),
        ],
    ),

    (
        "Open Google Docs and mute",
        [
            tool_call("open_website", site="google_docs"),
            tool_call("set_volume", level=0),
        ],
    ),

    (
        "Skip the song and open VS Code",
        [
            tool_call("skip_media"),
            tool_call("start_app", app="vscode"),
        ],
    ),

    (
        "Start Spotify then resume playback",
        [
            tool_call("start_app", app="spotify"),
            tool_call("play_media"),
        ],
    ),

    (
        "Pause playback and open File Explorer",
        [
            tool_call("pause_media"),
            tool_call("start_app", app="file_explorer"),
        ],
    ),

    (
        "Brightness 90 volume 50 and open GitHub",
        [
            tool_call("set_brightness", level=90),
            tool_call("set_volume", level=50),
            tool_call("open_website", site="github"),
        ],
    ),

    (
        "Volume 10 brightness 80 then open YouTube",
        [
            tool_call("set_volume", level=10),
            tool_call("set_brightness", level=80),
            tool_call("open_website", site="youtube"),
        ],
    ),

    (
        "Open Chrome and then set the volume to 45",
        [
            tool_call("start_app", app="chrome"),
            tool_call("set_volume", level=45),
        ],
    ),

    (
        "Open Spotify then skip the current song",
        [
            tool_call("start_app", app="spotify"),
            tool_call("skip_media"),
        ],
    ),

    (
        "Open settings and set brightness to 55",
        [
            tool_call("start_app", app="settings"),
            tool_call("set_brightness", level=55),
        ],
    ),
]


for user, calls in MULTI_EXAMPLES:

    add_train(
        user,
        calls,
        category="multi",
    )


# ============================================================
# GENERATED MULTI-COMMAND NUMERIC DATA
# ============================================================

for _ in range(300):

    volume = random.randint(0, 100)
    brightness = random.randint(0, 100)

    variants = [
        (
            f"volume {volume} and brightness {brightness}",
            [
                tool_call(
                    "set_volume",
                    level=volume,
                ),
                tool_call(
                    "set_brightness",
                    level=brightness,
                ),
            ],
        ),

        (
            f"set brightness to {brightness} then volume to {volume}",
            [
                tool_call(
                    "set_brightness",
                    level=brightness,
                ),
                tool_call(
                    "set_volume",
                    level=volume,
                ),
            ],
        ),

        (
            f"put audio at {volume} and the display at {brightness}",
            [
                tool_call(
                    "set_volume",
                    level=volume,
                ),
                tool_call(
                    "set_brightness",
                    level=brightness,
                ),
            ],
        ),

        (
            f"screen {brightness} sound {volume}",
            [
                tool_call(
                    "set_brightness",
                    level=brightness,
                ),
                tool_call(
                    "set_volume",
                    level=volume,
                ),
            ],
        ),
    ]

    user, calls = random.choice(
        variants
    )

    add_train(
        user,
        calls,
        category="multi_generated",
    )


# ============================================================
# APP + VALUE GENERATED DATA
# ============================================================

for _ in range(100):

    app = random.choice(APPS)
    level = random.randint(0, 100)

    add_train(
        f"start {app.replace('_', ' ')} and set volume to {level}",
        [
            tool_call(
                "start_app",
                app=app,
            ),
            tool_call(
                "set_volume",
                level=level,
            ),
        ],
        category="multi_generated",
    )


# ============================================================
# WEBSITE + VALUE GENERATED DATA
# ============================================================

for _ in range(100):

    site = random.choice(SITES)
    level = random.randint(0, 100)

    spoken_site = site.replace(
        "_",
        " ",
    )

    add_train(
        f"open {spoken_site} and set brightness to {level}",
        [
            tool_call(
                "open_website",
                site=site,
            ),
            tool_call(
                "set_brightness",
                level=level,
            ),
        ],
        category="multi_generated",
    )


# ============================================================
# HELD-OUT EVALUATION SET
#
# These phrases should NOT be copied into training data.
# They intentionally use different wording.
# ============================================================

HELD_OUT = [
    (
        "Fire up Google's browser",
        [tool_call("start_app", app="chrome")],
        "app",
    ),

    (
        "Get the code editor on my screen",
        [tool_call("start_app", app="vscode")],
        "app",
    ),

    (
        "Give me a cmd window",
        [tool_call("start_app", app="command_prompt")],
        "app",
    ),

    (
        "Let me browse my local files",
        [tool_call("start_app", app="file_explorer")],
        "app",
    ),

    (
        "Bring the Windows configuration screen up",
        [tool_call("start_app", app="settings")],
        "app",
    ),

    (
        "Put Chat GPT on screen",
        [tool_call("start_app", app="chatgpt")],
        "app",
    ),

    (
        "Fire up my music app Spotify",
        [tool_call("start_app", app="spotify")],
        "app",
    ),

    (
        "Bring my Notion workspace up",
        [tool_call("start_app", app="notion")],
        "app",
    ),

    (
        "Speakers at thirty seven percent",
        [tool_call("set_volume", level=37)],
        "volume",
    ),

    (
        "Audio should sit at 82 percent",
        [tool_call("set_volume", level=82)],
        "volume",
    ),

    (
        "Make my sound level 13",
        [tool_call("set_volume", level=13)],
        "volume",
    ),

    (
        "I want the speakers at sixty four",
        [tool_call("set_volume", level=64)],
        "volume",
    ),

    (
        "Display at thirty seven percent",
        [tool_call("set_brightness", level=37)],
        "brightness",
    ),

    (
        "The screen should sit at 82 percent brightness",
        [tool_call("set_brightness", level=82)],
        "brightness",
    ),

    (
        "Make the panel brightness 13",
        [tool_call("set_brightness", level=13)],
        "brightness",
    ),

    (
        "Put the display level at sixty four",
        [tool_call("set_brightness", level=64)],
        "brightness",
    ),

    (
        "Hold whatever I'm listening to",
        [tool_call("pause_media")],
        "media",
    ),

    (
        "Carry on with the music",
        [tool_call("play_media")],
        "media",
    ),

    (
        "I'm over this track",
        [tool_call("skip_media")],
        "media",
    ),

    (
        "Stop this where it is for now",
        [tool_call("pause_media")],
        "media",
    ),

    (
        "Keep the current thing playing",
        [tool_call("play_media")],
        "media",
    ),

    (
        "Move past the current audio",
        [tool_call("skip_media")],
        "media",
    ),

    (
        "Go to the code hosting site GitHub",
        [tool_call("open_website", site="github")],
        "website",
    ),

    (
        "Bring up Google's document editor",
        [tool_call("open_website", site="google_docs")],
        "website",
    ),

    (
        "Show me my files on Drive in the browser",
        [tool_call("open_website", site="google_drive")],
        "website",
    ),

    (
        "Load the YouTube webpage",
        [tool_call("open_website", site="youtube")],
        "website",
    ),

    (
        "Don't open the GitHub site, I need the editor",
        [tool_call("start_app", app="vscode")],
        "hard",
    ),

    (
        "Don't launch the editor, take me to GitHub",
        [tool_call("open_website", site="github")],
        "hard",
    ),

    (
        "Don't move to another song, just hold this one",
        [tool_call("pause_media")],
        "hard",
    ),

    (
        "Don't pause this one, move to another track",
        [tool_call("skip_media")],
        "hard",
    ),

    (
        "Leave the screen alone and set sound to 43",
        [tool_call("set_volume", level=43)],
        "hard",
    ),

    (
        "Leave audio alone and make brightness 43",
        [tool_call("set_brightness", level=43)],
        "hard",
    ),

    (
        "yo uh can you get chrome up",
        [tool_call("start_app", app="chrome")],
        "asr",
    ),

    (
        "okay um audio at forty seven",
        [tool_call("set_volume", level=47)],
        "asr",
    ),

    (
        "yeah put screen brightness at sixty three",
        [tool_call("set_brightness", level=63)],
        "asr",
    ),

    (
        "uh go ahead and move to the next song",
        [tool_call("skip_media")],
        "asr",
    ),

    (
        "hey yeah pause that for a sec",
        [tool_call("pause_media")],
        "asr",
    ),

    (
        "okay keep playing it",
        [tool_call("play_media")],
        "asr",
    ),

    (
        "sound twenty two display seventy one",
        [
            tool_call("set_volume", level=22),
            tool_call("set_brightness", level=71),
        ],
        "multi",
    ),

    (
        "hold the music and bring my files up",
        [
            tool_call("pause_media"),
            tool_call("start_app", app="file_explorer"),
        ],
        "multi",
    ),

    (
        "next track then take me to GitHub",
        [
            tool_call("skip_media"),
            tool_call("open_website", site="github"),
        ],
        "multi",
    ),

    (
        "open Spotify set audio to 34 then resume",
        [
            tool_call("start_app", app="spotify"),
            tool_call("set_volume", level=34),
            tool_call("play_media"),
        ],
        "multi",
    ),

    (
        "open vscode then put the screen at 58",
        [
            tool_call("start_app", app="vscode"),
            tool_call("set_brightness", level=58),
        ],
        "multi",
    ),

    (
        "go to youtube and make the speakers 29",
        [
            tool_call("open_website", site="youtube"),
            tool_call("set_volume", level=29),
        ],
        "multi",
    ),
]


for user, calls, category in HELD_OUT:

    add_eval(
        user,
        calls,
        category,
    )


# ============================================================
# OPTIONAL REAL FAILURE CASES
# ============================================================

def convert_simple_call(raw_call):

    if "name" not in raw_call:
        raise ValueError(
            "Real failure tool call missing 'name'"
        )

    return tool_call(
        raw_call["name"],
        **raw_call.get(
            "arguments",
            {},
        ),
    )


if Path(REAL_FAILURES_FILE).exists():

    print(
        f"Loading real-world failure cases from "
        f"{REAL_FAILURES_FILE}"
    )

    with open(
        REAL_FAILURES_FILE,
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
                raw = json.loads(line)

            except json.JSONDecodeError as e:

                raise ValueError(
                    f"{REAL_FAILURES_FILE}:"
                    f"{line_number} contains invalid JSON"
                ) from e

            if "user" not in raw:

                raise ValueError(
                    f"{REAL_FAILURES_FILE}:"
                    f"{line_number} missing 'user'"
                )

            if "calls" not in raw:

                raise ValueError(
                    f"{REAL_FAILURES_FILE}:"
                    f"{line_number} missing 'calls'"
                )

            calls = [
                convert_simple_call(c)
                for c in raw["calls"]
            ]

            add_train(
                raw["user"],
                calls,
                category="real_failure",
                source="real_failure",
            )


# ============================================================
# DATA VALIDATION
# ============================================================

ALLOWED_TOOLS = {
    "start_app",
    "set_volume",
    "set_brightness",
    "pause_media",
    "play_media",
    "skip_media",
    "open_website",
}


def validate_call(call_data):

    if not isinstance(
        call_data,
        dict,
    ):
        raise ValueError(
            "Tool call must be a dictionary"
        )

    if "function" not in call_data:
        raise ValueError(
            f"Tool call missing function: {call_data}"
        )

    function = call_data["function"]

    name = function.get("name")

    arguments = function.get(
        "arguments",
        {},
    )

    if name not in ALLOWED_TOOLS:

        raise ValueError(
            f"Unknown tool: {name}"
        )

    if not isinstance(
        arguments,
        dict,
    ):

        raise ValueError(
            f"{name} arguments must be a dictionary"
        )

    if name == "start_app":

        if set(arguments.keys()) != {"app"}:

            raise ValueError(
                f"Invalid start_app arguments: "
                f"{arguments}"
            )

        if arguments["app"] not in APPS:

            raise ValueError(
                f"Unsupported application: "
                f"{arguments['app']}"
            )

    elif name in {
        "set_volume",
        "set_brightness",
    }:

        if set(arguments.keys()) != {"level"}:

            raise ValueError(
                f"Invalid {name} arguments: "
                f"{arguments}"
            )

        level = arguments["level"]

        # bool is technically a subclass of int,
        # so explicitly reject it.
        if type(level) is not int:

            raise ValueError(
                f"{name} level must be an integer. "
                f"Got: {level!r}"
            )

        if not 0 <= level <= 100:

            raise ValueError(
                f"{name} level out of range: "
                f"{level}"
            )

    elif name == "open_website":

        if set(arguments.keys()) != {"site"}:

            raise ValueError(
                f"Invalid open_website arguments: "
                f"{arguments}"
            )

        if arguments["site"] not in SITES:

            raise ValueError(
                f"Unsupported website: "
                f"{arguments['site']}"
            )

    elif name in {
        "pause_media",
        "play_media",
        "skip_media",
    }:

        if arguments != {}:

            raise ValueError(
                f"{name} must have no arguments. "
                f"Got: {arguments}"
            )


def validate_examples(
    examples,
    dataset_name,
):

    for index, example in enumerate(
        examples
    ):

        if not example["user"]:

            raise ValueError(
                f"{dataset_name}[{index}] "
                f"has empty user text"
            )

        if not example["calls"]:

            raise ValueError(
                f"{dataset_name}[{index}] "
                f"has no tool calls"
            )

        for call_data in example["calls"]:

            validate_call(
                call_data
            )


validate_examples(
    train_examples,
    "train",
)

validate_examples(
    eval_examples,
    "eval",
)


# ============================================================
# DEDUPLICATE
#
# If the same phrase appears twice with the same output,
# keep one.
#
# If it appears twice with DIFFERENT outputs, error out.
# ============================================================

def deduplicate(
    examples,
    dataset_name,
):

    output = []

    seen = {}

    for example in examples:

        text_key = normalize_text(
            example["user"]
        )

        call_key = canonical_json(
            example["calls"]
        )

        if text_key in seen:

            previous = seen[text_key]

            if previous != call_key:

                raise ValueError(
                    "\nConflicting labels detected.\n"
                    f"Dataset: {dataset_name}\n"
                    f"Prompt: {example['user']}\n"
                    f"Existing calls: {previous}\n"
                    f"New calls: {call_key}\n"
                )

            # Same phrase + same label:
            # just ignore duplicate.
            continue

        seen[text_key] = call_key

        output.append(
            example
        )

    return output


train_examples = deduplicate(
    train_examples,
    "train",
)

eval_examples = deduplicate(
    eval_examples,
    "eval",
)


# ============================================================
# PREVENT EXACT TRAIN / EVAL LEAKAGE
# ============================================================

train_prompts = {
    normalize_text(
        example["user"]
    )
    for example in train_examples
}

eval_prompts = {
    normalize_text(
        example["user"]
    )
    for example in eval_examples
}


overlap = (
    train_prompts
    & eval_prompts
)


if overlap:

    raise ValueError(
        "\nExact train/eval prompt leakage detected:\n"
        + "\n".join(
            sorted(overlap)
        )
    )


# ============================================================
# FUNCTIONGEMMA FORMAT
# ============================================================

def to_functiongemma(
    example
):

    return {
        "messages": [
            {
                "role": "developer",
                "content": DEVELOPER_MESSAGE,
            },

            {
                "role": "user",
                "content": example["user"],
            },

            {
                "role": "assistant",
                "content": None,
                "tool_calls": example["calls"],
            },
        ],

        "tools": TOOLS,

        "metadata": {
            "category": example["category"],
            "source": example["source"],
        },
    }


train_rows = [
    to_functiongemma(example)
    for example in train_examples
]

eval_rows = [
    to_functiongemma(example)
    for example in eval_examples
]


# ============================================================
# SHUFFLE TRAINING DATA
#
# Evaluation remains deterministic / ordered.
# ============================================================

random.shuffle(
    train_rows
)


# ============================================================
# WRITE JSONL
# ============================================================

def write_jsonl(
    path,
    rows,
):

    with open(
        path,
        "w",
        encoding="utf-8",
    ) as f:

        for row in rows:

            f.write(
                json.dumps(
                    row,
                    ensure_ascii=False,
                )
                + "\n"
            )


write_jsonl(
    TRAIN_FILE,
    train_rows,
)

write_jsonl(
    EVAL_FILE,
    eval_rows,
)


# ============================================================
# STATISTICS
# ============================================================

train_categories = Counter(
    row["metadata"]["category"]
    for row in train_rows
)

eval_categories = Counter(
    row["metadata"]["category"]
    for row in eval_rows
)


stats = {
    "seed": SEED,

    "train_examples": len(
        train_rows
    ),

    "eval_examples": len(
        eval_rows
    ),

    "train_categories": dict(
        sorted(
            train_categories.items()
        )
    ),

    "eval_categories": dict(
        sorted(
            eval_categories.items()
        )
    ),

    "supported_apps": APPS,

    "supported_sites": SITES,

    "supported_tools": sorted(
        ALLOWED_TOOLS
    ),
}


with open(
    STATS_FILE,
    "w",
    encoding="utf-8",
) as f:

    json.dump(
        stats,
        f,
        indent=2,
    )


# ============================================================
# FINAL SANITY CHECK
#
# Re-read files after writing so a path/empty-file problem
# is caught immediately rather than in train.py.
# ============================================================

train_path = Path(
    TRAIN_FILE
)

eval_path = Path(
    EVAL_FILE
)


if not train_path.exists():
    raise RuntimeError(
        f"{TRAIN_FILE} was not created"
    )


if train_path.stat().st_size == 0:
    raise RuntimeError(
        f"{TRAIN_FILE} is EMPTY"
    )


if not eval_path.exists():
    raise RuntimeError(
        f"{EVAL_FILE} was not created"
    )


if eval_path.stat().st_size == 0:
    raise RuntimeError(
        f"{EVAL_FILE} is EMPTY"
    )


# Count actual lines on disk.
with open(
    TRAIN_FILE,
    "r",
    encoding="utf-8",
) as f:

    disk_train_count = sum(
        1
        for line in f
        if line.strip()
    )


with open(
    EVAL_FILE,
    "r",
    encoding="utf-8",
) as f:

    disk_eval_count = sum(
        1
        for line in f
        if line.strip()
    )


if disk_train_count != len(
    train_rows
):

    raise RuntimeError(
        "Training file line count mismatch"
    )


if disk_eval_count != len(
    eval_rows
):

    raise RuntimeError(
        "Evaluation file line count mismatch"
    )


# ============================================================
# FINISHED
# ============================================================

print()
print("=" * 72)
print("FUNCTIONGEMMA DATASET COMPLETE")
print("=" * 72)

print(
    f"\nTraining examples: "
    f"{len(train_rows)}"
)

print(
    f"Evaluation examples: "
    f"{len(eval_rows)}"
)

print(
    f"\nTraining file:"
    f"\n  {train_path.resolve()}"
)

print(
    f"\nEvaluation file:"
    f"\n  {eval_path.resolve()}"
)

print(
    f"\nStatistics file:"
    f"\n  {Path(STATS_FILE).resolve()}"
)

print(
    f"\nTraining file size: "
    f"{train_path.stat().st_size / 1024 / 1024:.2f} MB"
)

print(
    f"Evaluation file size: "
    f"{eval_path.stat().st_size / 1024:.2f} KB"
)


print("\nTraining categories:")

for category, count in sorted(
    train_categories.items()
):

    print(
        f"  {category:<25} "
        f"{count:>5}"
    )


print("\nEvaluation categories:")

for category, count in sorted(
    eval_categories.items()
):

    print(
        f"  {category:<25} "
        f"{count:>5}"
    )


print()
print(
    "Dataset validation: PASSED"
)

print(
    "Train/eval exact leakage: NONE"
)

print(
    "Unsupported/clarify tools: NONE"
)

print()
print(
    "Next step:"
)

print(
    "  python train.py"
)