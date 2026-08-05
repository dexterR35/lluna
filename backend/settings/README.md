# Settings boundaries

`backend/settings/` contains typed feature settings and user-facing presets.
Persistent application configuration lives separately in
`backend/configuration/`, while model metadata lives in
`backend/models/reference/`.

```text
settings/
├── schemas/model.py   # typed feature/model controls
├── presets.py         # hardware-aware defaults and presets
├── base.py            # shared settings serialization
└── metadata.py        # settings metadata used by the API/UI
```

Use `settings.schemas.model` for all typed feature and model setting schemas.
