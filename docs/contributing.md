# Contributing

Issues and pull requests are welcome on
[openself](https://github.com/mortennordbye/openself),
[openself-template](https://github.com/mortennordbye/openself-template) and
[openvita](https://github.com/mortennordbye/openvita).

## Ground rules

- **No real personal data**, ever: not in code, tests, docs, issues or pull requests. The
  [example profile](https://github.com/mortennordbye/openself/tree/main/example) (Ola Eksempel) is
  fictional; use it, or make up your own.
- **The library stays standard library only**, Python 3.10 or newer.
- **Format changes follow section 6 of the spec**: additive, optional fields within schema 1 and
  listed in `CHANGELOG.md`; anything that changes existing data is a new schema version with a
  migration.

## Working on openself

```sh
git clone https://github.com/mortennordbye/openself.git && cd openself
make test            # the tests (the sync tests need age 1.3 installed)
make docs            # preview this site on http://127.0.0.1:8000
make docs-build      # build it the way CI does, with --strict
make diagram         # re-render docs/assets/diagrams/*.d2 (needs Docker)
```

## Docs and diagrams

The site is built from `docs/` with ProperDocs and Material and published to GitHub Pages on every
push to `main`. A broken link between pages fails the build.

Diagrams are [D2](https://d2lang.com): a source in `docs/assets/diagrams/<name>.d2`, rendered to
`.svg` (used on this site) and `.png` (used in READMEs, since GitHub blocks the icons inside SVGs)
by `make diagram`. Commit the source and both renders; CI renders again and fails if they differ.
Every diagram imports `_style.d2` for the palette, and every node carries an icon from
`docs/assets/diagrams/icons/`. Keep them narrow: the docs column is about 700 pixels.

## Security

Found a way to make a home publish something unencrypted, or to read a profile without the key?
Report it privately through
[GitHub's security advisories](https://github.com/mortennordbye/openself/security/advisories/new)
rather than in an issue.
