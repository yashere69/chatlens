# Changelog

## 0.3.1

- `import --from chat-logs` errors name the file (`prod-logs.jsonl:2`), not just its stem.
- Output is UTF-8 even when redirected on Windows, where it used to follow the code page
  and fail on Devanagari text.
- `suggest --compare` reports the adjusted Rand index and a per-group breakdown instead of
  Cohen's kappa after matching group names. The old number couldn't drop when `suggest`
  split one of your modes in two, so the sample scored 1.00 with 5 groups against 3. It
  now scores 0.69, and the breakdown shows which modes were split.
- `import` that finds no conversations is an error and writes nothing. `report`, `suggest`,
  `agree` and `export` with a labels file that doesn't exist are errors; before, `report`
  printed an empty table and exited 0.
- `serve` given a labels file that isn't chatlens's (nakli's intent labels, say, which
  default to the same name) says so and points at `--labels`.
- CI: the `ui` job fails if the browser tests can't run, instead of passing on skips.

## 0.3.0

- `serve` checks the Host header on every request (DNS rebinding), sends a hash-based
  Content-Security-Policy with nosniff, no-referrer and no framing, and caps label bodies
  at 64 KB.
- A damaged line in labels.jsonl stops the load with its line number. Before, it crashed,
  or a line without `trace` was lost on the next save.
- Traces may carry a BOM, numeric ids, non-string text and epoch-second `at` values; a turn
  that isn't an object is a clear error. `serve` refuses an empty file and explains a busy
  port.
- The page builds the conversation list once and patches it per keypress (21 ms per move
  at 10,000 conversations, down from about 200 ms) and keeps the current row in view.
- `chatlens agree`: verdict and failure-mode agreement between two reviewers.
- Malformed axial maps are reported as errors, not tracebacks.
- Browser tests (Playwright and axe) in a `ui` CI job; tests also run on Windows and macOS.

## 0.2.0

- `import --from chat-logs`: chat-completions message logs, including tool calls and list content
- turncheck `--transcripts` output loads directly (contract test)
- Label writes require JSON and a matching Origin, so other pages can't post to the local server

## 0.1.0

- Keyboard-first labelling page served locally; browser-only demo mode for Pages
- Atomic label storage in JSONL
- `report` (failure modes), `suggest` (axial grouping with Cohen's kappa), `export` (turncheck scenarios)
- WhatsApp export importer
