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
        add_recipient(home, pub, f"key added {model.today()}")
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

def profile_dir(home):
    return os.path.join(home, "profile")


def pushed_file(home):
    return os.path.join(home, ".openself", "pushed")  # local only: the profile commit last encrypted


def push_stamp(home):
    """What was last encrypted: the profile commit and the recipients. Unchanged means no new upload."""
    import hashlib
    with open(recipients_file(home), "rb") as f:
        return f"{head(profile_dir(home))} {hashlib.sha256(f.read()).hexdigest()[:16]}"


def head(repo):
    r = subprocess.run(["git", "-C", repo, "rev-parse", "HEAD"], capture_output=True, text=True)
    return r.stdout.strip() if r.returncode == 0 else ""


def status(home):
    p = profile_dir(home)
    pushed = ""
    if os.path.exists(pushed_file(home)):
        with open(pushed_file(home)) as f:
            pushed = f.read().strip().split(" ")[0]
    return {"home": home, "profile": os.path.isfile(os.path.join(p, model.MANIFEST)),
            "encrypted": os.path.exists(os.path.join(home, "profile.age")),
            "recipients": len(recipients(home)), "key": has_identity(),
            "unpushed": bool(head(p)) and head(p) != pushed, "remote": bool(git_out(home, "remote"))}


def git_out(repo, *args):
    r = subprocess.run(["git", "-C", repo, *args], capture_output=True, text=True)
    return r.stdout.strip() if r.returncode == 0 else ""


MAGIC = b"OPENSELF-BUNDLE-1\n"


def pack(bundle_bytes):
    """Magic, length, the git bundle, then zeros up to a multiple of 64 KiB, so the encrypted size
    only says roughly how big the profile is."""
    head = MAGIC + len(bundle_bytes).to_bytes(8, "big")
    body = head + bundle_bytes
    return body + bytes(-len(body) % PAD)


def unpack(data):
    if not data.startswith(MAGIC):
        raise SyncError("profile.age does not contain an OpenSelf profile")
    n = int.from_bytes(data[len(MAGIC):len(MAGIC) + 8], "big")
    return data[len(MAGIC) + 8:len(MAGIC) + 8 + n]


def push(home, commit=True, upload=True, force=False):
    """Encrypt the profile into profile.age and commit it (and git push when there is a remote).
    Does nothing when neither the profile nor the recipients changed since the last push, since
    every upload is visible."""
    need_age()
    p = profile_dir(home)
    if not history.is_repo(p):
        raise SyncError(f"no profile repository in {p}")
    rcpt = recipients(home)
    if not rcpt:
        raise SyncError("no recipients: run `openself keys init` first")
    guard.install(home)
    index.write_all(p)
    history.commit(p, history.message("profile", "changes before an encrypted push", "tool"))
    out = os.path.join(home, "profile.age")
    if not force and os.path.exists(out) and os.path.exists(pushed_file(home)):
        with open(pushed_file(home)) as f:
            if f.read().strip() == push_stamp(home):
                return {"ok": True, "size": os.path.getsize(out), "commit": None, "uploaded": False, "unchanged": True}
    with tempfile.TemporaryDirectory() as tmp:
        bundle = os.path.join(tmp, "profile.bundle")
        run(["git", "-C", p, "bundle", "create", bundle, "--all"])
        with open(bundle, "rb") as f:
            data = pack(f.read())
    enc = run(["age", "-R", recipients_file(home)], input=data)
    tmp_out = out + ".tmp"
    with open(tmp_out, "wb") as f:
        f.write(enc)
    os.replace(tmp_out, out)
    with open(pushed_file(home), "w") as f:
        f.write(push_stamp(home) + "\n")
    result = {"ok": True, "size": len(enc), "commit": None, "uploaded": False}
    if commit and history.is_repo(home):
        subprocess.run(["git", "-C", home, "add", "profile.age", ".openself/recipients", ".gitignore"], check=True)
        if subprocess.run(["git", "-C", home, "diff", "--cached", "--quiet"]).returncode:
            run(["git", "-C", home, "commit", "-q", "-m", "Encrypted profile snapshot"])
            result["commit"] = git_out(home, "rev-parse", "--short", "HEAD")
        if upload and git_out(home, "remote"):
            bad = guard.check(home)
            if bad:
                raise SyncError("refusing to upload, the home repository would publish:\n  " + "\n  ".join(bad))
            run(["git", "-C", home, "push", "-q"])
            result["uploaded"] = True
    return result


def pull(home, download=True):
    """Fetch the newest profile.age, decrypt it and fast-forward profile/ to it."""
    need_age()
    if history.is_repo(home):
        guard.install(home)
    if download and git_out(home, "remote"):
        run(["git", "-C", home, "pull", "-q", "--ff-only"])
    src = os.path.join(home, "profile.age")
    if not os.path.exists(src):
        raise SyncError("there is no profile.age to pull")
    with open(src, "rb") as f:
        tar_bytes = with_identity(["age", "-d"], input=f.read())
    p = profile_dir(home)
    with tempfile.TemporaryDirectory() as tmp:
        bundle = os.path.join(tmp, "profile.bundle")
        with open(bundle, "wb") as f:
            f.write(unpack(tar_bytes))
        if not history.is_repo(p):
            if os.path.exists(p) and os.listdir(p):
                raise SyncError(f"{p} exists and is not a profile repository")
            run(["git", "clone", "-q", bundle, p])
            run(["git", "-C", p, "remote", "remove", "origin"])
            return {"ok": True, "result": "cloned", "head": head(p)[:7]}
        run(["git", "-C", p, "fetch", "-q", bundle, "+refs/heads/*:refs/remotes/encrypted/*"])
    branch = git_out(p, "rev-parse", "--abbrev-ref", "HEAD") or "main"
    theirs = git_out(p, "rev-parse", f"refs/remotes/encrypted/{branch}")
    mine = head(p)
    if not theirs or theirs == mine:
        return {"ok": True, "result": "up to date", "head": mine[:7]}
    if subprocess.run(["git", "-C", p, "merge-base", "--is-ancestor", theirs, mine]).returncode == 0:
        return {"ok": True, "result": "local is newer; push it", "head": mine[:7]}
    if subprocess.run(["git", "-C", p, "merge-base", "--is-ancestor", mine, theirs]).returncode != 0:
        raise SyncError("the profile was changed on two machines; merge refs/remotes/encrypted/"
                        f"{branch} in {p} with git, then push")
    if git_out(p, "status", "--porcelain"):
        history.commit(p, history.message("profile", "changes before a pull", "tool"))
        if subprocess.run(["git", "-C", p, "merge-base", "--is-ancestor", head(p), theirs]).returncode != 0:
            raise SyncError("there are local changes; push or commit them before pulling")
    run(["git", "-C", p, "merge", "-q", "--ff-only", theirs])
    return {"ok": True, "result": "updated", "head": head(p)[:7]}
