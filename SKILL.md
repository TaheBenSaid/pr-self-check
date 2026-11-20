---
name: pr-self-check
description: Review your own diff before opening or updating a pull request. Catches debug prints, secrets, merge conflict markers, new TODOs, commented-out code, oversized PRs, heavy files and missing tests, then drafts a PR title and description. Use when the user is about to open a PR, push a branch for review, asks "is this ready for review?", "check my branch", "write the PR description", or wants a self-review of their changes.
---

# PR self-check

The checker is `scripts/pr_self_check.py` in this skill's folder. It's plain Python 3 with no dependencies and works on any language.

## Steps

1. From inside the repo, on the branch you're about to push, run:

   ```bash
   python3 <skill-folder>/scripts/pr_self_check.py
   ```

   It compares with `main`, then `master`. If the PR goes somewhere else, pass `--base <branch>`. Ask the user if you're not sure which branch the PR targets.

2. Show the user the `✗` and `!` lines. Skip the `✓` lines unless they ask.

3. Fix these yourself:

   - **Merge conflict markers.** Open the file, read both sides, and keep the right version. If you can't tell which side is right, ask instead of guessing.
   - **Debug leftovers.** Remove the `print`, `console.log`, `debugPrint`, `Log.d` and similar lines. Leave them if the project logs on purpose (a CLI that prints its output, a real logger call) and tell the user why you kept them.

4. **Secrets.** Never print, quote or paste a secret value, not in chat, not in a commit message, not in the PR. Refer to it by file and line only. Move the value to the project's env or config setup and read it from there. If the secret was already committed, even on a local branch, tell the user to rotate it: removing it from the diff doesn't make it safe. For files like `.env` or `*.keystore`, unstage them with `git rm --cached <file>` and check `.gitignore` covers them.

5. **TODO / FIXME.** Ask the user before removing or changing any. Some are deliberate follow-ups.

6. **Commented-out code, big PR, heavy files, missing tests.** Explain what was found and suggest what to do: delete the dead code, split the PR, drop the build output, add a test. Don't do any of it without the user's go-ahead.

7. Run the check again until nothing blocks.

8. Draft the PR:

   - A title in plain words that says what changed, under 60 characters, imperative mood: "Add saved cards to checkout", not "updates" or "fix stuff".
   - A description of 2 to 5 lines: what changed and why, how it was tested, anything the reviewer needs to know (migrations, flags, config, follow-ups). Add a line asking for screenshots if the diff touches UI.

   Show it to the user. Don't open or update the PR unless they ask.

## Read it like a reviewer

The script ends with a short checklist. Go through it with the user before the PR goes out, especially "did you run it yourself". A green report means the diff is tidy, not that the change works.
