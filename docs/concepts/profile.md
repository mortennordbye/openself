# The profile

A profile is a folder of Markdown files, one per entry, in its own git repository. It is built so
that a person can edit it by hand, a tool can check it, and an AI can find and cite what it needs
without reading everything. The full rules are in [the format](../reference/spec.md); this page is
the tour.

[![A profile folder: person.md, employments and assignments as one file each, certifications and education as tables; each entry has YAML frontmatter, your own words and flags; openself index writes INDEX.md, which tools and AI start from; every change is a git commit](../assets/diagrams/profile-anatomy.svg)](../assets/diagrams/profile-anatomy.svg)

*Click the diagram to open it full size.*

## The folder

```
openself.json          manifest: format, schema, owner, languages
INDEX.md               generated: the whole career on one page
person.md              you
employments/<id>.md    one file per job title at one employer
assignments/<id>.md    one file per assignment done under an employment
certifications.md      a table, one row per certificate
education.md           a table, one row per degree or trade certificate
photos/                photos of you and their edits (optional)
_removed/<id>.md       removed entries, kept with their reason
```

An **employment** is one real title at one employer; a new title is a new employment. An
**assignment** is work done under it: for one customer (`client`), for several at once
(`portfolio`), or for the employer itself (`internal`). A consultant has many assignments; someone
in a regular job may have none.

## An entry

```markdown
---
schema: 1
id: 2021-04-vestkraft-skymigrering
type: assignment
kind: client
employment: 2021-03-fjordsky-seniorkonsulent
customer: Vestkraft AS
customer_public: anonymised
customer_alias: et regionalt kraftselskap
role: Skyarkitekt
start: 2021-04
end: 2023-08
tech: [Azure, Terraform, Azure DevOps, PowerShell]
confidence: stated
---

## Hva oppdraget var

Flytting av rundt 60 servere fra eget datasenter til Azure.

## Eget bidrag

- Laget landingssonen i Terraform.

## Flagg

- ⚑ conflict: Gammel CV sier 50 servere, intervjuet sier rundt 60.
```

From the [fictional example](https://github.com/mortennordbye/openself/tree/main/example), in
Norwegian, its first language. Three parts:

- **Frontmatter**: the facts tools filter on. Every value is a plain string; an empty value means
  *not known*, never a guess. `customer_public` says whether a customer may be named, or only
  described by its alias or sector.
- **Sections in your own words**: what it was, what you did yourself, the result, how the
  technology was used, and verbatim quotes. Headings follow the profile's language.
- **Flags** (`⚑`): open `question`s and `conflict`s, and standing wishes every tool must respect:
  `emphasis` (stress this) and `omit` (leave this out). `grep -rn "⚑ \(question\|conflict\):"`
  lists everything still open.

## Ids

The file name is the id: `<yyyy-mm>-<customer or employer>-<role or title>`. An id never changes
and is never reused, so anything that cites it stays valid. A tool writing about you cites
`<id>` or `<id>#<section>`, for example `2021-04-vestkraft-skymigrering#contribution`. For a
customer under NDA, build the id from the alias, since ids show up in file lists and history.

## History

Every change is a commit whose subject says what changed and who did it:

```
2021-04-vestkraft-skymigrering: team size 5 → 4 [owner]
```

The actor is `owner`, `claude` (or another assistant) or `tool`. History is never rewritten:
restoring an old version (`openself restore`) writes it back as a new commit, and
`openself as-of DIR 2024-06-01` shows the profile as it was on that day. The web app has both under
History.

## Checks

`openself lint` (or `make check` in a home) reports three levels:

- **error**: the file breaks the format. Fix these.
- **warning**: probably a mistake, like a period outside its employment or a technology name that
  is not canonical (`tech-names.txt`).
- **prompt**: a gap worth asking you about, like a missing role or an open question. Prompts are
  the interview list an assistant works from; they are not failures.

## What others may see

What a CV or a site may show is decided in one place, the **public view** (`openself export`): it
drops `nda` assignments, shows customers only as `customer_public` allows, never exports
`reference` sections, and respects `omit`. Every tool that writes for others builds on it, so they
all show the same things.
