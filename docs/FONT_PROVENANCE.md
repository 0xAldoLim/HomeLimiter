# Bundled font provenance

The dashboard uses the original variable TrueType files published in the Google Fonts
repository. No font service is contacted at runtime. Copyright and SIL OFL 1.1 notices
are included beside each font and in the wheel's license records.

Verified against the public repository on 2026-11-10:

| Asset | Public Git blob SHA | SHA-256 of bundled bytes |
|---|---|---|
| [Host Grotesk](https://github.com/google/fonts/tree/main/ofl/hostgrotesk) | `25174036d06c95274f77cb85c157564aaabd6e35` | `74c77b8e850d58dd3d8b22e39111a73bef3450de9fb57018ef99119f2d484f5d` |
| [Atkinson Hyperlegible Mono](https://github.com/google/fonts/tree/main/ofl/atkinsonhyperlegiblemono) | `d5208f64392e7e15624be4afff7f1283bbaf8069` | `5ce8b1698d1ded7dff2178c1a3ad159470085a58ea239e8b2cb88f4fb4a6f646` |

The Host Grotesk binary contains a byte sequence that matches a broad token-pattern
heuristic. Its complete bytes match the public upstream blob exactly; it is not a
local credential. Release review verifies these immutable asset hashes separately
instead of treating arbitrary font-table bytes as UTF-8 application source.

Trailing spaces in the bundled OFL text files were normalized without changing their
wording. The TrueType files are unmodified.
