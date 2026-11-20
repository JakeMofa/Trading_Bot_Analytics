"""One-shot, operator-only provisioning for the PP Storage archive Auth user.

This command never runs in an application container or during deployment.
An uncertain POST leaves a private stage for manual reconciliation; re-running
the command cannot create a second identity with the same staged credential.
"""

import argparse
import json
import os
from pathlib import Path
import re
import secrets
import stat
import urllib.error
import urllib.request
import uuid


PROJECT_REF = "xttdqeimdujweijxcuro"
ADMIN_URL = f"https://{PROJECT_REF}.supabase.co/auth/v1/admin/users"
IDENTITIES = {
    "archive": ("pp_storage_archive", "supabase_auth"),
    "history-reader": ("pp_storage_history_reader", "history_reader"),
}
ORIGIN = "pp-live-pp"
TRIAL_ORIGIN = "pp-live-pp-trial-20261119-01"
SECOND_TRIAL_ORIGIN = "pp-live-pp-trial-20261119-02"
THIRD_TRIAL_ORIGIN = "pp-live-pp-trial-20261119-03"
SUPPORTED_ORIGINS = (ORIGIN, TRIAL_ORIGIN, SECOND_TRIAL_ORIGIN, THIRD_TRIAL_ORIGIN)


class ProvisionError(RuntimeError):
    """A sanitized STOP reason; never includes an HTTP body or credential."""


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, request, fp, code, msg, headers, newurl):
        return None


def _read_admin_key(path):
    descriptor = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
    try:
        info = os.fstat(descriptor)
        if (not stat.S_ISREG(info.st_mode) or info.st_nlink != 1
                or info.st_uid not in (os.geteuid(), 0)
                or stat.S_IMODE(info.st_mode) & 0o077 or info.st_size > 8192):
            raise ProvisionError("unsafe admin key file")
        key = os.read(descriptor, 8193).strip()
        if not key or len(key) > 8192 or any(c in key for c in b"\r\n\x00 \t"):
            raise ProvisionError("invalid admin key file")
        return key
    finally:
        os.close(descriptor)


def _validate_email(email):
    if (not isinstance(email, str) or len(email) > 254 or email != email.lower()
            or not re.fullmatch(r"[a-z0-9.!#$%&'*+/=?^_`{|}~-]+@[a-z0-9](?:[a-z0-9.-]*[a-z0-9])?", email)
            or ".." in email):
        raise ProvisionError("invalid dedicated email")
    return email


def _private_parent(path):
    if path.is_symlink():
        raise ProvisionError("unsafe output parent")
    info = path.stat()
    if (not stat.S_ISDIR(info.st_mode) or info.st_uid != os.geteuid()
            or stat.S_IMODE(info.st_mode) & 0o077):
        raise ProvisionError("unsafe output parent")


def _write_private(directory, name, content):
    descriptor = os.open(directory / name, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o400)
    try:
        os.fchmod(descriptor, 0o400)
        remaining = memoryview(content)
        while remaining:
            written = os.write(descriptor, remaining)
            if written <= 0:
                raise OSError("private file write made no progress")
            remaining = remaining[written:]
        os.fsync(descriptor)
    except BaseException:
        # A short write or failed sync must never leave a usable partial
        # credential or UID file behind.
        try:
            (directory / name).unlink()
        except OSError:
            pass
        raise
    finally:
        os.close(descriptor)


def _replace_status(directory, value):
    # A status file contains no credentials; atomic replacement documents the
    # transition from staged to created or unconfirmed.
    temporary = directory / ".status-new"
    _write_private(directory, temporary.name, (value + "\n").encode())
    try:
        os.replace(temporary, directory / "status")
    finally:
        temporary.unlink(missing_ok=True)
    dirfd = os.open(directory, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        os.fsync(dirfd)
    finally:
        os.close(dirfd)


def _discard_stage(directory, prefix="supabase_auth"):
    for name in (f"{prefix}_email", f"{prefix}_password", f"{prefix}_uid", "status", ".status-new"):
        (directory / name).unlink(missing_ok=True)
    directory.rmdir()


def _default_request(payload, key):
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), NoRedirect())
    request = urllib.request.Request(
        ADMIN_URL, data=payload, method="POST",
        headers={"apikey": key.decode("ascii"), "Authorization": "Bearer " + key.decode("ascii"),
                 "Content-Type": "application/json", "Accept": "application/json"},
    )
    try:
        with opener.open(request, timeout=10) as response:
            return response.status, response.read(16385)
    except urllib.error.HTTPError as error:
        # Do not read, log, or surface response bodies; even error bodies can
        # contain submitted user fields.
        with error:
            return error.code, b""


def provision(*, project_ref, email, admin_key_file, output_dir, execute=False, request_fn=None, purpose="archive", origin=ORIGIN):
    if not execute:
        raise ProvisionError("explicit --execute required")
    if project_ref != PROJECT_REF:
        raise ProvisionError("wrong Supabase project")
    if purpose not in IDENTITIES:
        raise ProvisionError("unsupported PP Storage identity purpose")
    if origin not in SUPPORTED_ORIGINS:
        raise ProvisionError("unsupported exact PP Storage origin")
    role, prefix = IDENTITIES[purpose]
    email = _validate_email(email)
    output_dir = Path(output_dir)
    if output_dir.exists() or output_dir.is_symlink():
        raise ProvisionError("identity stage already exists; reconcile it before any retry")
    _private_parent(output_dir.parent)
    key = _read_admin_key(admin_key_file)
    password = secrets.token_hex(32)
    metadata = {"tradebot_role": role, "tradebot_origin": origin}
    payload = json.dumps({"email": email, "password": password,
                          "email_confirm": True, "app_metadata": metadata},
                         separators=(",", ":")).encode()
    os.mkdir(output_dir, 0o700)
    os.chmod(output_dir, 0o700)
    attempted = False
    try:
        _write_private(output_dir, f"{prefix}_email", (email + "\n").encode())
        _write_private(output_dir, f"{prefix}_password", (password + "\n").encode())
        # Persist the uncertain state *before* the external POST. If Auth
        # succeeds but the response or subsequent local write fails, a restart
        # cannot mistake this stage for one that was never submitted.
        _replace_status(output_dir, "UNCONFIRMED_CREATE")
        try:
            attempted = True
            status, body = (request_fn or _default_request)(payload, key)
        except Exception:
            raise ProvisionError("Auth request outcome uncertain; reconcile staged identity") from None
        if status in (400, 401, 403, 404, 409, 422):
            _discard_stage(output_dir, prefix)
            raise ProvisionError("Auth Admin rejected identity creation; no automatic retry")
        if status not in (200, 201) or len(body) > 16384:
            raise ProvisionError("Auth request outcome uncertain; reconcile staged identity")
        try:
            result = json.loads(body)
            uid = str(uuid.UUID(result["id"]))
            if (uid != result["id"] or result["email"] != email
                    or any(result["app_metadata"][k] != v for k, v in metadata.items())):
                raise ValueError("binding mismatch")
        except (ValueError, KeyError, TypeError, AttributeError):
            raise ProvisionError("Auth response binding uncertain; reconcile staged identity") from None
        _write_private(output_dir, f"{prefix}_uid", (uid + "\n").encode())
        _replace_status(output_dir, "CREATED_VERIFIED_RESPONSE")
        return uid
    except ProvisionError:
        raise
    except Exception:
        # Before POST, remove incomplete local staging. After POST, the server
        # outcome may be uncertain and the credential must remain reconcilable.
        if not attempted:
            try:
                _discard_stage(output_dir, prefix)
            except OSError:
                pass
        elif output_dir.exists():
            try:
                _replace_status(output_dir, "UNCONFIRMED_CREATE")
            except OSError:
                # Keep the private stage even if the local disk itself failed.
                # The command still stops and never authorizes installation.
                pass
        raise ProvisionError("identity stage requires operator reconciliation") from None


def main():
    parser = argparse.ArgumentParser(description="Provision dedicated PP Storage Auth identity")
    parser.add_argument("--project-ref", required=True)
    parser.add_argument("--email", required=True)
    parser.add_argument("--purpose", choices=sorted(IDENTITIES), default="archive")
    parser.add_argument("--origin", choices=SUPPORTED_ORIGINS, default=ORIGIN)
    parser.add_argument("--admin-key-file", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--execute", action="store_true")
    args = parser.parse_args()
    try:
        uid = provision(project_ref=args.project_ref, email=args.email,
                        admin_key_file=args.admin_key_file, output_dir=args.output_dir,
                        execute=args.execute, purpose=args.purpose, origin=args.origin)
    except (ProvisionError, OSError, UnicodeError):
        raise SystemExit("PP Auth identity provisioning STOP; inspect private stage and reconcile") from None
    print(uid)


if __name__ == "__main__":
    main()
