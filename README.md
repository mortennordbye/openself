# OpenSelf

An open file format for everything about a person: who they are, what they have done, and where
they show up online. A profile is a plain folder of Markdown files with structured frontmatter,
in its own git repository, owned by the person it describes. Any tool can read it: a CV builder,
a form filler, a search, an AI assistant.

Schema 1 covers the career: person, employments, assignments, certifications and education.
Identity, accounts, projects, publications and credentials are meant to follow as new entry types
in later schema versions, in the same shape.

- **Readable by AI.** One small file per entry, a generated `INDEX.md` with the whole profile on
  one page, and stable ids an assistant can grep, open and cite instead of reading everything.
- **Owned and honest.** Only the owner adds facts, in their own words. Every entry says where its
  facts come from and how sure they are. Open questions and conflicts are flags, not guesses.
- **Versioned.** Every change is a git commit with who made it. Nothing is rewritten: an old
  version comes back as a new commit, and the whole profile can be read as it was on any date.
- **Portable.** A profile refers to nothing outside its folder, so it can live anywhere: a local
  folder, a submodule, an encrypted backup.

See [SPEC.md](SPEC.md) for the format and [example/](example/) for a complete fictional profile.

## openself, the library

`openself/` is the reference library and command line tool. Python 3.10 or newer, standard
library only.

```
python3 -m openself init my-profile --owner "Kari Nordmann" --lang nb,en
python3 -m openself new my-profile employment employer="Acme AS" title=Utvikler start=2024-01 end=ongoing
python3 -m openself lint my-profile
python3 -m openself log my-profile
```

Run it from this folder, or add the repository to another project and put it on `PYTHONPATH`:

```
git submodule add https://github.com/mortennordbye/openself.git openself
PYTHONPATH=openself python3 -m openself lint path/to/profile
```

Tests: `python3 -m unittest discover -s tests`. Changes to the format are listed in
[CHANGELOG.md](CHANGELOG.md); section 6 of the spec says how versions work.

## License

[MIT](LICENSE).
