# PR #134 stale Draft dogfood fixture

This disposable branch exercises source-side publication recovery without
mutating canonical Task 13 or Draft PR #29.

Reference failure identities:

- stale publication metadata: `97dbf03607d8eaabfc76104be2722d89aa6ddf2d`
- current canonical Task head semantics: `8313bcfcfdee4a3985f8b5dd48861b2b2bcb69a4`
- historical blocked reviewer: `WU-13-28`

The second fixture revision advances the live Task branch while intentionally
leaving Draft PR publication metadata at the first fixture revision.
