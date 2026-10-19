# Changelog

## openself 1.1.0

- `openself serve`: a local web app to read, edit and version a profile (English and Norwegian).
- Encrypted sharing: `openself home`, `keys` (age, post-quantum when available, key in the macOS
  Keychain), `push` and `pull`, with the format of `profile.age` in section 7 of the spec.

## Schema 1, openself 1.0.0 (2026-10)

Named OpenSelf; earlier drafts called the format `career-profile` and the library `profilekit`.

First version: one file per entry, frontmatter subset, sections with language labels, typed
flags, removal to `_removed/`, generated `INDEX.md`, lint, git history with restore and as-of.
