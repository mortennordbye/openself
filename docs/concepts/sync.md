# Encryption and sync

Your profile lives readable on your machine and encrypted everywhere else. This page explains
what `make push` and `make pull` do, what the guard refuses, and where the key lives.

[![make push turns profile/ into a git bundle with every version, encrypts it with age to the public keys in .openself/recipients, and the guard lets only .age files and keys through; GitHub holds profile.age and runs the guard on every push; on another machine make pull decrypts it with the secret key and fast-forwards profile/](../assets/diagrams/sync-encryption.svg)](../assets/diagrams/sync-encryption.svg)

## The home

A home is your repository, made from
[openself-template](https://github.com/mortennordbye/openself-template). It contains:

| Path | Committed | What |
|---|---|---|
| `profile.age` | yes | the whole profile repository, every version, encrypted |
| `.openself/recipients` | yes | the age public keys that may decrypt, one per line |
| `.openself/config` | yes | settings: vaults, how push uploads |
| `openself/` | yes, as a submodule | the framework |
| `self`, `Makefile`, `README.md`, `AGENTS.md` | yes | the tools and their instructions |
| `profile/` | **never** | the readable profile, its own git repository |
| `<vault>/` | **never** | each vault's readable files |

## Push and pull

`make push` packs `profile/` into a `git bundle` with every commit, pads it to a multiple of
64 KiB, encrypts it with [age](https://age-encryption.org) to every key in
`.openself/recipients`, commits `profile.age` and pushes. It needs only the public keys, so an
assistant can push for you without ever holding the secret one. It skips the upload when nothing
changed, because every upload is visible in the public history.

`make pull` fetches, decrypts and fast-forwards `profile/`. It never merges silently: if the
profile changed on two machines, it stops and you merge with git.

## The guard

`./self guard` runs as git pre-commit and pre-push hooks (installed by every push and pull) and
again before each upload. It refuses:

- anything from `profile/` or a vault folder,
- any file that is not part of a home (add safe ones to `.openself/allow`),
- an allowed file, such as the README, that quotes your profile: your name, email, phone,
  employers or customers,
- a `profile.age` or vault file that is not encrypted,
- anything but public keys in `.openself/recipients`.

What it cannot read, it refuses. The same check runs on GitHub
(`.github/workflows/guard.yml`) on every push and pull request, with the guard taken from `main`,
so a pull request cannot change what checks it.

## Recipients and trust

The recipients file arrives with every pull, so a key is never used just because it is listed.
Each machine keeps the keys it has approved in its own `.git` folder. A push stops when the file
holds a key this machine has not approved, and lists it. If it is yours (a new machine, say), run
`make trust`; if you do not know it, remove it from `.openself/recipients`. It never got anything
encrypted to it.

On GitHub, a pull request that adds a recipient stays red until you add the label
`new-recipient`, so you know about every new reader.

## Your key

The secret key is the only thing that opens `profile.age`. Lose it and the profile is gone; leak
it and every version you ever pushed can be read. Only decrypting needs it.

openself looks for it in this order:

1. `OPENSELF_IDENTITY=<file>`, for tests and one-off use.
2. The command in `~/.config/openself/identity-command`, which prints the key. With Bitwarden,
   `make bitwarden` sets it to `bw get notes "OpenSelf age key"`, and openself asks for your master
   password when the vault is locked.
3. The macOS Keychain, service `openself`, account `age-identity` (where `make keys` puts it).
4. `~/.config/openself/identity.txt`, readable only by you.

Any password manager with a command line tool works through the `identity-command` file.

## On a new machine

With the key in a password manager (Bitwarden shown):

```sh
git clone --recurse-submodules git@github.com:<you>/<your-repo>.git && cd <your-repo>
brew install age bitwarden-cli && bw login
mkdir -p ~/.config/openself
echo 'bw get notes "OpenSelf age key"' > ~/.config/openself/identity-command
make pull
```

Without one: run `make keys` on the new machine, which makes a key for it. On a machine that can
already decrypt, add the public key it printed to `.openself/recipients`, then `make trust` and
`make push` there. Back on the new machine, `make pull`.

## Lock main

Make GitHub refuse anything on `main` that has not passed the guard there, even from you. With the
[GitHub CLI](https://cli.github.com) (`gh auth login` first), in the home:

```sh
gh api -X PATCH repos/<you>/<your-repo> -F allow_auto_merge=true -F delete_branch_on_merge=true
gh api -X POST repos/<you>/<your-repo>/rulesets --input - <<'JSON'
{"name": "main: pull request with the guard green", "target": "branch", "enforcement": "active",
 "conditions": {"ref_name": {"include": ["~DEFAULT_BRANCH"], "exclude": []}},
 "rules": [{"type": "deletion"}, {"type": "non_fast_forward"},
   {"type": "pull_request", "parameters": {"required_approving_review_count": 0,
     "dismiss_stale_reviews_on_push": false, "require_code_owner_review": false,
     "require_last_push_approval": false, "required_review_thread_resolution": false,
     "allowed_merge_methods": ["merge", "squash"]}},
   {"type": "required_status_checks", "parameters": {"strict_required_status_checks_policy": false,
     "required_status_checks": [{"context": "guard", "integration_id": 15368}]}}]}
JSON
printf '# how make push uploads: through a pull request that merges itself once the guard passes\npush = pull-request\n' > .openself/config
git add .openself/config && git commit -m "Push through pull requests"   # open a PR for this one, main is locked now
```

From then on `make push` sends the snapshot to the branch `openself/snapshot` and opens a pull
request that GitHub merges by itself (a merge commit) once the guard passes; `make pull`
fast-forwards to it. GitHub only offers content rules to organisation repositories, so other
branches cannot be locked the same way: a bad push there is public, but it cannot reach `main`,
and the check turns red.

## Vaults

A vault is a folder of any files (certificates, diplomas, CVs, photos) kept the same way as the
profile: its own git repository, never committed, encrypted into `<name>.age` on push.

```sh
make vault NAME=docs   # creates docs/ and lists it in .openself/config
make push              # encrypts it into docs.age next to profile.age
make vaults            # each vault, and whether it has changes to push
```

Only a vault that changed is uploaded again. GitHub refuses files over 100 MB, so split large
collections into several vaults. Every version stays in the history, so vaults suit documents you
keep, not media that changes every day. OpenVita keeps its CVs in a vault called `cv`.

## What stays visible

A public repository holding only `profile.age` still shows that it exists, when you push, and the
size in 64 KiB steps. Encrypted files stay in public history for good, so a key that leaks later
opens every old version. Keep the key safe, and use a private repository if that matters more to
you than reach.
