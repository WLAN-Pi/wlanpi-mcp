# Guidance for coding agents

Read this first.

## Branch and PR rules

- PRs target `main` (the default branch).
- Always branch from `main`, never from another PR branch. Rebase or
  recreate your branch if it has drifted; do not stack PR branches.
- One concern per PR. No mixed move-plus-change diffs.
- A version bump is a release. Only package-content changes bump
  `debian/changelog`; CI-only or docs-only changes do not.
- Keep `wlanpi_mcp/__version__.py` in sync with the deb version minus the
  revision (e.g. `0.6.7` for `0.6.7-1`). The deploy workflow fails if they
  diverge.

## Tooling and gates

All checks run through tox and are wired into CI workflows:
`python-lint-police.yml` (lint), `python-format-police.yml` (formatcheck),
`test-python-package.yml` (tests).

Before committing, run the gates that your change touches:

- `tox -e lint` : `ruff check wlanpi_mcp tests` then `mypy wlanpi_mcp`
- `tox -e formatcheck` : `ruff format --check wlanpi_mcp tests`
- `tox` : the py313 test suite plus coverage

`tox -e format` rewrites the tree with `ruff format` when the check fails.

### Rules that bite

1. **mypy runs against the installed package.** The `lint` env deliberately
   omits `skip_install` so tox installs the package and its runtime deps;
   that is what lets mypy resolve `mcp`, `uvicorn`, `httpx`, and so on. Do
   not add `skip_install = true` to `[testenv:lint]`, or every import becomes
   `import-not-found`.
2. **No bare generic annotations.** `mypy.ini` sets `disallow_any_generics`,
   so `dict`, `set`, `list`, and `tuple` need explicit type arguments.
   Follow the existing convention: JSON payloads are `dict[str, Any]`.
   Add `Any` to the existing `typing` import rather than a new import line.
3. **MCP docstrings are user-facing.** The MCP SDK serves each tool's,
   resource's, and prompt's `__doc__` verbatim as its description to every
   client. A missing or vague docstring shows up directly in the client's
   `tools/list`. ruff enforces Google-convention docstrings (D100-D106, D205,
   D401, D415) on the package; `tests/**` is exempt from the presence rules
   because test names self-describe.
4. **Line length is owned by the formatter.** `E501` is disabled; let
   `ruff format` wrap long lines. Do not hand-wrap to satisfy a linter that
   is off.
5. **Coverage artifacts are never committed.** `.coverage`, `coverage.xml`,
   and `coverage.svg` regenerate on every `tox` run and are gitignored.
   Do not `git add` them.
6. **Whitespace is handled by ruff** (W291/W293). There are no whitespace
   scripts; do not reintroduce them.

## Documentation

Write technical documentation using Diátaxis. Use clear, direct,
task-oriented prose. Verify all technical statements against the repository.
Do not invent behavior.

### House style

- Address the reader as "you."
- Use present tense and active voice.
- Put commands in fenced code blocks; put expected output immediately after.
- Use literal spelling for commands, paths, flags, config keys, and values.
- Never use emdashes; use commas or parentheses, or rewrite the sentence.
- Avoid filler such as "simply," "just," "obviously," and "easy."
- Link to the canonical reference instead of duplicating option details.