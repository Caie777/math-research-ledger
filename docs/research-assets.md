# Retained research artifacts

ledger.assets preserves historical run identity/provenance/retention contracts. ResearchAssetRef identifies run/path/content bytes; matching SHA-256 is not mathematical verification. ResearchAssetManifest links retained scripts/inputs/outputs to research objects. Published identities cannot silently rebaseline, and retention is monotonic.

The unified manifest reads retained assets without restoring an agent. Original run manifests/events/archive provenance remain on disk. Reads do not publish missing manifests. Pure tests cover deterministic identity, tampering, unsafe paths, associations and retention.

New verification contracts use ArtifactRef with raw hash, role, script/output links, environment and scope. No script runner or historical executor is required.
