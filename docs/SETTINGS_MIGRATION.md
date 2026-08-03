# Settings migration

Functional settings are immutable Python dataclasses at schema version 2. `ConfigurationService` is the single synchronized read/update/reset boundary and persists atomically. The renderer sends partial validated patches and owns only presentation/layout preferences in local storage.

On first load without a modern runtime file, `ConfigurationLoader` maps legacy Main/Infer/STTN/ProPainter/model sections into version 2, writes the modern file, and preserves the original as `*.legacy-v1-<timestamp>.bak`. There is no runtime compatibility facade. Corrupt modern JSON is moved to a recovery backup and safe defaults load with a warning.

Precedence is: compiled defaults, shipped defaults, modern user file (or one-time legacy migration), environment overrides, explicit runtime overrides.
