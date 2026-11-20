#!/usr/bin/env python3
import argparse
import os
import re
import subprocess
import sys

MAX_LINES = 400
MAX_FILES = 20
MAX_BYTES = 1024 * 1024
SHOW = 8
IGNORE_MARK = "pr-self-check: ignore"

DEBUG = [
    (r"\bdebugPrint\(", "debugPrint("),
    (r"(?<![\w.])print\(", "print("),
    (r"\bconsole\.(log|debug|trace|dir)\(", "console.log("),
    (r"\bSystem\.(out|err)\.print(ln)?\(", "System.out.println"),
    (r"\bfmt\.Print(ln|f)?\(", "fmt.Println"),
    (r"\bvar_dump\(", "var_dump("),
    (r"(?<![\w.>$])dd\(", "dd("),
    (r"\bLog\.[dv]\(", "Log.d("),
    (r"\bNSLog\(", "NSLog("),
    (r"\bdbg!\(", "dbg!("),
    (r"\bprintln!\(", "println!("),
    (r"\bdebugger;", "debugger"),
    (r"\bbinding\.pry\b", "binding.pry"),
    (r"\bpdb\.set_trace\(", "pdb.set_trace()"),
    (r"(?<![\w.])breakpoint\(\)", "breakpoint()"),
]
DEBUG = [(re.compile(p), label) for p, label in DEBUG]

SECRETS = [
    (r"\bAKIA[0-9A-Z]{16}\b", "AWS access key"),
    (r"-----BEGIN (RSA |EC |DSA |OPENSSH |PGP |ENCRYPTED )?PRIVATE KEY", "private key block"),
    (r"\bgh[pousr]_[A-Za-z0-9]{36,}\b", "GitHub token"),
    (r"\bxox[abprs]-[A-Za-z0-9-]{10,}", "Slack token"),
    (r"\bAIza[0-9A-Za-z_\-]{35}\b", "Google API key"),
    (r"\b[sr]k_live_[0-9A-Za-z]{16,}", "Stripe live key"),
    (
        r"(?i)(api[_-]?key|secret|token|passw(or)?d|client[_-]?secret|access[_-]?key)"
        r"[\w-]*[\"']?\s*[:=]\s*[\"'][^\"'\s]{16,}[\"']",
        "hardcoded credential",
    ),
]
SECRETS = [(re.compile(p), label) for p, label in SECRETS]

SECRET_FILES = re.compile(
    r"(^|/)(\.env(\.[\w.-]+)?|[^/]+\.(pem|key|p12|pfx|jks|keystore)|google-services\.json"
    r"|GoogleService-Info\.plist|key\.properties|id_(rsa|ed25519|ecdsa))$"
)
SAFE_ENV = re.compile(r"\.env\.(example|sample|template|dist)$")

TODO = re.compile(r"\b(TODO|FIXME|HACK|XXX)\b")
CONFLICT = re.compile(r"^(<{7}|>{7}|\|{7})( |$)")

BINARY_ARTIFACTS = re.compile(r"\.(zip|tar|gz|tgz|7z|rar|apk|aab|ipa|jar|war|exe|dll|so|dylib|a|o|class|mp4|mov)$", re.I)

# Lockfiles and generated code inflate the size without adding review work.
NOT_REVIEWED = re.compile(
    r"(^|/)(package-lock\.json|yarn\.lock|pnpm-lock\.yaml|pubspec\.lock|Podfile\.lock|Cargo\.lock"
    r"|poetry\.lock|Pipfile\.lock|composer\.lock|Gemfile\.lock|go\.sum|gradle\.lockfile)$"
    r"|\.(g|freezed|gr|config|mocks)\.dart$|\.min\.(js|css)$|\.pb\.go$|_pb2\.py$|\.snap$"
)

SOURCE_EXT = {
    "dart", "py", "js", "jsx", "ts", "tsx", "mjs", "vue", "svelte", "kt", "java", "scala",
    "swift", "m", "mm", "go", "rb", "php", "cs", "rs", "c", "cc", "cpp", "h", "hpp", "ex", "exs",
}
TEST_PATH = re.compile(
    r"(^|/)(tests?|__tests__|specs?|test_driver|integration_test|androidtest|[\w-]*tests)/"
    r"|_test\.\w+$|\.(test|spec)\.\w+$|(^|/)test_[^/]+\.py$|tests?\.(kt|java|swift|cs|m)$|spec\.(rb|kt|swift)$",
    re.I,
)

HASH_COMMENT_EXT = {"py", "rb", "sh", "bash", "zsh", "yaml", "yml", "toml", "r", "pl", "ps1", "cfg", "conf"}
DASH_COMMENT_EXT = {"sql", "lua", "hs"}
PROSE_EXT = {"md", "markdown", "txt", "rst", "adoc"}
CODE_LIKE = [
    re.compile(r"[;{}]\s*$"),
    re.compile(r"^(return|if|for|while|else|final|var|val|let|const|def|class|import|from|func|fun|"
               r"public|private|await|try|catch|switch|case)\b.*[(=:{;]"),
    re.compile(r"^[\w.\[\]'\"]+\s*(=|\+=|-=|:=)\s*\S"),
    re.compile(r"^[\w.]+\(.*\)\s*[;,]?$"),
    re.compile(r"^\)+[;,]?$"),
]


def git(*args):
    res = subprocess.run(["git", "-c", "core.quotePath=false", *args], capture_output=True, text=True,
                         encoding="utf-8", errors="replace")
    if res.returncode != 0:
        raise RuntimeError(res.stderr.strip() or "git " + " ".join(args) + " failed")
    return res.stdout


def ref_exists(ref):
    try:
        git("rev-parse", "--verify", "--quiet", ref + "^{commit}")
        return True
    except RuntimeError:
        return False


def pick_base(requested):
    if requested:
        return requested
    for ref in ("main", "master", "origin/main", "origin/master", "develop", "origin/develop"):
        if ref_exists(ref):
            return ref
    raise RuntimeError("couldn't find main or master, pass --base <branch>")


def ext_of(path):
    name = path.rsplit("/", 1)[-1]
    return name.rsplit(".", 1)[-1].lower() if "." in name else ""


def changed_files(base):
    out = git("diff", "--name-status", "-z", "-M", base).split("\0")
    files, i = {}, 0
    while i < len(out) - 1:
        status = out[i]
        if status.startswith(("R", "C")):
            files[out[i + 2]] = status[0]
            i += 3
        else:
            if not status.startswith("D"):
                files[out[i + 1]] = status[0]
            i += 2
    return files


def line_counts(base):
    out = git("diff", "--numstat", "-z", "-M", base).split("\0")
    counts, i = {}, 0
    while i < len(out) - 1:
        added, deleted, path = out[i].split("\t", 2)
        if path == "":
            path = out[i + 2]
            i += 3
        else:
            i += 1
        counts[path] = None if added == "-" else int(added) + int(deleted)
    return counts


def added_lines(base):
    path, line_no = None, 0
    for raw in git("diff", "-U0", "--no-color", "--no-ext-diff", "-M", base).splitlines():
        if raw.startswith("+++ "):
            path = None if raw == "+++ /dev/null" else raw[6:].rstrip("\t")
        elif raw.startswith("@@"):
            m = re.match(r"@@ -\S+ \+(\d+)", raw)
            line_no = int(m.group(1)) if m else 0
        elif raw.startswith("+") and path:
            yield path, line_no, raw[1:]
            line_no += 1


def comment_body(path, text):
    ext = ext_of(path)
    if ext in PROSE_EXT:
        return None
    s = text.strip()
    prefix = "#" if ext in HASH_COMMENT_EXT else "--" if ext in DASH_COMMENT_EXT else "//"
    if not s.startswith(prefix) or s.startswith(("///", "#!")):
        return None
    return s[len(prefix):].strip()


def looks_like_code(body):
    return bool(body) and any(p.search(body) for p in CODE_LIKE)


class Report:
    def __init__(self):
        self.sections = []

    def add(self, level, title, items=(), ok=None):
        self.sections.append((level, title, list(items), ok))

    def print(self):
        marks = {"ok": "✓", "warn": "!", "block": "✗"}
        for level, title, items, ok in self.sections:
            if not items and ok:
                print(f"✓ {ok}")
                continue
            count = f" ({len(items)})" if len(items) > 1 else ""
            print(f"{marks[level]} {title}{count}")
            for item in items[:SHOW]:
                print(f"    {item}")
            if len(items) > SHOW:
                print(f"    ...and {len(items) - SHOW} more")

    def count(self, level):
        return sum(1 for lvl, _, items, _ in self.sections if lvl == level and items)


def main():
    parser = argparse.ArgumentParser(description="Review your own diff before you open a PR.")
    parser.add_argument("--base", help="branch the PR goes into (default: main, then master)")
    args = parser.parse_args()

    try:
        # git prints paths from the repo root, so sizes only resolve from there.
        os.chdir(git("rev-parse", "--show-toplevel").strip())
        base = pick_base(args.base)
        merge_base = git("merge-base", base, "HEAD").strip()
        files = changed_files(merge_base)
        counts = line_counts(merge_base)
        lines = list(added_lines(merge_base))
        tracked = git("ls-files").splitlines()
        branch = git("rev-parse", "--abbrev-ref", "HEAD").strip()
    except RuntimeError as e:
        print(f"pr-self-check: {e}", file=sys.stderr)
        return 2

    total_lines = sum(c or 0 for c in counts.values())
    reviewed = {p: c for p, c in counts.items() if not NOT_REVIEWED.search(p)}
    reviewed_lines = sum(c or 0 for c in reviewed.values())

    print(f"PR self-check: {branch} vs {base} (merge base {merge_base[:7]})")
    print(f"{len(files)} files changed, {total_lines} lines, staged and unstaged changes included\n")

    if not files:
        print("Nothing to check. Your branch has no changes against the base.")
        return 0

    conflicts, secrets, debug, todos = [], [], [], []
    for path, n, text in lines:
        if CONFLICT.match(text):
            conflicts.append(f"{path}:{n}  {text[:7]}")
            continue
        if IGNORE_MARK in text:
            continue
        for rx, label in SECRETS:
            if rx.search(text):
                # Never echo the matched text, the report may end up in a CI log.
                secrets.append(f"{path}:{n}  {label}")
                break
        for rx, label in DEBUG:
            if rx.search(text):
                debug.append(f"{path}:{n}  {label}")
                break
        if TODO.search(text):
            todos.append(f"{path}:{n}  {text.strip()[:80]}")

    for path in files:
        if SECRET_FILES.search(path) and not SAFE_ENV.search(path):
            secrets.append(f"{path}  this file usually holds secrets, keep it out of git")

    commented = []
    run = []

    def flush():
        if len(run) >= 3:
            commented.append(f"{run[0][0]}:{run[0][1]}  {len(run)} lines of commented-out code")

    for path, n, text in lines:
        if not looks_like_code(comment_body(path, text)):
            flush()
            run = []
        elif run and (run[-1][0] != path or run[-1][1] != n - 1):
            flush()
            run = [(path, n)]
        else:
            run.append((path, n))
    flush()

    heavy = []
    for path, status in files.items():
        size = os.path.getsize(path) if os.path.isfile(path) else 0
        if size > MAX_BYTES:
            heavy.append(f"{path}  {size / MAX_BYTES:.1f} MB")
        elif status == "A" and BINARY_ARTIFACTS.search(path):
            heavy.append(f"{path}  build output or archive, usually belongs in a release, not the repo")

    size_notes = []
    if reviewed_lines > MAX_LINES:
        size_notes.append(f"{reviewed_lines} lines to review (over {MAX_LINES}). Split it if you can")
    if len(reviewed) > MAX_FILES:
        size_notes.append(f"{len(reviewed)} files (over {MAX_FILES}). Split it if you can")
    skipped = len(counts) - len(reviewed)
    size_hint = f", lockfiles and generated files skipped ({skipped})" if skipped else ""

    has_tests = any(TEST_PATH.search(p) for p in tracked) or any(TEST_PATH.search(p) for p in files)
    source = [p for p in files if ext_of(p) in SOURCE_EXT and not TEST_PATH.search(p) and not NOT_REVIEWED.search(p)]
    tests_touched = any(TEST_PATH.search(p) for p in files)

    r = Report()
    r.add("block", "Merge conflict markers", conflicts, ok="No merge conflict markers")
    r.add("block", "Possible secrets", secrets, ok="No secrets or secret files")
    r.add("warn", "Debug leftovers", debug, ok="No debug prints")
    r.add("warn", "New TODO / FIXME", todos, ok="No new TODOs")
    r.add("warn", "Commented-out code", commented, ok="No commented-out code blocks")
    r.add("warn", "Big PR", size_notes, ok=f"Size is fine: {reviewed_lines} lines, {len(reviewed)} files{size_hint}")
    r.add("warn", "Heavy files", heavy, ok="No large or binary files added")
    if not has_tests:
        r.add("ok", "", ok="Tests: skipped, this repo has no test files")
    elif source and not tests_touched:
        r.add("warn", "Source changed but no test touched",
              [f"{len(source)} source files changed, 0 test files. Add or update a test, or say why in the PR"])
    else:
        r.add("ok", "", ok="Tests touched" if source else "Tests: no source changes")
    r.print()

    print("\nRead it like a reviewer")
    print("  Does the title say what changed, in plain words?")
    print("  Did you run it yourself, not just build it?")
    print("  UI change? Add before and after screenshots.")
    print("  Anything the reviewer must know: migrations, flags, config, follow-ups?")
    print("  Would you approve this if someone else opened it?")

    blocking, warnings = r.count("block"), r.count("warn")
    print(f"\n{blocking} blocking, {warnings} to look at")
    return 1 if blocking else 0


if __name__ == "__main__":
    sys.exit(main())
