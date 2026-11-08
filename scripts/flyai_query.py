"""Save a read-only FlyAI service response independently of Node's exit status.

Usage: python flyai_query.py --output query.json -- keyword-search --query 杭州
The real CLI bundle is launched with node using an argument array. Its stderr
and environment are never forwarded to the output JSON or terminal.
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile

from dependencies import checked_at, doctor


COMMON_HOTEL_FLAGS = {"--dest-name", "--key-words", "--poi-name", "--hotel-bed-types",
                      "--max-price", "--sort", "--check-in-date", "--check-out-date"}
TRANSPORT_FLAGS = {"--origin", "--destination", "--dep-date", "--dep-date-start", "--dep-date-end",
                   "--back-date", "--back-date-start", "--back-date-end", "--journey-type",
                   "--seat-class-name", "--transport-no", "--transfer-city", "--dep-hour-start",
                   "--dep-hour-end", "--arr-hour-start", "--arr-hour-end", "--total-duration-hour",
                   "--max-price", "--sort-type"}
QUERY_FLAGS = {
    "keyword-search": {"--query"},
    "ai-search": {"--query"},
    "search-flight": TRANSPORT_FLAGS,
    "search-train": TRANSPORT_FLAGS,
    "search-hotel": COMMON_HOTEL_FLAGS | {"--hotel-types", "--hotel-stars"},
    "search-marriott-hotel": COMMON_HOTEL_FLAGS | {"--hotel-brands", "--hotel-name"},
    "search-poi": {"--city-name", "--poi-level", "--keyword", "--category"},
    "search-marriott-package": {"--keyword", "--sort-type"},
}


class QueryError(RuntimeError):
    """A sanitized, user-readable failure without raw transport diagnostics."""


def validate_query(arguments):
    """Validate a read-only subcommand and its documented value-taking options.

    Credentials and debug/config flags cannot be passed through or recorded.
    Argument values, including shell metacharacters, remain literal strings.
    """
    arguments = list(arguments)
    if not arguments or arguments[0] not in QUERY_FLAGS:
        raise QueryError("Only documented read-only FlyAI search commands are allowed.")
    allowed = QUERY_FLAGS[arguments[0]]
    index = 1
    while index < len(arguments):
        flag, separator, value = arguments[index].partition("=")
        if flag not in allowed:
            raise QueryError("The query contains an unsupported option; credentials and config commands are prohibited.")
        if separator:
            if not value:
                raise QueryError("A query option is missing its value.")
            index += 1
        else:
            if index + 1 >= len(arguments) or arguments[index + 1].startswith("--"):
                raise QueryError("A query option is missing its value.")
            index += 2
    return arguments


def extract_response(stdout):
    """Extract service JSON, accepting CLI log lines but requiring a status field.

    Notices may precede a response. Once a JSON object begins, it must decode
    completely; nested objects in a truncated document cannot report success.
    """
    if isinstance(stdout, bytes):
        stdout = stdout.decode("utf-8", errors="replace")
    stdout = (stdout or "").lstrip("\ufeff").strip()
    try:
        document = json.loads(stdout)
    except (ValueError, TypeError):
        document = None
    if isinstance(document, dict) and "status" in document:
        return document
    responses = []
    decoder = json.JSONDecoder()
    cursor = 0
    while cursor < len(stdout):
        if stdout[cursor].isspace():
            cursor += 1
            continue
        if stdout[cursor] != "{":
            newline = stdout.find("\n", cursor)
            cursor = newline + 1 if newline >= 0 else len(stdout)
            continue
        try:
            document, cursor = decoder.raw_decode(stdout, cursor)
        except ValueError as error:
            raise QueryError("FlyAI returned incomplete or malformed service JSON.") from error
        if isinstance(document, dict) and "status" in document:
            responses.append(document)
    if not responses:
        raise QueryError("FlyAI did not return valid service JSON with a status field.")
    return responses[-1]


def _write_json(output, envelope):
    output = Path(output)
    temporary = None
    try:
        output.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=output.parent,
                                         prefix=output.name + ".", suffix=".tmp", delete=False) as handle:
            temporary = Path(handle.name)
            json.dump(envelope, handle, ensure_ascii=False, indent=2, allow_nan=False)
            handle.write("\n")
        os.replace(temporary, output)
    except (OSError, ValueError) as error:
        raise QueryError("Could not save the FlyAI query response to the requested output file.") from error
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def run_query(arguments, output, *, home=None, env=None, workspace=None, which=None,
              user_environment=None, runner=None, timeout=120):
    arguments = validate_query(arguments)
    runner = subprocess.run if runner is None else runner
    environment = dict(os.environ if env is None else env)
    state = doctor(home=home, env=environment, workspace=workspace, which=which,
                   user_environment=user_environment)
    node = state["tools"]["node"]["path"]
    bundle = state["tools"]["flyai"]["bundle"]
    if not node:
        raise QueryError("Node.js is unavailable; install it before querying FlyAI.")
    if not bundle:
        raise QueryError("FlyAI CLI bundle was not found; use dependencies.py install-missing or check the npm global installation.")
    try:
        process = runner([node, bundle, *arguments], shell=False, capture_output=True,
                         text=True, encoding="utf-8", errors="replace", timeout=timeout,
                         env=environment)
    except subprocess.TimeoutExpired as error:
        raise QueryError("FlyAI query timed out before a complete process result was available.") from error
    except (OSError, subprocess.SubprocessError) as error:
        raise QueryError("FlyAI could not be started; raw subprocess diagnostics were suppressed.") from error
    response = extract_response(process.stdout)
    status = response.get("status")
    success = (type(status) is int and status == 0) or status == "0"
    warning = None
    if process.returncode != 0:
        warning = "Node exited abnormally after returning service JSON; inspect process_exit separately from response.status."
    envelope = {"query": arguments, "response": response, "checked_at": checked_at(),
                "process_exit": process.returncode, "transport_warning": warning}
    _write_json(output, envelope)
    if not success:
        raise QueryError("FlyAI reported a service failure; inspect response.status in the saved JSON.")
    return envelope


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    if "--help" in argv and "--" not in argv:
        parser.print_help()
        return 0
    if "--" not in argv:
        print(json.dumps({"error": "Separate the FlyAI read-only command with -- after --output PATH."}), file=sys.stderr)
        return 2
    separator = argv.index("--")
    try:
        options = parser.parse_args(argv[:separator])
        envelope = run_query(argv[separator + 1:], options.output)
    except QueryError as error:
        print(json.dumps({"error": str(error)}, ensure_ascii=False), file=sys.stderr)
        return 1
    print(json.dumps({"output": str(options.output.absolute()), "service_status": envelope["response"]["status"],
                      "process_exit": envelope["process_exit"], "transport_warning": envelope["transport_warning"]},
                     ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
