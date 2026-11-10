# Hallmark dashboard redesign

The user requested Hallmark for this project and future frontend builds, replacing the
initial sage sidebar and rounded summary-card presentation.

Hallmark source: [Nutlope/hallmark](https://github.com/Nutlope/hallmark), pinned for this
run at `407fa689f4a276f2fd389208d271d0fef08f5058`. Hallmark was installed as a personal
Codex skill; the user's personal instructions now select it for future new frontend work.
The repository's AGENTS.md and design.md preserve this project's own shared system.

## Direction

Full app-screen redesign. Console was selected from the dealt Ink, Console and
Ultraviolet materials because its instrument/readout vocabulary fits network
administration. It supplies typography, surfaces and color roles, not a marketing layout.

- Top navigation with a native mobile disclosure replaces the fixed left sidebar.
- Device/address ledger rows replace isolated device cards.
- Compact, API-derived figures use tabular numerals and rules instead of summary tiles.
- The enforcement-path readout stays distinct from traffic measurements.
- Paper and graphite modes use role-based OKLCH tokens, amber operator actions and blue
  system readings. Offline and unknown connection states use neutral text.
- Host Grotesk and Atkinson Hyperlegible Mono are bundled locally with SIL OFL notices.
  The dashboard makes no third-party font requests and retains its existing CSP.
- Loading, empty, error and full views remain explicit. Device filters are represented
  in the URL and survive reauthentication after a reload.

## Preservation and Git history

All destinations, API calls, authentication, form fields, exact target confirmations and
backend behavior remain. The original browser test was kept unchanged; a new browser
regression covers mobile-first navigation, breakpoint recovery, filters and state colors.

The old UI was introduced in commits that also implemented the controller and CLI.
The replacement undoes that presentation through a new commit rather than removing the
mixed functional commits or rewriting the published branch. Controller, database,
scheduler and Linux enforcement source are unchanged by this redesign.

## Verification

The initial four-route Hallmark baseline reported 86 Floor failures and 94 Reflex
findings. The replacement sweep checks the paper overview, graphite overview, device
inventory, scheduling and settings at eight viewport widths, producing 25 screenshots.
The before/after inventory preserves 13/13 links, 3/3 recorded fields and 6/6 figures.
One login heading was deliberately reworded and recorded in the stylesheet stamp.
Dynamic policy/identity forms and the remaining routes are exercised by the existing
real browser workflow; these counts are not a claim that the static record covers every
generated control.

The independent finish reviewer returned `fix`, with two defects:

1. A mobile-first load followed by desktop resize could leave navigation closed with no
   visible toggle. Desktop breakpoint recovery now opens it, and mobile destination
   selection closes the disclosure.
2. All overview connection states used success green. Only `online` now uses that token;
   offline and unknown states are neutral and retain their explicit text.

Both defects are covered by the new browser regression. Shell spacing and row padding
were tightened after the reviewer noted that the older overview surfaced more rows
earlier. Legible type, simulation notices and measured/configured distinctions remain.
Shared action-control geometry is one answered Finish item (F7), not a waived Floor gate.

Final local verification: 46 tests passed (including both browser workflows), with the
Linux-only namespace test skipped on this Windows host. Ruff, JavaScript syntax and
source/wheel builds passed. The confirming Hallmark sweep reported 0 Floor failures,
0 Reflex findings and 0 warnings, with F7 answered. The CI workflow also runs the new
browser regression alongside the unchanged original workflow.

## Copy and assets

Generic introductory captions were tightened to device inventory, identity and
enforcement tasks. Decorative orbit artwork, avatar initials, status dots and link-arrow
suffixes were removed. The login heading changed from “A little more balance at home” to
“Know your network. Choose its limits.” Meta strings use columns or normal punctuation.
Safety notices, consent/target confirmation text, model state labels, device facts and
policy values are preserved. No metrics, testimonials, logos or private traffic were added.

No external visual material is needed for these working screens. Production inventory
continues to come only from the configured authorized sources.
