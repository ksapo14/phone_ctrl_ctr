"""Generate a reproducible synthetic starter corpus, split by phrasing family."""
import argparse
import hashlib
import json
import random
from collections import Counter
from pathlib import Path
from functions import SYSTEM, TOOLS, to_command

ROOT = Path(__file__).resolve().parent


def build():
    rows = {split: [] for split in ("train", "validation", "test")}
    seen = set()

    def add(group, phrases, name, args):
        # Last two phrasing families are never trained on. Argument values may recur.
        assert len(phrases) >= 5
        for i, phrase in enumerate(phrases):
            split = "test" if i == len(phrases)-1 else "validation" if i == len(phrases)-2 else "train"
            key = phrase.casefold().strip()
            if key in seen: raise ValueError(f"Duplicate utterance: {phrase}")
            seen.add(key)
            rows[split].append({"id": hashlib.sha256(key.encode()).hexdigest()[:16],
                "group": f"{group}/phrasing-{i}", "utterance": phrase,
                "messages": [{"role": "developer", "content": SYSTEM}, {"role": "user", "content": phrase},
                    {"role": "assistant", "tool_calls": [{"type": "function", "function": {"name": name, "arguments": args}}]}],
                "expected_command": to_command(name, args)})

    for app, aliases in {"chrome": ["Chrome", "Google Chrome", "the browser"],
            "vscode": ["VS Code", "Visual Studio Code", "the code editor"],
            "chatgpt": ["ChatGPT", "Chat GPT"], "spotify": ["Spotify", "the Spotify app"],
            "explorer": ["File Explorer", "Windows Explorer", "the file manager"],
            "cmd": ["Command Prompt", "cmd", "the command prompt app"]}.items():
        for alias in aliases:
            add("launch", [f"Open {alias}", f"Launch {alias} please", f"Can you start {alias}?",
                f"I want to open {alias}", f"Bring up {alias}", f"Could you launch {alias} for me?",
                f"Get {alias} running"], "launch_app", {"app": app})

    words = {0: "zero", 10: "ten", 20: "twenty", 25: "twenty five", 30: "thirty", 40: "forty",
             50: "fifty", 60: "sixty", 70: "seventy", 75: "seventy five", 80: "eighty", 90: "ninety", 100: "one hundred"}
    for name, label in [("set_volume", "volume"), ("set_brightness", "brightness")]:
        for value in range(101):
            add(label, [f"Set {label} to {value} percent", f"{label.capitalize()} {value}%",
                f"Make the {label} {value} percent", f"Please set my {label} at {value}%",
                f"I want {value} percent {label}", f"Could you put {label} at {value} percent?",
                f"Change the {label} level to {value}%"], name, {"percent": value})
        for value, word in words.items():
            add(label+"-spoken", [f"Set {label} to {word} percent", f"{label.capitalize()} at {word} percent please",
                f"Make my {label} {word} percent", f"I'd like {word} percent {label}",
                f"Adjust the {label} level to {word} percent"], name, {"percent": value})

    families = [
        ("desktop_action", {"action": "nextWindow"}, ["Next window", "Switch to the next window", "Cycle forward one window", "Go to the following window", "Move ahead to another window"]),
        ("desktop_action", {"action": "previousWindow"}, ["Previous window", "Switch to the previous window", "Cycle backward one window", "Go back one window", "Return to the preceding window"]),
        ("desktop_action", {"action": "nextDesktop"}, ["Next desktop", "Switch to the desktop on the right", "Move to the next virtual desktop", "Go forward one virtual desktop", "Take me to the following desktop"]),
        ("desktop_action", {"action": "previousDesktop"}, ["Previous desktop", "Switch to the desktop on the left", "Move to the previous virtual desktop", "Go back one virtual desktop", "Take me to the preceding desktop"]),
        ("desktop_action", {"action": "taskView"}, ["Show Task View", "Open the task view", "Show the Windows task switcher", "Bring up Task View", "Display the overview of my windows"]),
        ("desktop_action", {"action": "desktop"}, ["Show desktop", "Toggle the desktop", "Show my desktop", "Let me see my desktop", "Reveal the Windows desktop"]),
        ("desktop_action", {"action": "search"}, ["Open Windows Search", "Show Windows search", "Bring up the Windows search box", "Let me search Windows", "Activate the Windows search panel"]),
        ("desktop_action", {"action": "notifications"}, ["Show notifications", "Open notification center", "Show my notifications panel", "Bring up Windows notifications", "Display the notification center"]),
        ("media_control", {"action": "playPause"}, ["Toggle playback", "Press play pause", "Toggle my music", "Hit the media play pause button", "Switch the current media between playing and paused"]),
        ("media_control", {"action": "next"}, ["Next song", "Skip this track", "Play the next track", "Skip ahead to the next song", "Move on to the following track"]),
        ("media_control", {"action": "previous"}, ["Previous song", "Go to the previous track", "Press previous track", "Go back a song", "Return to the preceding media track"]),
        ("media_control", {"action": "stop"}, ["Stop media playback", "Stop the music", "Press media stop", "Stop the current media", "Send the stop playback command"]),
        ("click_mouse", {"button": "left"}, ["Left click", "Click the mouse", "Click here", "Press the left mouse button once", "Single click at the pointer"]),
        ("click_mouse", {"button": "right"}, ["Right click", "Open the context menu here", "Click the right mouse button", "Show the menu at the cursor", "Single right click at the pointer"]),
        ("zoom_view", {"direction": "in"}, ["Zoom in", "Make the page bigger", "Increase zoom one step", "Enlarge this view", "Move the zoom in one notch"]),
        ("zoom_view", {"direction": "out"}, ["Zoom out", "Make the page smaller", "Decrease zoom one step", "Shrink this view", "Move the zoom out one notch"]),
        ("list_windows", {}, ["List my open windows", "Which windows are open?", "Get the window list", "Tell me the open window titles", "Enumerate the windows I have open"]),
        ("get_state", {}, ["What is the computer status?", "Check the current volume", "Read the display brightness", "Show the available apps and settings", "Report the current PC controls state"]),
        ("toggle_dictation", {}, ["Toggle hands free dictation", "Double click mouse button four", "Toggle Wispr hands free", "Press the Wispr toggle shortcut", "Switch hands free dictation mode"]),
        ("set_volume", {"percent": 0}, ["Silence the speakers", "Set speaker volume to zero", "Turn speaker volume all the way down", "Make the speakers silent", "Reduce output volume to zero"]),
        ("set_volume", {"percent": 50}, ["Set volume halfway", "Put the sound at half volume", "Half volume please", "Adjust speakers to fifty percent", "Set the speaker level to one half"]),
        ("set_brightness", {"percent": 50}, ["Set brightness halfway", "Put the screen at half brightness", "Half brightness please", "Adjust display to fifty percent", "Set the screen level to one half"]),
    ]
    for index, (name, args, phrases) in enumerate(families):
        add(f"intent-{index}", phrases, name, args)
    for direction in ["up", "down", "left", "right"]:
        for steps in range(1, 11):
            add("scroll", [f"Scroll {direction} {steps} steps", f"Move the page {direction} by {steps} notches",
                f"Scroll {steps} notches {direction}", f"Send {steps} wheel steps {direction}",
                f"Please scroll {direction}, {steps} wheel notches"], "scroll_mouse", {"direction": direction, "steps": steps})
        add("scroll-default", [f"Scroll {direction}", f"Scroll a little {direction}", f"One notch {direction}",
            f"Move the page one step {direction}", f"Give me a single scroll {direction}"], "scroll_mouse", {"direction": direction, "steps": 1})

    negatives = {
        "ambiguous": [
            ["Make it louder", "Turn it down", "Set the brightness", "Open it", "Switch to that one"],
            ["Play music", "Pause the song", "Start recording", "Stop dictation", "Unmute the computer"],
            ["Increase brightness by ten", "Lower volume a little", "Turn brightness up", "Raise the volume", "Make it dimmer"],
        ],
        "unsupported": [
            ["Delete all my files", "Run a shell command", "Install an app", "Shut down the PC", "Send an email"],
            ["Open Firefox", "Launch Photoshop", "Open Calculator", "Start Notepad", "Launch Edge"],
            ["Set volume to 110 percent", "Set brightness to -5 percent", "Volume 150 percent", "Brightness 200 percent", "Set volume to -1 percent"],
            ["What is the weather?", "Tell me a joke", "Buy some headphones", "Summarize my email", "Search the web for restaurants"],
            ["Focus the Spotify window", "Type hello into this document", "Close my browser", "Move the pointer to the red icon", "Set microphone gain to fifty percent"],
        ],
        "cancelled": [
            ["Never mind", "Cancel that", "Don't do anything", "Forget my request", "No action please"],
            ["Don't open Chrome", "Do not change the brightness", "Don't skip the song", "Don't launch Spotify", "Do not turn the volume down"],
        ],
        "multiple_commands": [
            ["Open Chrome and Spotify", "Set volume to 50 and brightness to 20", "Next song and next window", "Open VS Code then click", "Launch ChatGPT and show desktop"],
            ["Scroll down then right click", "Show Task View and notifications", "Open cmd and File Explorer", "Zoom out and switch desktops", "Stop music and list windows"],
        ],
    }
    for reason, groups in negatives.items():
        for index, phrases in enumerate(groups): add(f"{reason}-{index}", phrases, "no_action", {"reason": reason})
    for split in rows: random.Random(42).shuffle(rows[split])
    return rows


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=ROOT / "data")
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    rows = build()
    manifest = {"seed": 42, "kind": "synthetic starter data", "split": "held-out phrasing families", "splits": {}}
    (args.output / "tools.json").write_text(json.dumps(TOOLS, indent=2) + "\n", encoding="utf-8")
    for split, records in rows.items():
        content = "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in records)
        (args.output / f"{split}.jsonl").write_text(content, encoding="utf-8", newline="\n")
        manifest["splits"][split] = {"count": len(records), "sha256": hashlib.sha256(content.encode()).hexdigest(),
            "functions": dict(Counter(row["messages"][-1]["tool_calls"][0]["function"]["name"] for row in records))}
    (args.output / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(manifest, indent=2))


if __name__ == "__main__": main()
