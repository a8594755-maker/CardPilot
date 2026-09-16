#!/usr/bin/env python3
"""Small, fixed-format experiment log for CardPilot research."""

from __future__ import annotations

import argparse
import contextlib
import datetime as dt
import hashlib
import json
import os
import platform
import re
import socket
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any, Iterable


SCHEMA = "cardpilot.experiment.v1"
BENCHMARK = (
    "A frozen learned policy plays at least 100,000 fresh 200bb HUNL Slumbot hands, "
    "scores above 0 bb/100, and has a 95% confidence-interval lower bound above 0."
)
VALID_STATUSES = {"PLANNED", "RUNNING", "COMPLETED", "FAILED", "STOPPED"}
ID_RE = re.compile(r"^[a-z0-9][a-z0-9._-]{2,127}$")
TERMINAL_STATUSES = {"COMPLETED", "FAILED", "STOPPED"}
COMMAND_PLACEHOLDER_RE = re.compile(r"<[^>]+>|\.\.\.|\{[^}]+\}")


class LogError(RuntimeError):
    pass


def utc_now() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")


def slugify(value: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
    return slug[:64] or "experiment"


def default_run_id(title: str) -> str:
    stamp = dt.datetime.now(dt.timezone.utc).strftime("%Y%m%d-%H%M%S")
    return f"{stamp}-{slugify(title)}"


def run_git(repo: Path, *args: str) -> str | None:
    try:
        completed = subprocess.run(
            ["git", *args], cwd=repo, check=True, capture_output=True, text=True, timeout=10
        )
    except (FileNotFoundError, subprocess.SubprocessError):
        return None
    return completed.stdout.strip()


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def git_identity(repo: Path) -> dict[str, Any]:
    status = run_git(repo, "status", "--porcelain=v1")
    return {
        "commit": run_git(repo, "rev-parse", "HEAD"),
        "branch": run_git(repo, "branch", "--show-current"),
        "dirty": None if status is None else bool(status),
        "status_sha256": None if status is None else sha256_bytes(status.encode("utf-8")),
    }


def parse_pairs(values: Iterable[str]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for item in values:
        if "=" not in item:
            raise LogError(f"Expected KEY=VALUE, got: {item}")
        key, raw = item.split("=", 1)
        key = key.strip()
        if not key:
            raise LogError(f"Empty key in: {item}")
        try:
            result[key] = json.loads(raw)
        except json.JSONDecodeError:
            result[key] = raw
    return result


def atomic_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        "w", encoding="utf-8", newline="\n", dir=path.parent, delete=False
    ) as handle:
        json.dump(payload, handle, indent=2, ensure_ascii=False)
        handle.write("\n")
        temporary = Path(handle.name)
    os.replace(temporary, path)


def atomic_text(path: Path, value: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        "w", encoding="utf-8", newline="\n", dir=path.parent, delete=False
    ) as handle:
        handle.write(value)
        temporary = Path(handle.name)
    os.replace(temporary, path)


def artifact_label(repo: Path, path: Path) -> str:
    resolved = path.resolve()
    try:
        return resolved.relative_to(repo.resolve()).as_posix()
    except ValueError:
        return str(resolved)


def resolve_artifact(repo: Path, value: str) -> Path:
    path = Path(value)
    return path if path.is_absolute() else repo / path


def refresh_artifact_integrity(record: dict[str, Any], repo: Path) -> None:
    integrity: dict[str, Any] = {}
    for value in dict.fromkeys(record.get("artifacts", [])):
        path = resolve_artifact(repo, value)
        if path.is_file():
            integrity[value] = {
                "type": "file",
                "bytes": path.stat().st_size,
                "sha256": sha256_file(path),
            }
        elif path.is_dir():
            integrity[value] = {"type": "directory", "sha256": None}
        else:
            integrity[value] = {"type": "missing", "sha256": None}
    record["artifact_integrity"] = integrity


def command_audit(command: str) -> dict[str, Any]:
    value = " ".join(command.split())
    reasons: list[str] = []
    if not value:
        reasons.append("empty")
    if COMMAND_PLACEHOLDER_RE.search(value):
        reasons.append("contains_placeholder")
    if re.search(r"\b(same|bounded|followed by|on matched)\b", value, re.IGNORECASE):
        reasons.append("descriptive_not_exact")
    if value and not re.match(
        r"^(?:python(?:\.exe)?|py|node|npm|npx|pwsh|powershell|\.?[\\/]|[A-Za-z]:[\\/][^\s]*\.exe)\b",
        value,
        re.IGNORECASE,
    ):
        reasons.append("not_an_executable_command")
    return {"command": command, "exact": not reasons, "reasons": reasons}


def refresh_command_audit(record: dict[str, Any]) -> None:
    commands = record.setdefault("commands", [])
    if not commands and record.get("command"):
        commands.append({"command": record["command"], "recorded_at": record.get("created_at")})
    audited: list[dict[str, Any]] = []
    for item in commands:
        command = item if isinstance(item, str) else item.get("command", "")
        audit = command_audit(command)
        if isinstance(item, dict):
            audit["recorded_at"] = item.get("recorded_at")
        audited.append(audit)
    record["commands"] = audited
    record["reproducibility"] = {
        **record.get("reproducibility", {}),
        "exact_command_available": any(item["exact"] for item in audited),
        "all_recorded_commands_exact": bool(audited) and all(item["exact"] for item in audited),
        "exact_command_count": sum(bool(item["exact"]) for item in audited),
        "command_count": len(audited),
    }


def parse_time(value: str | None) -> dt.datetime | None:
    if not value:
        return None
    parsed = dt.datetime.fromisoformat(value.replace("Z", "+00:00"))
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=dt.timezone.utc)


def refresh_wall_time(record: dict[str, Any], now: str | None = None) -> None:
    started = parse_time(record.get("started_at"))
    if started is None:
        return
    terminal = record.get("ended_at") if record.get("status") in TERMINAL_STATUSES else None
    ended = parse_time(terminal or now or utc_now())
    if ended is not None:
        record["accounting"]["wall_time_seconds"] = max(
            0.0, round((ended - started).total_seconds(), 3)
        )


def capture_code_provenance(
    repo: Path, experiment_dir: Path, code_paths: list[str]
) -> tuple[dict[str, Any], list[str]]:
    code = git_identity(repo)
    code["code_paths"] = list(code_paths)
    code["captured_at"] = utc_now()
    code["provenance_complete"] = False
    artifacts: list[str] = []
    if not code_paths or code.get("commit") is None:
        code["provenance_gap"] = "No --code-path supplied or git metadata unavailable."
        return code, artifacts

    resolved_paths: list[Path] = []
    for value in code_paths:
        path = (repo / value).resolve()
        try:
            path.relative_to(repo.resolve())
        except ValueError as error:
            raise LogError(f"Code path escapes repository: {value}") from error
        if not path.exists():
            raise LogError(f"Code path does not exist: {value}")
        resolved_paths.append(path)

    relative_paths = [path.relative_to(repo.resolve()).as_posix() for path in resolved_paths]
    try:
        completed = subprocess.run(
            ["git", "diff", "--no-ext-diff", "--full-index", "--binary", "HEAD", "--", *relative_paths],
            cwd=repo,
            check=True,
            capture_output=True,
            timeout=120,
        )
        patch_bytes = completed.stdout
    except (FileNotFoundError, subprocess.SubprocessError) as error:
        code["provenance_gap"] = f"Could not capture git patch: {error}"
        return code, artifacts

    patch_path = experiment_dir / "code.patch"
    atomic_text(patch_path, patch_bytes.decode("utf-8", errors="replace"))
    patch_label = artifact_label(repo, patch_path)
    artifacts.append(patch_label)

    files: list[dict[str, Any]] = []
    seen: set[Path] = set()
    for path in resolved_paths:
        candidates = [path] if path.is_file() else sorted(item for item in path.rglob("*") if item.is_file())
        for candidate in candidates:
            if candidate in seen or "__pycache__" in candidate.parts:
                continue
            seen.add(candidate)
            files.append(
                {
                    "path": candidate.relative_to(repo.resolve()).as_posix(),
                    "bytes": candidate.stat().st_size,
                    "sha256": sha256_file(candidate),
                }
            )
    manifest_path = experiment_dir / "source_manifest.json"
    atomic_json(
        manifest_path,
        {"schema": "cardpilot.source-manifest.v1", "captured_at": code["captured_at"], "files": files},
    )
    manifest_label = artifact_label(repo, manifest_path)
    artifacts.append(manifest_label)
    code.update(
        {
            "patch": patch_label,
            "patch_sha256": sha256_file(patch_path),
            "source_manifest": manifest_label,
            "source_manifest_sha256": sha256_file(manifest_path),
            "source_files": len(files),
            "provenance_complete": True,
        }
    )
    return code, artifacts


@contextlib.contextmanager
def log_lock(root: Path):
    root.mkdir(parents=True, exist_ok=True)
    lock_path = root.parent / ".experiment_log.lock"
    with lock_path.open("a+b") as handle:
        handle.seek(0, os.SEEK_END)
        if handle.tell() == 0:
            handle.write(b"0")
            handle.flush()
        handle.seek(0)
        if os.name == "nt":
            import msvcrt

            msvcrt.locking(handle.fileno(), msvcrt.LK_LOCK, 1)
            try:
                yield
            finally:
                handle.seek(0)
                msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
        else:
            import fcntl

            fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
            try:
                yield
            finally:
                fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


def record_path(root: Path, run_id: str) -> Path:
    if not ID_RE.fullmatch(run_id):
        raise LogError(
            "Run ID must be 3-128 lowercase letters, digits, dots, underscores, or hyphens."
        )
    return root / run_id / "experiment.json"


def create_record(root: Path, repo: Path, args: argparse.Namespace) -> dict[str, Any]:
    run_id = args.id or default_run_id(args.title)
    path = record_path(root, run_id)
    if path.exists():
        raise LogError(f"Experiment already exists: {run_id}")
    now = utc_now()
    code, provenance_artifacts = capture_code_provenance(
        repo, path.parent, list(getattr(args, "code_path", []))
    )
    record: dict[str, Any] = {
        "schema": SCHEMA,
        "id": run_id,
        "title": args.title,
        "status": args.status,
        "created_at": now,
        "updated_at": now,
        "started_at": args.started_at or (now if args.status == "RUNNING" else None),
        "ended_at": None,
        "benchmark": BENCHMARK,
        "hypothesis": args.hypothesis,
        "material_change": args.change,
        "baseline": args.baseline,
        "source": args.source,
        "parent_id": args.parent,
        "command": args.command,
        "commands": [{"command": args.command, "recorded_at": now}] if args.command else [],
        "code": code,
        "runtime": {
            "cwd": str(repo.resolve()),
            "host": socket.gethostname(),
            "platform": platform.platform(),
            "python": platform.python_version(),
        },
        "accounting": {
            "new_training_hands": 0,
            "lineage_training_hands": 0,
            "offline_samples": 0,
            "evaluation_hands": 0,
            "wall_time_seconds": None,
        },
        "metrics": {},
        "artifacts": list(args.artifact) + provenance_artifacts,
        "notes": list(args.note),
        "result": {"summary": "", "conclusion": "", "decision": "", "next_step": ""},
        "tags": sorted(set(args.tag)),
    }
    record["accounting"].update(parse_pairs(args.count))
    record["metrics"].update(parse_pairs(args.metric))
    refresh_command_audit(record)
    refresh_wall_time(record, now)
    refresh_artifact_integrity(record, repo)
    atomic_json(path, record)
    return record


def load_record(root: Path, run_id: str) -> tuple[Path, dict[str, Any]]:
    path = record_path(root, run_id)
    if not path.exists():
        raise LogError(f"Unknown experiment: {run_id}")
    with path.open("r", encoding="utf-8") as handle:
        return path, json.load(handle)


def mutate_record(root: Path, repo: Path, args: argparse.Namespace, finishing: bool) -> dict[str, Any]:
    path, record = load_record(root, args.id)
    if args.status:
        record["status"] = args.status
        if args.status == "RUNNING" and not record.get("started_at"):
            record["started_at"] = utc_now()
    record["accounting"].update(parse_pairs(args.count))
    record["metrics"].update(parse_pairs(args.metric))
    record["artifacts"].extend(args.artifact)
    record["notes"].extend(args.note)
    commands = list(getattr(args, "command", []))
    if commands:
        record.setdefault("commands", []).extend(
            {"command": command, "recorded_at": utc_now()} for command in commands
        )
    for name in ("summary", "conclusion", "decision", "next_step"):
        value = getattr(args, name, None)
        if value is not None:
            record["result"][name] = value
    if finishing and record["status"] in {"PLANNED", "RUNNING"}:
        record["status"] = "COMPLETED"
    if finishing:
        record["ended_at"] = args.ended_at or utc_now()
    record["updated_at"] = utc_now()
    code = record.setdefault("code", {})
    if code.get("dirty") and not code.get("patch_sha256"):
        code.setdefault(
            "provenance_gap",
            "Historical record predates automatic patch/source-manifest capture; the exact dirty worktree cannot be reconstructed post hoc.",
        )
    record["artifacts"] = list(dict.fromkeys(record["artifacts"]))
    refresh_command_audit(record)
    refresh_wall_time(record, record["updated_at"])
    refresh_artifact_integrity(record, repo)
    atomic_json(path, record)
    return record


def validate_record(record: dict[str, Any], path: Path) -> list[str]:
    required = {
        "schema", "id", "title", "status", "created_at", "updated_at", "hypothesis",
        "material_change", "accounting", "metrics", "result",
    }
    errors: list[str] = []
    missing = sorted(required - record.keys())
    if missing:
        errors.append(f"{path}: missing {', '.join(missing)}")
    if record.get("schema") != SCHEMA:
        errors.append(f"{path}: unsupported schema {record.get('schema')!r}")
    if record.get("status") not in VALID_STATUSES:
        errors.append(f"{path}: invalid status {record.get('status')!r}")
    return errors


def audit_record(record: dict[str, Any], path: Path) -> list[str]:
    warnings: list[str] = []
    code = record.get("code", {})
    if not code.get("commit"):
        warnings.append(f"{path}: missing git commit")
    if code.get("dirty") and not code.get("patch_sha256"):
        warnings.append(f"{path}: dirty code without a captured patch SHA256")
    if not code.get("source_manifest_sha256"):
        warnings.append(f"{path}: missing source-manifest SHA256")
    accounting = record.get("accounting", {})
    if record.get("status") in TERMINAL_STATUSES and accounting.get("wall_time_seconds") is None:
        warnings.append(f"{path}: terminal record missing wall_time_seconds")
    refresh_command_audit(record)
    reproducibility = record.get("reproducibility", {})
    if not reproducibility.get("exact_command_available"):
        warnings.append(f"{path}: no directly rerunnable exact command")
    elif not reproducibility.get("all_recorded_commands_exact"):
        warnings.append(f"{path}: at least one recorded command is descriptive or contains placeholders")
    slumbot_hands = accounting.get("slumbot_hands", 0) or 0
    evaluation_hands = accounting.get("evaluation_hands", 0) or 0
    if slumbot_hands > evaluation_hands:
        warnings.append(
            f"{path}: evaluation_hands={evaluation_hands} is below slumbot_hands={slumbot_hands}"
        )
    integrity = record.get("artifact_integrity", {})
    for artifact in record.get("artifacts", []):
        metadata = integrity.get(artifact)
        if metadata is None:
            warnings.append(f"{path}: artifact has no integrity metadata: {artifact}")
        elif metadata.get("type") == "missing":
            warnings.append(f"{path}: artifact is missing: {artifact}")
        elif metadata.get("type") == "file" and not metadata.get("sha256"):
            warnings.append(f"{path}: file artifact has no SHA256: {artifact}")
    return warnings


def all_records(root: Path) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for path in root.glob("*/experiment.json"):
        with path.open("r", encoding="utf-8") as handle:
            record = json.load(handle)
        errors = validate_record(record, path)
        if errors:
            raise LogError("\n".join(errors))
        records.append(record)
    return sorted(records, key=lambda item: item["updated_at"], reverse=True)


def cell(value: Any, limit: int = 110) -> str:
    text = " ".join(str(value or "").split()).replace("|", "\\|")
    return text if len(text) <= limit else text[: limit - 1] + "…"


def markdown_index(title: str, intro: str, records: list[dict[str, Any]]) -> str:
    lines = [
        f"# {title}",
        "",
        f"Goal: {BENCHMARK}",
        "",
        intro,
        "",
        "| Updated (UTC) | ID | Status | Experiment | Result / next step |",
        "|---|---|---|---|---|",
    ]
    for record in records:
        result = record["result"].get("summary") or record["result"].get("next_step")
        if not result:
            result = record.get("material_change", "")
        lines.append(
            f"| {cell(record['updated_at'], 25)} | `{cell(record['id'], 60)}` | "
            f"{cell(record['status'], 15)} | {cell(record['title'])} | {cell(result)} |"
        )
    if not records:
        lines.append("| — | — | — | No experiments logged yet | — |")
    lines.append("")
    return "\n".join(lines)


def rebuild_index(root: Path) -> list[dict[str, Any]]:
    records = all_records(root)
    atomic_json(
        root.parent / "EXPERIMENTS.json",
        {
            "schema": "cardpilot.experiment-index.v1",
            "updated_at": utc_now(),
            "benchmark": BENCHMARK,
            "experiments": records,
        },
    )
    active = [record for record in records if "legacy-import" not in record.get("tags", [])]
    history = [record for record in records if "legacy-import" in record.get("tags", [])]
    atomic_text(
        root.parent / "EXPERIMENTS.md",
        markdown_index(
            "CardPilot active experiments",
            "Generated by `python research/experiment_log.py`. Start here. Historical results are not instructions; search `research/HISTORY.md` only when a prior route is relevant.",
            active,
        ),
    )
    atomic_text(
        root.parent / "HISTORY.md",
        markdown_index(
            "CardPilot historical experiments",
            "Generated legacy evidence for duplicate avoidance. These outcomes are observations, not restrictions on future methods.",
            history,
        ),
    )
    return records


def add_common_mutation_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--status", choices=sorted(VALID_STATUSES))
    parser.add_argument("--count", action="append", default=[], metavar="KEY=VALUE")
    parser.add_argument("--metric", action="append", default=[], metavar="KEY=VALUE")
    parser.add_argument("--artifact", action="append", default=[])
    parser.add_argument("--note", action="append", default=[])
    parser.add_argument(
        "--command", action="append", default=[],
        help="Append an exact, directly rerunnable command used by this experiment.",
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--root", type=Path, default=Path(__file__).resolve().parent / "experiments"
    )
    parser.add_argument(
        "--repo", type=Path, default=Path(__file__).resolve().parents[1]
    )
    commands = parser.add_subparsers(dest="command_name", required=True)

    start = commands.add_parser("start", help="Create a fixed-format experiment record")
    start.add_argument("--id")
    start.add_argument("--title", required=True)
    start.add_argument("--hypothesis", required=True)
    start.add_argument("--change", required=True)
    start.add_argument("--baseline", default="")
    start.add_argument("--source", default="")
    start.add_argument("--parent")
    start.add_argument("--command", required=True,
                       help="Exact, directly rerunnable first command for the experiment.")
    start.add_argument(
        "--code-path", action="append", default=[], required=True,
        help="Repository file or directory whose source and dirty patch must be captured.",
    )
    start.add_argument("--status", choices=["PLANNED", "RUNNING"], default="RUNNING")
    start.add_argument("--started-at", help="ISO-8601 timestamp; useful for history imports")
    start.add_argument("--count", action="append", default=[], metavar="KEY=VALUE")
    start.add_argument("--metric", action="append", default=[], metavar="KEY=VALUE")
    start.add_argument("--artifact", action="append", default=[])
    start.add_argument("--note", action="append", default=[])
    start.add_argument("--tag", action="append", default=[])

    update = commands.add_parser("update", help="Update progress and regenerate the index")
    update.add_argument("id")
    add_common_mutation_arguments(update)

    finish = commands.add_parser("finish", help="Close an experiment and record the decision")
    finish.add_argument("id")
    add_common_mutation_arguments(finish)
    finish.add_argument("--summary", required=True)
    finish.add_argument("--conclusion", required=True)
    finish.add_argument("--decision", required=True)
    finish.add_argument("--next-step", required=True)
    finish.add_argument("--ended-at", help="ISO-8601 timestamp; useful for history imports")

    commands.add_parser("index", help="Validate records and rebuild both indexes")
    commands.add_parser("validate", help="Validate every experiment record")
    audit = commands.add_parser("audit", help="Report provenance/accounting warnings")
    audit.add_argument("--since", default="", help="Only audit records created at or after ISO time.")
    audit.add_argument("--out-json", type=Path)
    audit.add_argument("--fail-on-warning", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    root = args.root.resolve()
    repo = args.repo.resolve()
    try:
        with log_lock(root):
            if args.command_name == "start":
                record = create_record(root, repo, args)
                rebuild_index(root)
                print(record["id"])
            elif args.command_name == "update":
                mutate_record(root, repo, args, finishing=False)
                rebuild_index(root)
                print(args.id)
            elif args.command_name == "finish":
                mutate_record(root, repo, args, finishing=True)
                rebuild_index(root)
                print(args.id)
            elif args.command_name == "audit":
                records = all_records(root)
                if args.since:
                    records = [item for item in records if item.get("created_at", "") >= args.since]
                findings = [
                    {"id": record["id"], "warnings": audit_record(record, record_path(root, record["id"]))}
                    for record in records
                ]
                warning_count = sum(len(item["warnings"]) for item in findings)
                report = {
                    "schema": "cardpilot.experiment-audit.v1",
                    "checked_at": utc_now(),
                    "records": findings,
                    "warning_count": warning_count,
                }
                if args.out_json:
                    atomic_json(args.out_json.resolve(), report)
                print(f"{len(findings)} experiment(s), {warning_count} warning(s)")
                if args.fail_on_warning and warning_count:
                    return 3
            else:
                records = rebuild_index(root)
                print(f"{len(records)} experiment(s) valid")
    except (LogError, OSError, json.JSONDecodeError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
