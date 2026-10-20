# Changelog

## Unreleased

- `INDEX.md` says under the technology table what its months are: calendar months in which an
  assignment lists the technology, breaks left out, overlaps counted once, allocation not used.

- `push` uploads a snapshot an earlier push committed but did not get out (refused, offline),
  instead of waiting for the next change. In a pull-request home it no longer replaces another
  machine's waiting snapshot branch, and asks for a pull when the remote main is ahead.

- `lint`: warns about sources cited inline (`[kilde: ...]`), and prompts for a technology in
  `tech` the text never names, employments sharing more than one month, and the person's missing
  title, languages or about text.

- The public view: `openself export` and `export.public_view` give what a tool may show to others
  (spec section 8) as JSON, so a CV and a portfolio site leave out the same things. `export.leaks`
  checks generated output for hidden customer names and reference sections. `names=False` (and
  `openself export --no-names`) hides every real customer name behind the alias or sector.

- Vaults: a home can keep more folders of any files (documents, images, PDFs), each its own git
  repository, declared with `vaults = ...` in `.openself/config` and encrypted into `<name>.age`
  in the profile's format. `openself vault add` and `vault list`; push and pull handle every vault,
  and the guard refuses a vault's plaintext and checks its `.age` (spec section 7).

- Schema 1, retired: `sources` and the Source column of the certifications and education tables.
  The profile is the owner's own record and is itself the source; tools cite entry ids, and the
  history says who changed what. Older files still read; `lint` warns and `openself fmt` drops them.
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
