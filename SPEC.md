# OpenSelf, schema 1

OpenSelf is an open format for a person's record: who they are, what they have done, and where
they show up. An OpenSelf profile is the only source of facts about that person for the tools that
use it: a CV builder, a form filler, a search, an AI assistant. It is built so that:

- an AI can find and cite what it needs without reading everything (one small file per entry, a
  generated index, stable ids),
- adding, changing and removing an entry touches one file,
- every change is kept, and any earlier version can be read or restored,
- it can be moved, shared as a submodule, or published encrypted, because it refers to nothing
  outside its own folder.

Schema 1 covers the career: the person, employments, assignments, certifications and education.
Later schema versions add more entry types (identity, accounts, projects, publications,
credentials) in the same shape: one folder per type, one file per entry, fields defined by a JSON
Schema in `schema/`.

`openself/` is the reference library (Python standard library only). `example/` is a complete
fictional profile. The JSON Schemas in `schema/v1/` are the field definitions; this document
explains them.

## 1. Folder

```
openself.json          manifest
README.md             generated
INDEX.md              generated: the whole career on one page
person.md             the owner
certifications.md     a table, one row per certificate
education.md          a table, one row per degree or trade certificate
employments/<id>.md   one file per employment
assignments/<id>.md   one file per assignment
_removed/<id>.md      removed entries
```

`openself.json`, the manifest:

```json
{"format": "openself", "schema": 1, "owner": "Ola Eksempel",
 "languages": ["nb", "en"], "readonly": false, "spec": "<url of this document>"}
```

`languages[0]` is the language the entries are written in. It sets the section headings and the
labels in `INDEX.md`. `readonly: true` marks a copy that must not be edited (for example a
decrypted checkout of a published profile).

Files starting with `.` are ignored. Nothing else belongs in the folder: source documents (old
CVs, exports) stay with the tool that collected them, and entries refer to them by label.

## 2. Entries

### Employment and assignment

An **employment** is one real title at one employer. A new title at the same employer is a new
employment. An **assignment** is work done under an employment:

| `kind` | Meaning |
|---|---|
| `client` | Work for one customer. |
| `portfolio` | Ongoing work for several customers at once (operations for a set of customers). |
| `internal` | Work for the employer itself: internal platforms, open source, tooling. |

A consultant has many assignments under one employment. A person in a normal job may have no
assignments at all, or a few internal ones for the projects worth telling apart.

### Ids

- The id is the file name without `.md`, and the `id` field must say the same.
- Pattern `^[a-z0-9][a-z0-9-]{2,80}$`. New ids are made as `<yyyy-mm>-<customer or employer>-<role
  or title>`, lowercased, with æ, ø, å written as ae, o, a.
- **An id never changes.** Correcting a date or a name does not rename the file; the id is a name,
  not data.
- **An id is never reused.** Removed entries keep theirs in `_removed/`. A new id that is taken
  gets `-2`, `-3`, and so on.
- For a customer under NDA, make the id from the alias or sector, not the name. Ids are visible in
  file lists and history.
- Cite an entry as `<id>`, or a section as `<id>#<section-id>` (`2023-09-acme-platform#contribution`).
  Bullets are not numbered in the file; a tool that shows a section back can number them on the fly.

### Frontmatter

Each entry starts with frontmatter: a small subset of YAML between `---` lines.

- One `key: value` per line. No nesting, no comments, no `|` or `>` blocks, no anchors.
- Values are plain, `"double quoted"` (JSON escapes) or `'single quoted'`.
- Lists are inline `[a, b, "c, d"]` or one `  - item` per line under `key:`.
- An empty value means **not known**. Never write a guess.
- **Every value is a string.** Read it the way `yaml.BaseLoader` does. Numbers (`allocation`,
  `team_size`) are digits in a string. This keeps `no`, `on`, `2024-02` and `010` from turning
  into something else.
- Quote a value that starts with `-?:,[]{}#&*!|>'"%@` or a backtick, contains `: ` or ` #`, or
  looks like a boolean or a non-integer number.

The canonical form, which `openself fmt` writes, has every field of the type in schema order,
empty ones included, so a reader sees what is missing.

**Fields** (see `schema/v1/*.schema.json` for formats and allowed values):

| Field | On | Meaning |
|---|---|---|
| `schema`, `id`, `type` | all | `1`, the id, the type |
| `kind` | assignment | `client`, `portfolio`, `internal` |
| `employment` | assignment | id of the employment it was done under |
| `customer` / `customers` | assignment | the real name / every name in a portfolio |
| `customer_public` | assignment | `public` (may be named), `anonymised` (use the alias), `nda` (ask before mentioning it at all), `unknown` (treat as anonymised, and ask) |
| `customer_alias`, `sector` | assignment | how to describe the customer when it may not be named |
| `role` | assignment | the owner's role, as they describe it |
| `employer`, `title`, `location`, `employment_type` | employment | the real title, exactly as the employer uses it |
| `start`, `end` | both | `YYYY-MM` (`YYYY` when the month is unknown); `end` may be `ongoing` |
| `breaks` | both | leave inside the period, `YYYY-MM/YYYY-MM`, both months included |
| `allocation`, `team_size` | assignment | percent of full time; people on the team, owner included |
| `tech`, `methods` | both | canonical names from `tech-names.txt` |
| `sources` | all | labels for where the facts come from (below) |
| `imports` | certifications | public pages the table is imported from (a Credly profile, a Microsoft Learn transcript link), so the import can run again |
| `confidence` | all | `verified`, `stated`, `old-cv`, `linkedin`, `needs-confirmation` |
| `status`, `last_reviewed` | all | `active` or `removed`; date of the last check or change |
| `removed`, `removed_reason` | removed | when and why, in the owner's words |
| `*_en` | some | a vetted English version of a text field when the profile is not in English |
| `x-<tool>-<name>` | all | a tool's own field. Kept as is and not validated |

**Sources** are labels, never paths, so the profile stays self-contained: `interview 2026-05-13`,
`intake:old-cv.pdf`, `linkedin`, `self-edit 2026-10-20`. A single fact from a different source
than the rest of the entry can say so inline: `[kilde: linkedin]`.

**Imports.** `openself import` reads the certificates on a public Credly profile or Microsoft
Learn transcript and merges them into `certifications.md`: a certificate that matches a row fills
its empty cells and makes a year-month date exact when the two agree; one that disagrees becomes a
`conflict` flag, never an overwrite; one not in the table becomes a new row. The source column and
`sources` get a label such as `Credly 2026-10-19`.

**Confidence** says how much a reader can lean on the entry. `verified` means the owner has
checked the entry as it stands. `stated` means the owner said it. `old-cv` and `linkedin` mean it
was read from such a document and the owner has not confirmed it. A tool that writes for others
(a CV, a form) should use `verified` and `stated` freely, and turn the rest into questions.

### Body

After the frontmatter, the body is Markdown in sections. Each `## ` heading is a section with a
fixed id; the heading text is the label in the profile's language (`labels/<lang>.json`), and a
reader accepts the label of any known language.

| Section id | Assignment | Employment | nb label |
|---|---|---|---|
| `summary` | what the assignment was | what the job really was | Hva oppdraget var / Hva jobben egentlig var |
| `challenge` | the customer's problem | | Utfordring |
| `contribution` | what the owner did personally, not the team | | Eget bidrag |
| `outcome` | the result; numbers only if the owner gave them | | Resultat |
| `tech-in-practice` | how the technology was used | the same, for the job | Teknologi i praksis |
| `own-words` | verbatim quotes | verbatim quotes | Brukerens ord |
| `reference` | contact for a reference. **Private: never exported** | | Referanse (privat) |
| `other` | anything else | anything else | Annet |
| `flags` | open questions and wishes | | Flagg |

`person.md` has `about`, `other`, `flags`. `certifications.md` and `education.md` start with a
table, columns in this order: Name, Issuer, Date, Expires, Source; and Degree, School, From, To,
Source. The header text is free (it is the language's labels).

All sections are optional. A different `##` heading is allowed but reported, and `###` and
deeper are free inside a section.

### Flags

A flag is a list item anywhere in the body, usually under `## Flagg`/`## Flags`:

```
- ⚑ question: How many nodes did the production cluster have?
- ⚑ conflict: LinkedIn says 2021, the old CV says 2020.
- ⚑ conflict (resolved 2026-10-20): LinkedIn says 2021, the old CV says 2020. Answer: «2020.»
- ⚑ emphasis: wants the Kubernetes part emphasised
- ⚑ omit: do not mention the on-call rota
- ⚑ correction: 2026-10-19 team size changed from 5 to 4 on the owner's word
```

`question` and `conflict` are open until resolved; resolving adds `(resolved <date>)` and the
owner's answer in quotes. `emphasis` and `omit` are standing wishes every tool must respect.
`correction` is a log line. The keywords of any label language are accepted (`spørsmål`,
`konflikt`, `vekt`, `utelat`, `retting`, `løst`), and a line with ⚑ that is not a valid flag is
an error. `grep -rn "⚑ \(question\|spørsmål\|conflict\|konflikt\):"` lists exactly the open
questions and conflicts.

## 3. Rules

0. **Only the owner adds facts, in their own words.** A tool that finds a claim the profile does
   not support weakens or drops the claim; it never adds to the profile to justify it. An AI may
   write the files, but only what the owner said or confirmed.
1. **Be verbose.** Keep every fact the owner gives, and keep their wording. Presentation is
   decided by the tool that uses the profile, not here.
2. **Never guess.** Unknown is empty. Conflicting sources become a `conflict` flag, resolved by
   the owner.
3. **One entry per file, one change per commit.** Never rename or reuse an id.
4. **Remove by moving** the file to `_removed/` with `status: removed`, `removed` and
   `removed_reason`. Only the whole profile is ever deleted (when the owner leaves, or asks).
5. **Readers start with `INDEX.md`**, then open or grep only the entries they need, and cite ids.
6. **Respect `customer_public`, `omit` and the private `reference` section** in anything shown to
   others.
7. **After a change, regenerate the index** (`openself index`) and check (`openself lint`).

## 4. Versions

The profile folder is its own git repository.

- Every change is a commit with the subject `<id>: <what changed> [<actor>]`, where actor is
  `owner`, `claude` (or another assistant) or `tool`. Several entries at once use the most
  important id or `profile`.
- Tags mark points worth finding again: `migrated-<date>`, and whatever a tool releases from the
  profile (a CV version).
- **History is never rewritten.** Restoring an old version of an entry writes it back as a new
  commit (`openself restore`).
- The whole profile as it was on a date is the last commit on or before that date
  (`openself as-of`).

A tool that uses the profile reads the folder it is pointed to. To keep a profile in a repository
of its own, even a public one, publish it encrypted with every version inside (section 7).

## 5. Checks

`openself lint` reports three levels:

- **error**: the file breaks the format (bad frontmatter or field, id not matching the file name,
  duplicate id, end before start, unknown employment, malformed flag).
- **warning**: probably a mistake (period outside the employment, more than 100% allocation at
  once, a tech name that is not canonical, unknown heading, stale `INDEX.md`).
- **prompt**: a gap worth asking the owner about (open questions and conflicts, unknown customer
  naming, missing role, allocation, team size or own contribution, gaps of more than three
  months between employments, entries not reviewed in 18 months). The prompts are the interview
  list.

## 6. Changing the format

Additive, optional fields are added within schema 1 and listed in `CHANGELOG.md`. Anything that
changes the meaning or form of existing data is a new schema version, with a migration in
`openself` that rewrites a profile from the old version to the new one.

## 7. Sharing encrypted

A profile can be kept in a repository of its own, even a public one, as a single encrypted file.
Such a repository (a *home*) holds:

```
.openself/recipients   age public keys allowed to decrypt, one per line, # comments
profile.age            the profile, encrypted
.gitignore             keeps profile/ (the decrypted working copy) out
```

`profile.age` is an [age](https://age-encryption.org) file encrypted to every recipient. Its
plaintext is the line `OPENSELF-BUNDLE-1`, a newline, the length of the bundle as 8 bytes (big
endian), a `git bundle` of the whole profile repository (`--all`, so every version), and zero
bytes up to a multiple of 65536. Readers decrypt, check the first line, take the bundle, and
clone or fast-forward from it. They never merge silently: if the profile changed in two places,
the user merges with git.

A tool that writes to a home must never let it publish plaintext. `openself guard` checks the
index before a commit and every outgoing commit before a push, and refuses anything under
`profile/`, any file outside an allow list (the files above, the tools next to them, and globs in
`.openself/allow` that start with a fixed name), an allowed file that contains the person's name,
email or phone, an employer or a customer from the decrypted profile, a `profile.age` that is not
an age header followed by ciphertext only, and anything but public keys in the recipients file.
Whatever git cannot read counts as a problem. It runs as git pre-commit and pre-push hooks, which
`openself` installs on every push and pull (a push refuses when another tool's hook is in the
way), and again on every outgoing commit before each upload. `openself guard --history` checks
every commit, for CI. A push commits only `profile.age`, the recipients and `.gitignore`.

A home whose main branch takes no direct pushes (a GitHub ruleset that requires a pull request
and the guard check) says so in `.openself/config` with the line `push = pull-request`. A push
then goes to the branch `openself/snapshot` and opens a pull request that GitHub merges by
itself, as a merge commit, once the check passes; every machine fast-forwards to it.

The recipients file comes in with every pull, so a tool never encrypts to a key just because it is
listed there. Each machine keeps the keys it has approved inside its `.git` folder, where no pull
reaches; the first sync on a machine approves the list as it is, `openself keys` approves the
machine's own key, and a push refuses while the file holds any other key until the owner runs
`openself trust`. Encrypting needs only the public keys, so a tool (or an AI) can push without
ever holding the secret key.

## 8. Privacy

A profile holds personal data and often confidential customer details. It lives on the owner's
machine by default. Sharing or publishing it is the owner's choice, and a tool that exports from
it leaves out `reference` sections, `nda` customers and anything flagged `omit` unless the owner
says otherwise. When the owner leaves or asks, the whole folder and its history are deleted.
