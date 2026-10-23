# Troubleshooting

## Messages from openself

**`could not get the key … Is Bitwarden unlocked?`**
: Run the command in a terminal, where it asks for your master password, or run
  `export BW_SESSION=$(bw unlock --raw)` first. In the web app, restart it with `make serve`.

**`Bitwarden already has a note named … with a different key`**
: There are two keys. Do not overwrite either; find out which one opens `profile.age`
  (`make pull` with each) first.

**`not encrypting: .openself/recipients has keys this machine has not approved`**
: Someone or something added a key. If it is one of your machines, `make trust`. If you do not know
  it, remove it from `.openself/recipients` and push; it never got anything encrypted to it.

**`openself guard: refusing …`**
: A commit or push would have published something unencrypted or unexpected. Read the list it
  prints and remove that from the commit. Never use `--no-verify`. A file that is safe to publish
  goes in `.openself/allow`, one glob per line.

**`make pull` stops because the profile diverged**
: The profile changed on two machines. Pull never merges silently: go into `profile/`, merge with
  git as usual, then `make push`.

## Common snags

**`openself/` is empty**
: The repository was cloned without `--recurse-submodules`. Run `git submodule update --init`.

**`age: command not found`, or classic keys instead of post-quantum ones**
: Install age 1.3 or newer: `brew install age`, or a release from
  [GitHub](https://github.com/FiloSottile/age/releases).

**`make push` says nothing changed**
: Nothing in the profile, the vaults or the recipients changed since the last upload, so it skips
  it. Every upload is public, so it never pushes an identical file.

**The web app shows "No AI connected"**
: Nothing is watching the requests. Run `make ai` in the home, or `./self assistant watch` in your
  assistant's session. See [Working with an AI assistant](ai.md).

**A lint error after updating OpenSelf**
: A newer version may check something the old one did not. `make check` says what and where;
  `openself fmt` rewrites entries in canonical form.

Still stuck? [Open an issue](https://github.com/mortennordbye/openself/issues). Never paste
profile text, keys or a Bitwarden session into it.
