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
the user can read (~/.config/openself/identity.txt), and it reaches age through a pipe.
"""

import os
import platform
import shutil
import subprocess
import tempfile
import threading

from . import history, index, model

PAD = 64 * 1024
KEYCHAIN = ("openself", "age-identity")
IDENTITY_FILE = os.path.expanduser("~/.config/openself/identity.txt")


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


def find_identity():
    """(secret key text, where it is), or (None, None) when this machine has none."""
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


def head(repo):
    r = subprocess.run(["git", "-C", repo, "rev-parse", "HEAD"], capture_output=True, text=True)
    return r.stdout.strip() if r.returncode == 0 else ""


def status(home):
    p = profile_dir(home)
    pushed = ""
    if os.path.exists(pushed_file(home)):
        with open(pushed_file(home)) as f:
            pushed = f.read().strip()
    return {"home": home, "profile": os.path.isfile(os.path.join(p, model.MANIFEST)),
            "encrypted": os.path.exists(os.path.join(home, "profile.age")),
            "recipients": len(recipients(home)), "key": identity() is not None,
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


def push(home, commit=True, upload=True):
    """Encrypt the profile into profile.age and commit it (and git push when there is a remote)."""
    need_age()
    p = profile_dir(home)
    if not history.is_repo(p):
        raise SyncError(f"no profile repository in {p}")
    rcpt = recipients(home)
    if not rcpt:
        raise SyncError("no recipients: run `openself keys init` first")
    index.write_all(p)
    history.commit(p, history.message("profile", "changes before an encrypted push", "tool"))
    with tempfile.TemporaryDirectory() as tmp:
        bundle = os.path.join(tmp, "profile.bundle")
        run(["git", "-C", p, "bundle", "create", bundle, "--all"])
        with open(bundle, "rb") as f:
            data = pack(f.read())
    out = os.path.join(home, "profile.age")
    enc = run(["age", "-R", recipients_file(home)], input=data)
    tmp_out = out + ".tmp"
    with open(tmp_out, "wb") as f:
        f.write(enc)
    os.replace(tmp_out, out)
    with open(pushed_file(home), "w") as f:
        f.write(head(p) + "\n")
    result = {"ok": True, "size": len(enc), "commit": None, "uploaded": False}
    if commit and history.is_repo(home):
        subprocess.run(["git", "-C", home, "add", "profile.age", ".openself/recipients", ".gitignore"], check=True)
        if subprocess.run(["git", "-C", home, "diff", "--cached", "--quiet"]).returncode:
            run(["git", "-C", home, "commit", "-q", "-m", "Encrypted profile snapshot"])
            result["commit"] = git_out(home, "rev-parse", "--short", "HEAD")
        if upload and git_out(home, "remote"):
            run(["git", "-C", home, "push", "-q"])
            result["uploaded"] = True
    return result


def pull(home, download=True):
    """Fetch the newest profile.age, decrypt it and fast-forward profile/ to it."""
    need_age()
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
