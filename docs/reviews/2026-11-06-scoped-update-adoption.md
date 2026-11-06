# Exact product-file adoption during update

Need: previously scoped installations can leave shipped runtime files absent from the vendored manifest. Ordinary updates must continue refusing collisions with owner files. An explicitly selected update may provide an exact plan naming only currently shipped files, the selected home, each existing content hash and each shipped content hash. Validate the full plan before any writes; stale, escaping, duplicated or unshipped entries are refused. No deletion or preservation copy is introduced.

Exact allowed files: `company/runtime/bootstrap.py`, `company/runtime/onboard.py`, `company/__main__.py`, their matching runtime twins, `company/tests/test_update_preservation.py`, and this record. Acceptance includes default collision refusal, exact adoption, preservation and stale-plan refusal, followed by installed-home update verification. Independent acceptance remains separate.

Verification: synthetic tests cover refusal by default, correct hash-bound adoption, stale content and unshipped-path rejection. The selected home's ten previously scoped product files were adopted through a pinned plan, then its ordinary Python updater refreshed the complete shipped runtime without pruning or preservation copies. Current product parity and company behavior checks pass; historical provenance warnings remain explicitly separate.
