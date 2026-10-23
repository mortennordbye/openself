# OpenSelf

OpenSelf is an open file format for a person's record, owned by that person: who you are and what
you have done, and later where you show up online. Your profile is a folder of small Markdown
files in its own git repository. You edit it in a local web app or by hand, an AI assistant can
read it and cite it, and tools such as a CV builder use it as their only source of facts.

It is stored on GitHub only encrypted, so your repository can be public and still show nothing
but one opaque file.

[Get started](getting-started.md){ .md-button .md-button--primary }
[See the format](reference/spec.md){ .md-button }

## How the pieces fit

[![The OpenSelf ecosystem: openself, openself-template and openvita on GitHub; your home folder on your machine with profile/ and profile.age; the web app, an AI assistant and OpenVita working on profile/; profile.age pushed to your own repository through the guard; the secret key used only to decrypt](assets/diagrams/ecosystem-overview.svg)](assets/diagrams/ecosystem-overview.svg)

*Click the diagram to open it full size.*

| Repository | What it is | You use it to |
|---|---|---|
| [openself](https://github.com/mortennordbye/openself) | The format (`SPEC.md`, JSON Schemas), the Python library and command line tool, and the web app. Standard library only. | Nothing directly: it comes along as a git submodule. |
| [openself-template](https://github.com/mortennordbye/openself-template) | The starting point for your own repository, your *home*. | Click **Use this template** once. |
| your home (made from the template) | Holds `profile.age` (your profile, encrypted), the public keys and the tools. `profile/` is the readable copy on your machine. | Keep, edit and sync your profile. |
| [openvita](https://github.com/mortennordbye/openvita) | A CV builder on top of OpenSelf: drafts, a workbench, templates, applications. | Make CVs from your profile. Optional. |

## Choose your path

- **Keep my career in one place I own.** Follow [Getting started](getting-started.md). It takes
  about fifteen minutes, most of it writing.
- **Make CVs from it.** Get started first, then [CVs with OpenVita](openvita.md).
- **Let an AI help me write it.** [Working with an AI assistant](ai.md): it interviews you, writes
  your answers in your own words, and never adds facts.
- **Build a tool on the format.** Read [the format](reference/spec.md) and the
  [library](reference/cli.md#the-library). A profile refers to nothing outside its folder, so any
  tool can read it.

## What it promises

- **Yours.** Plain files in a repository you control. No service, no account, nothing to export.
- **Honest.** Only you add facts, in your own words. Open questions and conflicts are marked as
  flags, not guessed.
- **Versioned.** Every change is a commit that says who made it. Nothing is rewritten: an old
  version comes back as a new commit, and you can read the profile as it was on any date.
- **Private when stored.** Only `profile.age` leaves your machine, encrypted with
  [age](https://age-encryption.org). A guard on every commit and push refuses anything else.
