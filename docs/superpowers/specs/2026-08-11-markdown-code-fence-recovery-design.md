# Markdown code-fence recovery design

## Goal

Keep LambChat's repair for fenced code markers attached to surrounding text,
while preventing one malformed code block from reversing every later Markdown
fence.

## Behavior

- An opening fence attached to preceding prose is still moved onto its own line.
- While a backtick fence is open, a marker followed by a language/info string
  is not treated as a closing fence. CommonMark permits only spaces or tabs
  after a closing marker.
- The next valid bare marker closes the open fence, so later headings and
  fenced blocks recover normally.
- Valid fenced blocks and inline code spans remain unchanged.

## Implementation

Update `normalizeMarkdownCodeFences` at its existing closing-fence branch. If
the remainder of the marker's line contains non-whitespace text, leave that
marker untouched and keep the current fence open. Text after a fence is
ambiguous and cannot be safely repaired as closing prose because the same
syntax is an opening fence with an info string. This is deliberately a narrow
parser correction: it does not rewrite model content, guess missing code, or
replace ReactMarkdown.

## Testing

Add a regression derived from the reported SystemVerilog response. It opens a
code fence, encounters another language-tagged marker before a bare closing
marker, and then contains a heading and a valid code block. Assert the
normalizer returns the input unchanged, which lets ReactMarkdown localize the
malformed section instead of cascading the error.

Run the focused normalizer tests, related Markdown component tests, frontend
lint, and frontend build.
