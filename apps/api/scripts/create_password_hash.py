"""Generate an Argon2id hash for BAYMAX_PASSWORD_HASH without saving the password."""

from __future__ import annotations

from getpass import getpass

from argon2 import PasswordHasher


def main() -> None:
    password = getpass("New Baymax password: ")
    confirmation = getpass("Confirm Baymax password: ")
    if len(password) < 12:
        raise SystemExit("Use a password with at least 12 characters.")
    if password != confirmation:
        raise SystemExit("Passwords do not match.")
    print("\nCopy this Argon2id hash into Render as BAYMAX_PASSWORD_HASH:")
    print(PasswordHasher().hash(password))
    print("\nThe password itself was not written to a file.")


if __name__ == "__main__":
    main()
