# pr-self-check

_By [Tahe Ben Said](https://tahebensaid.dev), senior mobile engineer. More apps and tools at [tahebensaid.dev](https://tahebensaid.dev)._

Reviews your own diff before you open a pull request, and catches the stuff a reviewer shouldn't have to point out: a forgotten `console.log`, a key in the code, a merge conflict marker, a 900-line PR.

It works with any language and any stack. One Python file, standard library only.

It works two ways:

- as a plain script you run from the terminal, a git hook or CI,
- as an agent skill, so Claude Code (or any agent that supports the Agent Skills format) can run it, clean up the easy stuff and draft the PR description for you.

## Run it

```bash
git clone https://github.com/TaheBenSaid/pr-self-check.git
python3 pr-self-check/scripts/pr_self_check.py
```

Run it from inside your repo, on your feature branch. It compares your branch with `main` (or `master` if there's no `main`). Pass `--base develop` to compare with another branch.

It looks at everything you've committed on the branch, plus staged and unstaged changes. Untracked files are ignored until you `git add` them.

```
PR self-check: messy vs main (merge base 9a16493)
26 files changed, 575 lines, staged and unstaged changes included

✗ Merge conflict markers (2)
    src/checkout.js:15  <<<<<<<
    src/checkout.js:19  >>>>>>>
✗ Possible secrets (3)
    src/checkout.js:4  hardcoded credential
    src/checkout.js:6  AWS access key
    .env  this file usually holds secrets, keep it out of git
! Debug leftovers (3)
    src/checkout.js:9  console.log(
    src/debug.py:2  print(
    src/debug.py:4  breakpoint()
! New TODO / FIXME
    src/checkout.js:10  // TODO: handle declined cards
! Commented-out code
    src/checkout.js:11  3 lines of commented-out code
! Big PR (2)
    575 lines to review (over 400). Split it if you can
    26 files (over 20). Split it if you can
! Heavy files
    src/hero.bin  1.4 MB
! Source changed but no test touched
    24 source files changed, 0 test files. Add or update a test, or say why in the PR

Read it like a reviewer
  Does the title say what changed, in plain words?
  Did you run it yourself, not just build it?
  UI change? Add before and after screenshots.
  Anything the reviewer must know: migrations, flags, config, follow-ups?
  Would you approve this if someone else opened it?

2 blocking, 6 to look at
```

And on a clean branch:

```
PR self-check: clean vs main (merge base 9a16493)
2 files changed, 5 lines, staged and unstaged changes included

✓ No merge conflict markers
✓ No secrets or secret files
✓ No debug prints
✓ No new TODOs
✓ No commented-out code blocks
✓ Size is fine: 5 lines, 2 files
✓ No large or binary files added
✓ Tests touched
...
0 blocking, 0 to look at
```

`✗` blocks, `!` is worth a look, `✓` is fine. The script exits with 1 when something blocks, 0 otherwise.

## What it checks

Only lines and files you added. Old problems already on `main` aren't your PR's fault, so they're left alone.

| Blocks the PR | Worth a look |
| --- | --- |
| Merge conflict markers | Debug prints: `print(`, `debugPrint(`, `console.log(`, `System.out.println`, `fmt.Println`, `var_dump`, `dd(`, `Log.d(`, `NSLog(`, `dbg!`, `breakpoint()` and friends |
| AWS, GitHub, Slack, Google and Stripe live keys | New `TODO`, `FIXME`, `HACK` |
| Private key blocks | 3 or more lines of commented-out code in a row |
| `api_key = "..."` style long literals | Over 400 changed lines or over 20 files |
| `.env`, `*.pem`, `*.key`, `*.jks`, `*.keystore`, `key.properties`, `google-services.json`, `GoogleService-Info.plist` | Files over 1 MB, and APKs, IPAs, zips and other build output |
| | Source changed but no test file touched (skipped if the repo has no tests) |

Secret values are never printed, only the file, the line and the kind of secret. Lockfiles and generated files (`package-lock.json`, `pubspec.lock`, `*.g.dart`, `*.min.js`...) don't count toward the size limit.

Got a line that's fine on purpose, like a CLI that really should `print`? Add `pr-self-check: ignore` in a comment on that line.

## Use it as a skill

Clone it straight into your agent's skills folder, for example:

```bash
git clone https://github.com/TaheBenSaid/pr-self-check.git ~/.claude/skills/pr-self-check
```

Or into the skills folder inside one project. Then ask something like "check my branch before I open the PR" or "is this ready for review?". The skill runs the check, removes debug prints and conflict markers, tells you about secrets without repeating them, asks before touching your TODOs, and drafts a PR title and description.

## Use it as a git hook or in CI

To run it before every push, copy the script into your repo, for example under `tools/`, and add `.git/hooks/pre-push`:

```bash
#!/bin/sh
python3 tools/pr_self_check.py
```

In CI, run the same line as a step. Make sure the base branch is fetched, for example `actions/checkout` with `fetch-depth: 0`, then pass `--base origin/main`.

## More tools

This is part of a series of small tools I use on real projects, each tied to a problem I write about. The full list is in [flutter-skills](https://github.com/TaheBenSaid/flutter-skills).

## License

MIT
