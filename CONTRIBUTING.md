# Contributing

Thanks for helping. The longer version, with how the docs and diagrams work, is
[Contributing](https://mortennordbye.github.io/openself/contributing/) on the docs site.

## Ground rules

- **No real personal data**, ever: not in code, tests, docs, issues or pull requests. Use the
  fictional [example](example/) profile.
- **Standard library only**, Python 3.10 or newer.
- **Format changes follow [SPEC.md](SPEC.md) section 6**, and are listed in [CHANGELOG.md](CHANGELOG.md).

## Flow

1. Fork, and branch from `main`.
2. Make the change, with a test when it changes behaviour.
3. Check locally:

   ```sh
   make test            # the tests (the sync tests need age 1.3)
   make docs-build      # the docs site, strict
   make diagram-check   # only if you touched docs/assets/diagrams (needs Docker)
   ```

4. Open a pull request. `main` is protected: it needs a pull request and green checks.

## Pull request titles

Titles follow [Conventional Commits](https://www.conventionalcommits.org) and become the
squash commit, which release-please reads to pick the next version:

```
feat(web): show the profile as of a date in the header
fix(guard): refuse a vault file that is not encrypted
docs: explain recipients and trust
```

`feat` makes a minor release, `fix` a patch, and `feat!` or a `BREAKING CHANGE:` footer a major
one. Other types (`docs`, `chore`, `ci`, `test`, `refactor`) do not release on their own.
