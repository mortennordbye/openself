# Commands

## In a home

Run these in your home folder. `make` on its own prints the list; each is a thin wrapper around
`./self`, which runs the framework's `openself` with the home's paths filled in.

| Command | What it does |
|---|---|
| `make serve` | Open the web app (asks for the password manager's password if the key is there) |
| `make ai` | Start Claude Code here, watching the web app's requests |
| `make pull` | Download and decrypt the profile and every vault |
| `make push` | Check, then encrypt, commit and upload |
| `make check` | The guard and the profile lint |
| `make keys` | Make this machine's key and add its public key to the recipients |
| `make trust` | Approve recipients this machine has not seen yet |
| `make bitwarden` | Move the key into Bitwarden and read it from there from now on |
| `make vault NAME=docs` | Make a vault: `docs/`, any files, pushed encrypted as `docs.age` |
| `make vaults` | The vaults, and which have changes to push |

## openself

`python3 -m openself <command>` (or `./self <command>` in a home). In a home, `DIR` defaults to its
`profile/` and `HOME` to the home. `python3 -m openself --help` prints the current list.

### The profile

| Command | What it does |
|---|---|
| `init DIR [--owner NAME] [--lang nb,en]` | Create an empty profile |
| `new DIR TYPE key=value ... [--section id=text]` | Create an employment or assignment; prints its id |
| `remove DIR ID --reason TEXT` | Move an entry to `_removed/` |
| `commit DIR ID WHAT [--actor owner\|claude\|tool]` | Reindex and commit as `<id>: <what> [<actor>]` |
| `lint DIR [--strict] [--quiet]` | Check; exit 1 on errors (and warnings with `--strict`) |
| `fmt DIR [--check]` | Rewrite every entry in canonical form |
| `index DIR` | Rewrite `INDEX.md` and `README.md` |
| `import DIR [URL ...] [--dry-run]` | Certifications from a Credly profile or a Microsoft Learn transcript link |
| `photo list\|add\|use\|remove DIR ...` | Manage photos: originals, edits and the person's photo |
| `export DIR [--no-names] [--lang en\|nb]` | The public view as JSON: what a CV or site may show |

### History

| Command | What it does |
|---|---|
| `log DIR [ID]` | History of the profile or one entry |
| `show DIR ID REV` | An entry as it was at a revision |
| `restore DIR ID REV [--actor ...]` | Bring an old version back as a new commit |
| `as-of DIR DATE` | The index as the profile was on `DATE` (`YYYY-MM-DD`) |

### Homes and sync

| Command | What it does |
|---|---|
| `serve [DIR] [--port 8765] [--no-browser]` | The web app for a profile |
| `home [DIR]` | Make `DIR` a home: `.openself/`, `profile/`, `.gitignore` |
| `keys [HOME] [--bitwarden]` | Make this machine's key and add it to the recipients |
| `push [HOME]` / `pull [HOME]` | Encrypt and upload / fetch and decrypt, profile and vaults |
| `guard [HOME] [--hook pre-commit\|pre-push] [--history]` | Refuse anything unencrypted; `--history` checks every commit (CI) |
| `trust [HOME] [--yes]` | Approve recipients this machine has not seen yet |
| `vault add NAME [HOME]`, `vault list [HOME]` | Make a vault; list vaults and their changes |

### Assistants

| Command | What it does |
|---|---|
| `assistant watch [DIR]` | For an assistant session, as a background monitor: prints each request from the web app |
| `assistant list [DIR]` | The requests and their status |
| `assistant done N [DIR] [--note TEXT]` | Mark request `N` done, with what changed |

## The library

`openself/` is a Python package, 3.10 or newer, standard library only. To use it from another
project, add the repository as a submodule and put it on `PYTHONPATH`:

```sh
git submodule add https://github.com/mortennordbye/openself.git openself
PYTHONPATH=openself python3 -m openself lint path/to/profile
```

```python
from openself import model, export

profile = model.load_profile("path/to/profile")
view = export.public_view(profile, names=False)   # what a public page may show
```

The web app's interface (`openself/web/static/app.js`) is a module, `OpenSelfUI(container, host)`,
so another tool can mount it with its own `host` object; `index.html` is the standalone host.
