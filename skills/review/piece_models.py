#!/usr/bin/env python3
"""What each piece of a review really ran on: its models, and any refusal.

A piece is named a model, and a tool can carry it on with another one after a refusal without
saying so (the review skill, *Refusals and model changes*). This reads the tool's own record of
each piece, never what the piece says of itself, and prints one line a piece.

    python3 piece_models.py --models <id>[,<id>...] <transcript or folder> [...]

`--models` lists the model ids the proposal named (`claude-opus-5-5,claude-sonnet-5-5`). A
transcript is a Claude Code sub-agent's `agent-<id>.jsonl`; a folder is searched for them. Claude
Code keeps them in `$CLAUDE_CONFIG_DIR/projects/<project>/<session>/subagents/`, each beside an
`agent-<id>.meta.json` that holds the piece's description.

Exit status: 0 when every piece ran on one named model with no refusal; 1 when a piece ran on a
model that wasn't named, on more than one model, or was refused; 2 when nothing could be read (no
transcript, or none with an answer in it), so that a format this script doesn't know is never
taken for a clean run. Standard library only.
"""

import argparse
import collections
import json
import pathlib
import sys


def read_piece(path):
    """One transcript: the models of its answers in order, and its refusals."""
    answers, refusals, bad_lines = [], [], 0
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        if not line.strip():
            continue
        try:
            entry = json.loads(line)
        except ValueError:
            bad_lines += 1
            continue
        if not isinstance(entry, dict) or entry.get("type") != "assistant":
            continue
        message = entry.get("message")
        if not isinstance(message, dict):
            continue
        model = message.get("model")
        if not model or model == "<synthetic>":
            continue
        answers.append({"model": model, "time": entry.get("timestamp", "")})
        if message.get("stop_reason") == "refusal":
            refusals.append({"model": model, "time": entry.get("timestamp", ""), "answer": len(answers)})
    description = ""
    meta = path.with_name(path.name[: -len(".jsonl")] + ".meta.json") if path.name.endswith(".jsonl") else None
    if meta and meta.is_file():
        try:
            description = str(json.loads(meta.read_text(encoding="utf-8")).get("description") or "")
        except ValueError:
            pass
    return {"path": path, "description": description, "answers": answers, "refusals": refusals,
            "bad_lines": bad_lines}


def changes(answers):
    """Where the model changed: (answer number, from, to, time)."""
    out = []
    for i in range(1, len(answers)):
        if answers[i]["model"] != answers[i - 1]["model"]:
            out.append((i + 1, answers[i - 1]["model"], answers[i]["model"], answers[i]["time"]))
    return out


def report(piece, named):
    """(the piece's line or lines, whether anything is wrong with it)."""
    answers = piece["answers"]
    name = piece["description"] or piece["path"].name
    if not answers:
        return [f"UNREAD   {name}: no answer with a model in {piece['path'].name}"], None
    counts = collections.Counter(a["model"] for a in answers)
    ran = ", ".join(f"{model} ({n} of {len(answers)} answers)" for model, n in counts.most_common())
    problems = []
    for model in counts:
        if model not in named:
            problems.append(f"ran on {model}, which the proposal doesn't name")
    for number, old, new, when in changes(answers):
        problems.append(f"changed from {old} to {new} at answer {number} of {len(answers)} ({when})")
    for refusal in piece["refusals"]:
        problems.append(f"{refusal['model']} refused at answer {refusal['answer']} ({refusal['time']})")
    lines = [f"{'CHECK' if problems else 'ok':8} {name}: {ran}"]
    lines += [f"         - {problem}" for problem in problems]
    return lines, bool(problems)


def transcripts(paths):
    found = []
    for raw in paths:
        path = pathlib.Path(raw)
        if path.is_dir():
            found += sorted(path.rglob("agent-*.jsonl"))
        elif path.is_file():
            found.append(path)
        else:
            print(f"{raw}: not a file or folder", file=sys.stderr)
    return found


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--models", required=True, help="the model ids the proposal named, comma-separated")
    parser.add_argument("paths", nargs="+", help="transcripts, or folders that hold them")
    args = parser.parse_args(argv)
    named = {m.strip() for m in args.models.split(",") if m.strip()}
    files = transcripts(args.paths)
    if not files:
        print("no transcript found: nothing was checked", file=sys.stderr)
        return 2
    wrong = read = 0
    for path in files:
        lines, problem = report(read_piece(path), named)
        print("\n".join(lines))
        if problem is None:
            continue
        read += 1
        wrong += problem
    if not read:
        print("no transcript held an answer with a model: nothing was checked", file=sys.stderr)
        return 2
    print(f"{read} pieces read, {wrong} to check" + ("" if read == len(files) else f", {len(files) - read} unread"))
    return 1 if wrong or read != len(files) else 0


if __name__ == "__main__":
    sys.exit(main())
