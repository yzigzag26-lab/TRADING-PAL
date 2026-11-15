"""Generate an Argon2id hash for BAYMAX_PASSWORD_HASH without saving the password."""

from __future__ import annotations

from getpass import getpass

from argon2 import PasswordHasher


def main() -> None:
    password = getpass("New Baymax password: ")
    confirmation = getpass("Confirm Baymax password: ")
    if not password:
        raise SystemExit("Password must not be empty.")
    if password != confirmation:
        raise SystemExit("Passwords do not match.")
    print("\nCopy this Argon2id hash into Render as BAYMAX_PASSWORD_HASH:")
    print(PasswordHasher().hash(password))
    print("\nThe password itself was not written to a file.")


if __name__ == "__main__":
    main()
