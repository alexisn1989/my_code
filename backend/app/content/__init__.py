"""Disk-facing loaders for data-driven game content (product spec §5.6).

This is the I/O boundary between content authored as files under `data/`
(scenarios now; policies, events, government rules, technologies, country
templates, and AI personalities from Phase 2+) and the pure parsing/validation
logic in `app.simulation`, which never touches disk itself. See
`app.content.scenarios` for the one loader this session needs.
"""
