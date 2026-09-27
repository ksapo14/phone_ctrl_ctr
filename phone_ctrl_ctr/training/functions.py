"""Shared schemas and a strict, non-executing adapter to the companion protocol."""
import re

SYSTEM = (
    "You are a model that can do function calling with the following functions. "
    "Route one transcribed Windows remote command to exactly one function. "
    "Use no_action for ambiguous, unsupported, negated or multiple commands. "
    "Never invent a window ID, application, percentage or current playback state. "
    "Only explicit absolute percentages can change volume or brightness."
)


def enum(*values):
    return {"type": "string", "enum": list(values)}


def tool(name, description, **properties):
    return {"type": "function", "function": {"name": name, "description": description,
        "parameters": {"type": "object", "properties": properties,
                       "required": list(properties), "additionalProperties": False}}}


PERCENT = {"type": "integer", "minimum": 0, "maximum": 100}
TOOLS = [
    tool("launch_app", "Open an installed supported application. Does not focus an existing named window.",
         app=enum("chrome", "vscode", "chatgpt", "spotify", "explorer", "cmd")),
    tool("set_volume", "Set speaker volume to an explicit absolute percentage. Silence means zero. Relative requests need clarification.", percent=PERCENT),
    tool("set_brightness", "Set display brightness to an explicit absolute percentage. Relative requests need clarification.", percent=PERCENT),
    tool("desktop_action", "Cycle windows or virtual desktops, show Task View, toggle desktop, open Windows Search or notifications.",
         action=enum("nextWindow", "previousWindow", "nextDesktop", "previousDesktop", "taskView", "desktop", "search", "notifications")),
    tool("media_control", "Send a media key: toggle playback, skip next/previous track, or stop. Play/pause toggle has no knowledge of current playback. Explicit play-only or pause-only needs clarification.",
         action=enum("playPause", "next", "previous", "stop")),
    tool("click_mouse", "Click the current pointer position once with the specified mouse button.", button=enum("left", "right")),
    tool("scroll_mouse", "Scroll at the current pointer position. One step is one Windows wheel notch.",
         direction=enum("up", "down", "left", "right"), steps={"type": "integer", "minimum": 1, "maximum": 10}),
    tool("zoom_view", "Zoom in or out by one Ctrl+wheel notch in the focused application.", direction=enum("in", "out")),
    tool("list_windows", "List currently open windows without switching to one."),
    tool("get_state", "Read current speaker volume, brightness, available apps and open windows."),
    tool("toggle_dictation", "Double-click mouse button 4 to toggle Wispr hands-free dictation. Does not know if dictation is currently on."),
    tool("no_action", "Do not execute an action. Request clarification, explain unsupported operations, or acknowledge cancellation.",
         reason=enum("ambiguous", "unsupported", "cancelled", "multiple_commands")),
]
SCHEMAS = {t["function"]["name"]: t["function"]["parameters"] for t in TOOLS}


def validate_call(name, arguments):
    if name not in SCHEMAS or not isinstance(arguments, dict):
        raise ValueError("Unknown function or invalid arguments")
    schema = SCHEMAS[name]
    if set(arguments) != set(schema["required"]):
        raise ValueError("Missing or unexpected arguments")
    for key, value in arguments.items():
        spec = schema["properties"][key]
        if spec["type"] == "integer":
            if type(value) is not int or not spec["minimum"] <= value <= spec["maximum"]:
                raise ValueError("Integer out of range")
        elif not isinstance(value, str) or value not in spec["enum"]:
            raise ValueError("Invalid enum value")
    return {"name": name, "arguments": arguments}


def to_command(name, arguments):
    """Returns a packet for a future authenticated dispatcher; never sends it."""
    validate_call(name, arguments)
    a = arguments
    if name == "no_action": return None
    if name == "launch_app": return {"type": "launch", "app": a["app"]}
    if name in ("set_volume", "set_brightness"):
        return {"type": name.removeprefix("set_"), "value": a["percent"]}
    if name == "desktop_action": return {"type": "gesture", "name": a["action"]}
    if name == "media_control": return {"type": "media", "action": a["action"]}
    if name == "click_mouse": return {"type": "click", "button": a["button"]}
    if name == "scroll_mouse":
        amount = a["steps"] * 120
        dx, dy = {"up": (0, amount), "down": (0, -amount), "left": (-amount, 0), "right": (amount, 0)}[a["direction"]]
        return {"type": "scroll", "dx": dx, "dy": dy}
    if name == "zoom_view": return {"type": "zoom", "delta": 120 if a["direction"] == "in" else -120}
    if name == "toggle_dictation": return {"type": "doubleClick", "button": "x1"}
    return {"type": "windows" if name == "list_windows" else "state"}


def parse_output(text):
    """Parse only our single-call scalar grammar. No eval, execution, or repair."""
    text = text.strip()
    text = re.sub(r"(?:<pad>|<eos>|<end_of_turn>|<start_function_response>)+$", "", text)
    match = re.fullmatch(r"<start_function_call>call:(\w+)\{(.*?)\}<end_function_call>", text.strip(), re.S)
    if not match: raise ValueError("Expected exactly one function call")
    name, body = match.groups()
    arguments = {}
    while body.strip():
        item = re.match(r"\s*(\w+)\s*:\s*(?:<escape>([^<>]*)<escape>|(-?\d+))\s*(,|$)", body)
        if not item: raise ValueError("Invalid argument syntax")
        key, string, number, comma = item.groups()
        if key in arguments: raise ValueError("Duplicate argument")
        arguments[key] = string if string is not None else int(number)
        body = body[item.end():]
        if comma and not body.strip(): raise ValueError("Trailing comma")
    return validate_call(name, arguments)
