# Compact home review

Implemented October 14, 2026 after user selected Compact review prototype.

## Behavior

- Small floating panel keeps map visible. Toolbar entry is Review homes (Review on narrow screens).
- Overview shows one headline, clickable exclusion/review counts, two policy summaries, optional limits action, and one primary action.
- Home lists, reasons and capture dates open only on demand. Source coverage, per-filter counts and saved-review history stay inside Sources & saved reviews.
- Filter edits are drafts until Apply filters. Cancel preserves active filters. Saved reviews remain read-only; New review recalculates separately.
- Explicit Check N homes advances existing bounded API batches automatically. Pause finishes current batch, then stops. Close stops subsequent requests. Completed results remain cached. Source failures or non-advancing batches stop the queue.
- No backend source, design engine or saved neighborhood membership changes.

## Verification

- Production build passes.
- 15 frontend checks pass: eight map presentation checks and seven queue tests (multi-batch progress, pause, close, cache-only completion, source error, zero progress, repeated attempts without shrinking backlog).
- Browser default: 108 unchecked, one excluded. Exclusion opens the actual home and Google capture date.
- Optional year >=2000 and assessor FCV >=1,000,000: 97 excluded, 12 unchecked. Saved review succeeds and remains read-only. Default overview restored after checking.
- Mobile 390x844: panel fits viewport, document width 390 with no horizontal overflow. Viewport restored.
- No paid Google requests started during UI verification. Queue tests use local mock functions.
