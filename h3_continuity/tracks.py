"""Pure typed track placement and validation. No torch or timeline import."""
import copy

FEATURE = "timeline-tracks-1"
TYPES = ("video", "audio", "text")


def _error(message):
    raise ValueError(f"H3 Timeline tracks: {message}")


def placements(data, duration=None):
    duration = duration or (lambda box, index: box["frames"])
    cursor, result = 0, []
    for index, box in enumerate(data["boxes"]):
        start = box.get("start") if "tracks" in data else cursor
        cursor = start + duration(box, index)
        result.append(dict(id=box["id"], track=box.get("track", "legacy"), start=start, end=cursor))
    return result


def duration_frames(data, duration=None):
    return max((p["end"] for p in placements(data, duration)), default=0)


def predecessor(data, box_id, duration=None):
    spans = placements(data, duration)
    at = next((p for p in spans if p["id"] == box_id), None)
    return next((p["id"] for p in spans if at and p["id"] != box_id and p["track"] == at["track"]
                 and p["end"] == at["start"]), None)


def validate_data(data, duration=None):
    if "tracks" not in data:
        if any("track" in b or "start" in b for b in data.get("boxes", []) or []) or "text_lanes" in data or "overlap_switches" in data:
            _error("placement needs tracks")
        return
    if FEATURE not in data.get("requires", []):
        _error(f"tracks require {FEATURE}")
    if not isinstance(data["tracks"], list):
        _error("tracks must be a list")
    ids, kinds = set(), {}

    def identity(value):
        if not isinstance(value, str) or not value or value in ids:
            _error("IDs must be nonempty and unique")
        ids.add(value)

    def kind(value, expected):
        if kinds.get(value) != expected:
            _error(f"unknown or wrong-type {expected} track {value}")

    for track in data["tracks"]:
        if not isinstance(track, dict) or track.get("type") not in TYPES or not isinstance(track.get("name"), str):
            _error("invalid track")
        identity(track.get("id")); kinds[track["id"]] = track["type"]
    for box in data["boxes"]:
        identity(box.get("id")); kind(box.get("track"), "video")
        if type(box.get("start")) is not int or not 0 <= box["start"] <= 9007199254740991:
            _error(f"clip {box['id']} start must be a nonnegative integer")
        for layer in box.get("layers", []):
            identity(layer.get("id"))
    spans = placements(data, duration)
    for track in data["tracks"]:
        rows = sorted((p for p in spans if p["track"] == track["id"]), key=lambda p: p["start"])
        for left, right in zip(rows, rows[1:]):
            if right["start"] < left["end"]:
                _error(f"clips overlap on {track['name']}")
    occupied = set()
    for field, expected in (("audio_clips", "audio"), ("text_lanes", "text")):
        if not isinstance(data.get(field, []), list):
            _error(f"{field} must be a list")
        for item in data.get(field, []):
            if not isinstance(item, dict):
                _error(f"invalid {field} item")
            kind(item.get("track"), expected)
            if item["track"] in occupied:
                _error(f"{expected} track already has a source")
            occupied.add(item["track"])
    windows = []
    if not isinstance(data.get("overlap_switches", []), list):
        _error("overlap switches must be a list")
    for switch in data.get("overlap_switches", []):
        if not isinstance(switch, dict):
            _error("invalid overlap switch")
        identity(switch.get("id"))
        a = next((p for p in spans if p["id"] == switch.get("from")), None)
        b = next((p for p in spans if p["id"] == switch.get("to")), None)
        if not a or not b or a["track"] == b["track"]:
            _error("switch needs clips on different video tracks")
        start, end = max(a["start"], b["start"]), min(a["end"], b["end"])
        at, fade = switch.get("at"), switch.get("fade")
        if (type(at) is not int or type(fade) is not int or not 0 <= fade <= 12 or not start < at < end
                or at - fade // 2 < start or at + (fade + 1) // 2 > end):
            _error("switch fade must fit its overlap")
        if switch.get("sound") not in ("screen", a["id"], b["id"]):
            _error("invalid switch sound")
        pair = {a["id"], b["id"]}
        if any(s < end and start < e and pair & existing for s, e, existing in windows):
            _error("conflicting overlap switches")
        windows.append((start, end, pair))


def validate(parsed, data):
    validate_data(data)
    parsed.tracks = copy.deepcopy(data.get("tracks"))
    parsed.placements = {p["id"]: p for p in placements(data)} if "tracks" in data else {}
    parsed.overlap_switches = copy.deepcopy(data.get("overlap_switches", []))
    parsed.text_lanes = copy.deepcopy(data.get("text_lanes", []))
