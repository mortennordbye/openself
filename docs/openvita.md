# CVs with OpenVita

[OpenVita](https://github.com/mortennordbye/openvita) is an open CV builder on top of OpenSelf.
It turns your profile into CVs: a first draft straight from the profile, then a workbench in the
browser where you read the CV, select text and say what to change, while an assistant does the
edits. Bring your own template, or your company's.

[![From profile to PDF: the profile goes through the public view, which leaves out omitted entries and shows customers only as allowed, into a first draft; in the workbench the CV is a PDF rebuilt on every save, edited by the assistant from your comments, in the template you choose; make release keeps the PDF you sent](assets/diagrams/openvita-flow.svg)](assets/diagrams/openvita-flow.svg)

## Set up

Needs Python 3.10 or newer, git and Docker (PDFs render in a container). Clone it next to your
home:

```sh
git clone --recurse-submodules https://github.com/mortennordbye/openvita.git
cd openvita
make new-person C=ola PROFILE=openself/example   # try it with the fictional example first
make serve C=ola
```

Then connect your own home. This keeps your CVs, applications and released PDFs in a vault of the
home (`cv/`), so they are encrypted and synced with the profile:

```sh
make connect-home C=<you> HOME=~/path/to/your-home
make serve C=<you>
```

On another machine: `make pull` in the home, then the same `make connect-home` in OpenVita.

## What you do there

| Command | What it does |
|---|---|
| `make draft C=<you>` | A complete CV from the profile, following its rules |
| `make serve C=<you>` | The workbench: CVs as real PDF text, revisions, comments for the assistant |
| `make new C=<you> APP=2026-11-acme-platform` | An application, with the job ad next to its CV |
| `make release C=<you> APP=...` | Keep the PDF you sent, numbered and tagged |
| `make templates C=<you>` | The templates you can use, and where each comes from |

## The rules it follows

- **The profile is the only source of facts.** A claim the profile does not support is weakened or
  removed from the CV, never added to the profile to make it fit.
- **What may be shown is decided by the public view.** Customers are named only as
  `customer_public` allows (and can be hidden altogether with `CUSTOMERS=hidden`), private
  references and anything flagged `omit` stay out, removed entries are never used.
- **Nothing personal is committed to OpenVita.** Your folders live in `local/` (ignored by git), and
  its own guard refuses names and text from connected profiles in ordinary files.

Templates, applications, interview prep and the assistant's rules are in the
[OpenVita README](https://github.com/mortennordbye/openvita#readme) and its
[TEMPLATES.md](https://github.com/mortennordbye/openvita/blob/main/TEMPLATES.md).
