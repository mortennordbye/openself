"""Encrypted sharing of a profile: a personal repository ("home") holds the profile only as one
encrypted file, so it can be public, and any machine with the key can get the full profile back.

    home/
      .openself/recipients   age public keys that may decrypt, one per line
      profile/               the profile, decrypted, its own git repository (never committed here)
      profile.age            the whole profile repository, every version, encrypted

push: git bundle of the profile (all history), padded to a multiple of 64 KiB, encrypted with age
to every recipient, committed as profile.age. pull: the reverse, then a fast-forward of profile/.
GitHub sees one opaque file and when it changes; no names, no number of entries.

The secret key never touches the disk: on macOS it lives in the Keychain, elsewhere in a file only
the user can read (~/.config/openself/identity.txt), and it reaches age through a pipe. It can also
come from a password manager: a command in ~/.config/openself/identity-command (or the environment
variable OPENSELF_IDENTITY_COMMAND) that prints the key, such as `bw get notes "OpenSelf age key"`.
"""

import getpass
import json
import os
import platform
import shutil
import subprocess
import tempfile
import threading

from . import guard, history, index, model

PAD = 64 * 1024
SNAPSHOT_BRANCH = "openself/snapshot"
KEYCHAIN = ("openself", "age-identity")
IDENTITY_FILE = os.path.expanduser("~/.config/openself/identity.txt")
IDENTITY_COMMAND_FILE = os.path.expanduser("~/.config/openself/identity-command")


class SyncError(Exception):
    pass


def run(args, **kw):
    r = subprocess.run(args, capture_output=True, **kw)
    if r.returncode:
        err = r.stderr.decode() if isinstance(r.stderr, bytes) else r.stderr
        raise SyncError(f"{args[0]}: {err.strip() or 'failed'}")
    return r.stdout


def need_age():
    for tool in ("age", "age-keygen"):
        if not shutil.which(tool):
            raise SyncError(f"{tool} is not installed (https://age-encryption.org; brew install age)")


def is_home(path):
    return os.path.isdir(os.path.join(path, ".openself"))


def find_home(start="."):
    """The home folder at or above start, or None."""
    p = os.path.abspath(start)
    while True:
        if is_home(p):
            return p
        parent = os.path.dirname(p)
        if parent == p:
            return None
        p = parent


def recipients_file(home):
    return os.path.join(home, ".openself", "recipients")


def setting(home, key, default=""):
    """A `key = value` line in .openself/config, committed so every machine does the same."""
    try:
        with open(os.path.join(home, ".openself", "config"), encoding="utf-8") as f:
            for line in f:
                k, sep, v = line.partition("=")
                if sep and k.strip() == key and not k.lstrip().startswith("#"):
                    return v.strip()
    except OSError:
        pass
    return default


def recipients(home):
    try:
        with open(recipients_file(home), encoding="utf-8") as f:
            return [l.strip() for l in f if l.strip() and not l.lstrip().startswith("#")]
    except OSError:
        return []


# ---- the secret key --------------------------------------------------------------------------

def mac():
    return platform.system() == "Darwin" and shutil.which("security")


def identity_command():
    """The command that prints the key, when one is set (environment first, then the config file)."""
    cmd = os.environ.get("OPENSELF_IDENTITY_COMMAND", "").strip()
    if not cmd and os.path.exists(IDENTITY_COMMAND_FILE):
        with open(IDENTITY_COMMAND_FILE, encoding="utf-8") as f:
            cmd = next((l.strip() for l in f if l.strip() and not l.lstrip().startswith("#")), "")
    return cmd


def bw_session(interactive=None):
    """A Bitwarden session for this process: BW_SESSION if set, else unlock now, asking for the master
    password on the terminal. The session lives in this process's environment only."""
    if os.environ.get("BW_SESSION"):
        return os.environ["BW_SESSION"]
    if not shutil.which("bw"):
        raise SyncError("the Bitwarden CLI (bw) is not installed: brew install bitwarden-cli")
    st = subprocess.run(["bw", "status"], capture_output=True, text=True)
    state = (json.loads(st.stdout or "{}").get("status") if st.returncode == 0 else "") or ""
    if state == "unauthenticated":
        raise SyncError("log in to Bitwarden first: bw login")
    if interactive is None:
        import sys
        interactive = sys.stdin.isatty()
    if not interactive:
        raise SyncError("Bitwarden is locked: run `export BW_SESSION=$(bw unlock --raw)` in the shell that runs openself")
    pw = getpass.getpass("Bitwarden master password: ")
    env = dict(os.environ, OPENSELF_BW_PASSWORD=pw)
    r = subprocess.run(["bw", "unlock", "--raw", "--passwordenv", "OPENSELF_BW_PASSWORD"], capture_output=True, text=True, env=env)
    if r.returncode != 0 or not r.stdout.strip():
        raise SyncError("could not unlock Bitwarden (wrong password?)")
    os.environ["BW_SESSION"] = r.stdout.strip()
    return os.environ["BW_SESSION"]


def run_identity_command(cmd):
    if cmd.split()[0] == "bw":
        bw_session()
    r = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=120)
    key = "".join(l.strip() + "\n" for l in r.stdout.splitlines() if l.strip().startswith("AGE-SECRET-KEY"))
    if r.returncode != 0 or not key:
        why = (r.stderr or "").strip().splitlines()[-1:] or ["it printed no AGE-SECRET-KEY line"]
        hint = ""
        if cmd.split()[0] == "bw":
            hint = " Is Bitwarden unlocked? Run `export BW_SESSION=$(bw unlock --raw)` in the shell that runs openself."
        raise SyncError(f"could not get the key from `{cmd}`: {why[0]}.{hint}")
    return key


def find_identity():
    """(secret key text, where it is), or (None, None) when this machine has none."""
    cmd = "" if os.environ.get("OPENSELF_IDENTITY") else identity_command()
    if cmd:
        return run_identity_command(cmd), f"the command `{cmd}`"
    return local_identity()


def local_identity():
    """The key from the environment's file, the Keychain or identity.txt, without the command."""
    if os.environ.get("OPENSELF_IDENTITY"):
        path = os.environ["OPENSELF_IDENTITY"]
        if not os.path.exists(path):
            return None, None
        with open(path, encoding="utf-8") as f:
            return f.read(), path
    if mac():
        r = subprocess.run(["security", "find-generic-password", "-s", KEYCHAIN[0], "-a", KEYCHAIN[1], "-w"],
                           capture_output=True, text=True)
        if r.returncode == 0 and r.stdout.strip():
            return r.stdout.strip() + "\n", "macOS Keychain (service openself)"
    if os.path.exists(IDENTITY_FILE):
        with open(IDENTITY_FILE, encoding="utf-8") as f:
            return f.read(), IDENTITY_FILE
    return None, None


def identity():
    return find_identity()[0]


def has_identity():
    """Whether this machine has a key, without asking a password manager for it (status polls often)."""
    if not os.environ.get("OPENSELF_IDENTITY") and identity_command():
        return True
    return identity() is not None


def new_key():
    """A post-quantum hybrid key when this age supports it (1.3+), a classic X25519 key otherwise."""
    r = subprocess.run(["age-keygen", "-pq"], capture_output=True)
    return r.stdout.decode() if r.returncode == 0 else run(["age-keygen"]).decode()


def public_key(secret):
    return run(["age-keygen", "-y"], input=secret.encode()).decode().split()[0]


def store_identity(secret):
    if mac():
        # Through `security -i` on stdin, so the key never shows up in the process list.
        key = "".join(l for l in secret.splitlines() if l.startswith("AGE-SECRET-KEY"))
        run(["security", "-i"], input=f'add-generic-password -U -s {KEYCHAIN[0]} -a {KEYCHAIN[1]} -w "{key}"\n'.encode())
        return "macOS Keychain (service openself)"
    os.makedirs(os.path.dirname(IDENTITY_FILE), exist_ok=True)
    fd = os.open(IDENTITY_FILE, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        f.write(secret)
    return IDENTITY_FILE


def keys_init(home=None):
    """Make this machine's key if it has none (post-quantum hybrid), and add its public key to the
    home's recipients. Returns (public key, where the secret is, created)."""
    need_age()
    secret, where = find_identity()
    created = secret is None
    if created:
        secret = new_key()
        where = store_identity(secret)
    pub = public_key(secret)
    if home:
        # The recipients file is public: label the key with a date, not the user or machine name.
        start_trust(home)
        add_recipient(home, pub, f"key added {model.today()}")
        trust(home, [pub])
    return pub, where, created


BW_ITEM = "OpenSelf age key"


def bw(args, **kw):
    r = subprocess.run(["bw", *args], capture_output=True, text=True, **kw)
    return r.stdout if r.returncode == 0 else None


def to_bitwarden(home=None, item=BW_ITEM, interactive=None):
    """Put this machine's key in Bitwarden as a secure note and make openself read it from there.
    Checks that what Bitwarden returns is the same key before anything else changes. Returns
    (public key, where the key was before, whether a note was created)."""
    need_age()
    secret, where = local_identity()
    pub_cmd = identity_command()
    if secret is None and pub_cmd:
        secret, where = find_identity()
    if secret is None:
        raise SyncError("no key on this machine to move: run `openself keys` first")
    pub = public_key(secret)
    if home and pub not in recipients(home):
        raise SyncError("this key is not in .openself/recipients; it would not open profile.age")
    bw_session(interactive)
    existing = bw(["get", "notes", item])
    created = False
    if existing and existing.strip():
        if public_key(existing) != pub:
            raise SyncError(f"Bitwarden already has a note named «{item}» with a different key; rename one of them")
    else:
        template = json.loads(bw(["get", "template", "item"]) or "{}")
        template.update(type=2, name=item, notes=secret.strip(), secureNote={"type": 0}, login=None)
        encoded = bw(["encode"], input=json.dumps(template))
        if not encoded or bw(["create", "item"], input=encoded.strip()) is None:
            raise SyncError("Bitwarden would not save the note")
        created = True
        bw(["sync"])
    back = bw(["get", "notes", item]) or ""
    if not back.strip() or public_key(back) != pub:
        raise SyncError("the key read back from Bitwarden does not match; nothing else was changed")
    os.makedirs(os.path.dirname(IDENTITY_COMMAND_FILE), exist_ok=True)
    with open(IDENTITY_COMMAND_FILE, "w", encoding="utf-8") as f:
        f.write(f'# OpenSelf reads its age key from this command (no secret here).\nbw get notes "{item}"\n')
    return pub, where, created


def remove_keychain_copy():
    if mac():
        return subprocess.run(["security", "delete-generic-password", "-s", KEYCHAIN[0], "-a", KEYCHAIN[1]],
                              capture_output=True).returncode == 0
    return False


def trusted_file(home):
    """The recipients this machine has approved. Inside .git, so no pull or checkout can change it."""
    if history.is_repo(home):
        path = git_out(home, "rev-parse", "--git-path", "openself-trusted-recipients")
        if path:
            return path if os.path.isabs(path) else os.path.join(home, path)
    return os.path.join(home, ".openself", "trusted")


def trusted(home):
    """The approved keys, or None when this machine has not started a list yet."""
    try:
        with open(trusted_file(home), encoding="utf-8") as f:
            return {l.strip() for l in f if l.strip() and not l.lstrip().startswith("#")}
    except OSError:
        return None


def trust(home, keys):
    have = trusted(home) or set()
    new = [k for k in keys if k not in have]
    path = trusted_file(home)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "a", encoding="utf-8") as f:
        if not have:
            f.write("# age public keys this machine has approved as recipients of profile.age (openself trust)\n")
        f.writelines(k + "\n" for k in new)
    return new


def start_trust(home):
    """The first time on a machine, approve the recipients as they are. Returns how many."""
    if trusted(home) is None and recipients(home):
        return len(trust(home, recipients(home)))
    return 0


def untrusted(home):
    """[(key, label)] in .openself/recipients that this machine has not approved."""
    have = trusted(home) or set()
    out, label = [], ""
    try:
        with open(recipients_file(home), encoding="utf-8") as f:
            lines = f.read().splitlines()
    except OSError:
        return []
    for line in lines:
        s = line.strip()
        if s.startswith("#"):
            label = s.lstrip("# ")
        elif s:
            if s not in have:
                out.append((s, label))
            label = ""
    return out


def short_key(key):
    return f"{key[:16]}...{key[-8:]}"


def add_recipient(home, pub, label=""):
    os.makedirs(os.path.join(home, ".openself"), exist_ok=True)
    if pub in recipients(home):
        return False
    with open(recipients_file(home), "a", encoding="utf-8") as f:
        f.write((f"# {label}\n" if label else "") + pub + "\n")
    return True


def with_identity(args, **kw):
    """Run age with the secret key on a pipe (/dev/fd/N) instead of a file."""
    secret = identity()
    if secret is None:
        raise SyncError("no key on this machine: run `openself keys init`, or copy the key from your backup")
    r, w = os.pipe()

    def feed():
        with os.fdopen(w, "w") as f:
            f.write(secret)
    t = threading.Thread(target=feed)
    t.start()
    try:
        return run(args[:1] + ["-i", f"/dev/fd/{r}"] + args[1:], pass_fds=(r,), **kw)
    finally:
        os.close(r)
        t.join()


# ---- push and pull ---------------------------------------------------------------------------
# A home encrypts the profile and any number of vaults: more folders of any files (documents,
# images, PDFs, CVs), each its own git repository, listed in .openself/config as `vaults = cv`.
# Each becomes <name>.age, in the same format as profile.age, so every version of every file
# travels encrypted and the public repository sees only opaque files and when they change.

MAX_FILE = 95 * 1024 * 1024  # GitHub refuses files over 100 MB


def profile_dir(home):
    return os.path.join(home, "profile")


def config_text(home):
    try:
        with open(os.path.join(home, ".openself", "config"), encoding="utf-8") as f:
            return f.read()
    except OSError:
        return ""


def vaults(home):
    """The vault names this home declares, in order."""
    return guard.vault_names(config_text(home))


def folders(home):
    """[(name, folder)]: the profile first, then each vault."""
    return [("profile", profile_dir(home))] + [(v, os.path.join(home, v)) for v in vaults(home)]


def add_vault(home, name):
    """Declare a vault: a git repository in <home>/<name>/ (kept out of the home's git), listed in
    .openself/config so every machine pulls it too. Returns its folder."""
    if not guard.VAULT_NAME.fullmatch(name) or name in guard.NOT_VAULTS:
        raise SyncError(f"bad vault name {name!r}: lower-case letters, digits, - and _, not profile")
    path = os.path.join(home, name)
    if os.path.exists(path) and os.listdir(path) and not history.is_repo(path):
        raise SyncError(f"{path} exists and is not a git repository; move it aside or make it one first")
    names = vaults(home)
    if name not in names:
        text = config_text(home)
        lines = [l for l in text.splitlines() if l.partition("=")[0].strip() != "vaults"]
        lines.append("vaults = " + ", ".join(names + [name]))
        with open(os.path.join(home, ".openself", "config"), "w", encoding="utf-8") as f:
            f.write("\n".join(lines).lstrip("\n") + "\n")
    gi = os.path.join(home, ".gitignore")
    lines = open(gi, encoding="utf-8").read().splitlines() if os.path.exists(gi) else []
    if f"/{name}/" not in lines:
        with open(gi, "a", encoding="utf-8") as f:
            f.write(("\n" if lines and lines[-1] else "") + f"# The decrypted vault never goes in this repository; only {name}.age does.\n/{name}/\n")
    if not history.is_repo(path):
        os.makedirs(path, exist_ok=True)
        run(["git", "init", "-q", "-b", "main", path])
    if not head(path):
        history.git(path, "add", "-A")
        history.git(path, "commit", "-q", "--allow-empty", "-m", history.message(name, "vault created", "tool"))
    return path


def pushed_file(home):
    return os.path.join(home, ".openself", "pushed")  # local only: what was last encrypted, per folder


def recipients_hash(home):
    import hashlib
    with open(recipients_file(home), "rb") as f:
        return hashlib.sha256(f.read()).hexdigest()[:16]


def pushed(home):
    """{name: 'commit recipients-hash'} last encrypted on this machine. An old one-line file is the profile's."""
    out = {}
    try:
        with open(pushed_file(home)) as f:
            for line in f:
                parts = line.split()
                if len(parts) == 2:
                    out["profile"] = " ".join(parts)
                elif len(parts) == 3:
                    out[parts[0]] = " ".join(parts[1:])
    except OSError:
        pass
    return out


def push_stamp(home, folder=None):
    """What would be encrypted now for one folder: its commit and the recipients."""
    return f"{head(folder or profile_dir(home))} {recipients_hash(home)}"


def head(repo):
    r = subprocess.run(["git", "-C", repo, "rev-parse", "HEAD"], capture_output=True, text=True)
    return r.stdout.strip() if r.returncode == 0 else ""


def status(home):
    p = profile_dir(home)
    done = pushed(home)
    vs = {}
    for name, path in folders(home)[1:]:
        vs[name] = {"here": history.is_repo(path), "encrypted": os.path.exists(os.path.join(home, f"{name}.age")),
                    "unpushed": bool(head(path)) and head(path) != done.get(name, "").split(" ")[0]}
    return {"home": home, "profile": os.path.isfile(os.path.join(p, model.MANIFEST)),
            "encrypted": os.path.exists(os.path.join(home, "profile.age")),
            "recipients": len(recipients(home)), "key": has_identity(),
            "unpushed": (bool(head(p)) and head(p) != done.get("profile", "").split(" ")[0]) or any(v["unpushed"] for v in vs.values()),
            "vaults": vs, "remote": bool(git_out(home, "remote"))}


def git_out(repo, *args):
    r = subprocess.run(["git", "-C", repo, *args], capture_output=True, text=True)
    return r.stdout.strip() if r.returncode == 0 else ""


MAGIC = b"OPENSELF-BUNDLE-1\n"


def pack(bundle_bytes):
    """Magic, length, the git bundle, then zeros up to a multiple of 64 KiB, so the encrypted size
    only says roughly how big the folder is."""
    head = MAGIC + len(bundle_bytes).to_bytes(8, "big")
    body = head + bundle_bytes
    return body + bytes(-len(body) % PAD)


def unpack(data, name="profile"):
    if not data.startswith(MAGIC):
        raise SyncError(f"{name}.age does not contain an OpenSelf bundle")
    n = int.from_bytes(data[len(MAGIC):len(MAGIC) + 8], "big")
    return data[len(MAGIC) + 8:len(MAGIC) + 8 + n]


def encrypt_folder(home, name, path):
    """Bundle the folder's repository (every version) and encrypt it to <name>.age. Returns its size."""
    with tempfile.TemporaryDirectory() as tmp:
        bundle = os.path.join(tmp, f"{name}.bundle")
        run(["git", "-C", path, "bundle", "create", bundle, "--all"])
        with open(bundle, "rb") as f:
            data = pack(f.read())
    enc = run(["age", "-R", recipients_file(home)], input=data)
    if len(enc) > MAX_FILE:
        raise SyncError(f"{name}.age would be {len(enc) // (1024 * 1024)} MB; GitHub refuses files over 100 MB. "
                        f"Split {name}/ into more vaults, or remove large files from its history")
    out = os.path.join(home, f"{name}.age")
    with open(out + ".tmp", "wb") as f:
        f.write(enc)
    os.replace(out + ".tmp", out)
    return len(enc)


def push(home, commit=True, upload=True, force=False):
    """Encrypt the profile into profile.age and each vault into <name>.age, commit them (and git push
    when there is a remote). A folder that did not change since the last push, with the same
    recipients, is not encrypted again, since every upload is visible. Nothing changed: nothing done."""
    need_age()
    p = profile_dir(home)
    if not history.is_repo(p):
        raise SyncError(f"no profile repository in {p}")
    rcpt = recipients(home)
    if not rcpt:
        raise SyncError("no recipients: run `openself keys init` first")
    if history.is_repo(home):
        skipped = guard.install(home)
        if skipped:
            raise SyncError("the guard hooks cannot be installed, another tool's hook is in the way: "
                            + ", ".join(skipped) + ". Remove it (openself puts its own in place) and push again")
    start_trust(home)
    new = untrusted(home)
    if new:
        raise SyncError("not encrypting: .openself/recipients has keys this machine has not approved:\n  "
                        + "\n  ".join(short_key(k) + (f" ({l})" if l else "") for k, l in new)
                        + "\nIf they are yours (a new machine), run `openself trust`. If not, remove them.")
    index.write_all(p)
    history.commit(p, history.message("profile", "changes before an encrypted push", "tool"))
    done, sizes, missing = pushed(home), {}, []
    for name, path in folders(home):
        if name != "profile":
            if not history.is_repo(path):
                missing.append(name)  # declared, but not here: pull it first; its .age stays as it is
                continue
            history.commit(path, history.message(name, "changes before an encrypted push", "tool"))
            if not head(path):
                continue
        out = os.path.join(home, f"{name}.age")
        if not force and os.path.exists(out) and done.get(name) == push_stamp(home, path):
            continue
        sizes[name] = encrypt_folder(home, name, path)
        done[name] = push_stamp(home, path)
    with open(pushed_file(home), "w") as f:
        f.write("".join(f"{n} {v}\n" for n, v in done.items()))
    size = sizes.get("profile", os.path.getsize(os.path.join(home, "profile.age")) if os.path.exists(os.path.join(home, "profile.age")) else 0)
    result = {"ok": True, "size": size, "encrypted": sizes, "missing": missing, "commit": None, "uploaded": False}
    if not sizes:
        result["unchanged"] = True
    if commit and history.is_repo(home):
        # Only these files: anything else that happens to be staged stays out of the snapshot.
        own = [f"{n}.age" for n, _ in folders(home) if os.path.exists(os.path.join(home, f"{n}.age"))]
        own += [x for x in (".openself/recipients", ".openself/config", ".gitignore") if os.path.exists(os.path.join(home, x))]
        subprocess.run(["git", "-C", home, "add", *own], check=True)
        if subprocess.run(["git", "-C", home, "diff", "--cached", "--quiet", "--", *own]).returncode:
            what = "Encrypted profile snapshot" if list(sizes) in ([], ["profile"]) else "Encrypted snapshot: " + ", ".join(sizes)
            run(["git", "-C", home, "commit", "-q", "-m", what, "--", *own])
            result["commit"] = git_out(home, "rev-parse", "--short", "HEAD")
            result.pop("unchanged", None)
        if upload and git_out(home, "remote") and (result["commit"] or not result.get("unchanged")):
            bad = guard.unpushed(home)
            if bad:
                raise SyncError("refusing to upload, the home repository would publish:\n  " + "\n  ".join(bad))
            if setting(home, "push") == "pull-request":
                result["pr"] = push_pull_request(home)
            else:
                run(["git", "-C", home, "push", "-q"])
            result["uploaded"] = True
    return result


def push_pull_request(home):
    """Push to a branch and open a pull request that GitHub merges by itself once its required
    checks pass, for a home whose main branch takes no direct pushes. A merge commit, not a
    squash, so every machine can fast-forward to it."""
    if not shutil.which("gh"):
        raise SyncError("pushing through a pull request needs the GitHub CLI: brew install gh, then gh auth login")
    base = git_out(home, "rev-parse", "--abbrev-ref", "HEAD") or "main"
    run(["git", "-C", home, "push", "-q", "--force", "origin", f"HEAD:refs/heads/{SNAPSHOT_BRANCH}"])

    def gh(*args):
        return run(["gh", *args], cwd=home).decode().strip()
    url = gh("pr", "list", "--head", SNAPSHOT_BRANCH, "--state", "open", "--json", "url", "--jq", ".[0].url")
    if not url:
        url = gh("pr", "create", "--base", base, "--head", SNAPSHOT_BRANCH, "--title", "Encrypted profile snapshot",
                 "--body", "Made by `openself push`. GitHub merges it once the guard check passes.").splitlines()[-1]
    gh("pr", "merge", url, "--auto", "--merge")
    return url


def pull_folder(home, name, path):
    """Decrypt <name>.age and clone or fast-forward the folder to it. Never merges by itself."""
    src = os.path.join(home, f"{name}.age")
    with open(src, "rb") as f:
        plain = with_identity(["age", "-d"], input=f.read())
    with tempfile.TemporaryDirectory() as tmp:
        bundle = os.path.join(tmp, f"{name}.bundle")
        with open(bundle, "wb") as f:
            f.write(unpack(plain, name))
        if not history.is_repo(path):
            if os.path.exists(path) and os.listdir(path):
                raise SyncError(f"{path} exists and is not a git repository")
            run(["git", "clone", "-q", bundle, path])
            run(["git", "-C", path, "remote", "remove", "origin"])
            return {"ok": True, "result": "cloned", "head": head(path)[:7]}
        run(["git", "-C", path, "fetch", "-q", bundle, "+refs/heads/*:refs/remotes/encrypted/*"])
    branch = git_out(path, "rev-parse", "--abbrev-ref", "HEAD") or "main"
    theirs = git_out(path, "rev-parse", f"refs/remotes/encrypted/{branch}")
    mine = head(path)
    if not theirs or theirs == mine:
        return {"ok": True, "result": "up to date", "head": mine[:7]}
    if subprocess.run(["git", "-C", path, "merge-base", "--is-ancestor", theirs, mine]).returncode == 0:
        return {"ok": True, "result": "local is newer; push it", "head": mine[:7]}
    if subprocess.run(["git", "-C", path, "merge-base", "--is-ancestor", mine, theirs]).returncode != 0:
        raise SyncError(f"{name} was changed on two machines; merge refs/remotes/encrypted/"
                        f"{branch} in {path} with git, then push")
    if git_out(path, "status", "--porcelain"):
        history.commit(path, history.message(name, "changes before a pull", "tool"))
        if subprocess.run(["git", "-C", path, "merge-base", "--is-ancestor", head(path), theirs]).returncode != 0:
            raise SyncError(f"there are local changes in {name}/; push or commit them before pulling")
    run(["git", "-C", path, "merge", "-q", "--ff-only", theirs])
    return {"ok": True, "result": "updated", "head": head(path)[:7]}


def pull(home, download=True):
    """Fetch the newest encrypted files, decrypt them and fast-forward profile/ and every vault.
    The result is the profile's, with each vault's under "vaults"."""
    need_age()
    if history.is_repo(home):
        guard.install(home)
    start_trust(home)  # before the download, so keys that arrive with it need approval
    if download and git_out(home, "remote"):
        run(["git", "-C", home, "pull", "-q", "--ff-only"])
    if not os.path.exists(os.path.join(home, "profile.age")):
        raise SyncError("there is no profile.age to pull")
    result = pull_folder(home, "profile", profile_dir(home))
    result["vaults"] = {}
    for name, path in folders(home)[1:]:
        if os.path.exists(os.path.join(home, f"{name}.age")):
            result["vaults"][name] = pull_folder(home, name, path)
        else:
            result["vaults"][name] = {"ok": True, "result": "not pushed yet", "head": head(path)[:7]}
    return result
