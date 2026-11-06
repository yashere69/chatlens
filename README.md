# chatlens

A local workbench for the least glamorous and most useful part of evaluating a chat agent:
reading its conversations, one at a time, and writing down what went wrong.

**Try it in the browser (sample data, nothing leaves your machine):** https://yashere69.github.io/chatlens/

![chatlens: conversation list on the left with pass/fail dots, the conversation in the middle with the verdict form, failure codes counted on the right](docs/workbench.png)

```bash
pip install git+https://github.com/yashere69/chatlens
chatlens import "WhatsApp Chat with Asha.txt" --business "Your Store" -o traces.jsonl
chatlens serve traces.jsonl            # opens http://127.0.0.1:8765
```

## The method

Hamel Husain and Shreya Shankar have made a simple case in their writing on LLM evals:
before writing any eval, read real traces and do *error analysis*.

1. **Open coding.** For each conversation, mark pass or fail, then write a note and a short
   code for the first thing that went wrong.
2. **Axial coding.** Group the codes into a handful of failure modes.
3. **Count.** The most common failure modes are the evals worth writing.

General observability tools can store traces, but a dashboard isn't where this reading
happens. chatlens is built for that one job:

- One conversation on screen, laid out like the chat it was
- `j`/`k` to move, `p` to pass and advance, `f` to fail and jump to the note, `Ctrl+Enter`
  to save and advance. No mouse needed.
- Codes autocomplete from the ones you've already used, so twenty traces in, you're not
  inventing a fourth spelling of the same thing
- A live count of codes on failed conversations, so the patterns show up while you work
- Every save rewrites `labels.jsonl` through a temp file and a rename
  so a crash can't leave it half-written

## After labelling

```bash
chatlens report labels.jsonl --map axial.yaml     # failure-rate table
chatlens suggest labels.jsonl --compare axial.yaml
chatlens export traces.jsonl labels.jsonl -o scenarios/
```

`axial.yaml` is your grouping:

```yaml
policy-error: [wrong-shipping-fee, fee-amount-wrong, policy-number-wrong, wrong-return-window]
missing-info: [missing-tracking-link, no-tracking-link]
non-answer:   [ignored-question, question-ignored, generic-reply]
```

On the sample data:

```
40 traces labelled, 17 failed

failure mode              traces    rate
non-answer                     7     18%
policy-error                   5     12%
missing-info                   5     12%
```

**`suggest`** proposes a grouping from your codes alone, by shared content words with
"wrong", "missing" and "no" ignored (no model involved), and reports Cohen's kappa between
its grouping and yours. On the sample it finds 5 groups where I made 3, and agrees on every
failed trace once groups are matched (κ = 1.00). Over-splitting isn't penalised by that
number, which is why the group count is printed next to it. It's a second pair of eyes on
your axial coding, not a replacement for it.

**`export`** turns every failed conversation into a [turncheck](https://github.com/yashere69/turncheck)
scenario, with the customer's messages replayed in order and the note kept as the name.
You tighten the `expect_reply` steps to describe the correct behaviour, and the failure
becomes a regression test.

## Sample data

`examples/traces.jsonl` comes from a [nakli](https://github.com/yashere69/nakli) chat
export for a fictional store. `tools/make_sample.py` planted four kinds of agent mistakes
in 17 of the 40 conversations: a wrong shipping fee, a wrong return window, a missing
tracking link, and a canned non-answer. `labels.jsonl` marks them with the inconsistent
codes real reviewers produce ("missing-tracking-link" vs "no-tracking-link"), which is
exactly what axial coding exists to tidy up.

## Design notes

- **Local only.** The server binds to 127.0.0.1. Conversations usually contain customer
  data, so there's no reason for this to listen on a network.
- **One HTML file, no build step.** The page is about 210 lines of HTML, CSS and plain
  JavaScript, shipped inside the Python package. The Pages demo is the same file: when
  `/api/traces` isn't there, it loads the sample, keeps labels in `localStorage`, and
  offers a download.
- **JSONL in, JSONL out.** Both are easy to produce from any logging setup and easy to diff
  in git. Labelling decisions become reviewable like code.
- **First failure only.** The note asks what went wrong *first*. Later errors in a
  conversation are often caused by the first, and counting them separately inflates the
  wrong failure mode. This follows the error-analysis advice above.

## Limits

- One reviewer at a time. There's no merge for two people labelling the same file, and
  inter-rater agreement between people isn't computed yet (the kappa function is there).
- Tool calls show up only if your traces include `"role": "tool"` turns. The WhatsApp
  importer only knows customer and store messages.
- No LLM-assisted clustering of notes. `suggest` works on codes, not free text.

MIT licensed.
