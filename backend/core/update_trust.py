"""Pinned trust root for release manifests.

Set this to the base64-encoded raw 32-byte Ed25519 public key before publishing
the first auto-updating release. The private key belongs only in the protected
GitHub release environment.
"""

UPDATE_PUBLIC_KEY_B64 = ""
