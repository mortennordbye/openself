# Changelog

## Unreleased

- `openself import` and an Import button in the web app: certifications from a public Credly
  profile or Microsoft Learn transcript, with a preview, merged into `certifications.md`.
- Schema 1, additive: `imports` on certifications, the links to import from again.
- `openself guard` and git hooks (installed by push and pull) so a home never publishes plaintext.
- The encryption key can come from a password manager command; `openself keys --bitwarden` moves
  it into Bitwarden and openself asks for the master password when the vault is locked.
- Web app: opens on an overview of the career (a stream with assignments that open in place, a
  compact timeline, the most used technology, the open questions), dark mode, and icons.

## openself 1.1.0

- `openself serve`: a local web app to read, edit and version a profile (English and Norwegian).
- Encrypted sharing: `openself home`, `keys` (age, post-quantum when available, key in the macOS
  Keychain), `push` and `pull`, with the format of `profile.age` in section 7 of the spec.

## Schema 1, openself 1.0.0 (2026-10)

Named OpenSelf; earlier drafts called the format `career-profile` and the library `profilekit`.

First version: one file per entry, frontmatter subset, sections with language labels, typed
flags, removal to `_removed/`, generated `INDEX.md`, lint, git history with restore and as-of.
