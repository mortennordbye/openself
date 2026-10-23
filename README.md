# OpenSelf

**[Documentation](https://mortennordbye.github.io/openself/)** ·
[Getting started](https://mortennordbye.github.io/openself/getting-started/) ·
[The format](SPEC.md)

An open file format for a person's record, owned by that person: your career now, later the rest
of where you show up. A profile is a folder of small Markdown files in its own git repository.
You edit it in a local web app, an AI assistant can read and cite it, and tools such as a CV
builder use it as their only source of facts. On GitHub it is stored only encrypted.

[![The OpenSelf ecosystem: openself, openself-template and openvita on GitHub; your home on your machine with profile/ and profile.age; the web app, an AI assistant and OpenVita working on profile/; profile.age pushed to your own repository through the guard](docs/assets/diagrams/ecosystem-overview.png)](docs/assets/diagrams/ecosystem-overview.png?raw=1)

| Repository | What it is |
|---|---|
| **openself** (this one) | The format, the Python library and CLI, and the web app |
| [openself-template](https://github.com/mortennordbye/openself-template) | The starting point for your own repository, which keeps the profile encrypted |
| [openvita](https://github.com/mortennordbye/openvita) | CVs from your profile (optional) |

## Start

Click **Use this template** on
[openself-template](https://github.com/mortennordbye/openself-template), then follow
[Getting started](https://mortennordbye.github.io/openself/getting-started/). You need Python
3.10+, git and [age](https://age-encryption.org) 1.3+.

To see what a profile looks like first, browse the fictional [example/](example/).

## Use it in your own tool

Standard library only. Add it as a submodule and run it, or import it:

```sh
git submodule add https://github.com/mortennordbye/openself.git openself
PYTHONPATH=openself python3 -m openself lint path/to/profile
```

Every command is in the [reference](https://mortennordbye.github.io/openself/reference/cli/).

## More

- [How the profile works](https://mortennordbye.github.io/openself/concepts/profile/) and
  [how encryption and sync work](https://mortennordbye.github.io/openself/concepts/sync/)
- [Working with an AI assistant](https://mortennordbye.github.io/openself/ai/)
- [Contributing](CONTRIBUTING.md) · [Security](SECURITY.md) · [Changelog](CHANGELOG.md)

## License

[MIT](LICENSE).
