# Changelog

## Unreleased

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
