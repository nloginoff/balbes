# Canonical user id, linking Telegram ↔ MAX, OpenRouter `user`

See the full Russian guide (with curl examples): [IDENTITY_AND_OPENROUTER_USER.md](../ru/IDENTITY_AND_OPENROUTER_USER.md).

Summary:

- Each **Telegram** and **MAX** external id maps to a **canonical UUID** via `GET /api/v1/identity/resolve`.
- They do **not** auto-merge: the same person chatting in both apps has **two** UUIDs until you **`POST /api/v1/identity/link`** to attach the second channel to the chosen canonical id.
- OpenRouter **`user`** is that UUID for session traffic; service embeddings use **`OPENROUTER_SERVICE_USER`** (default `balbes-service`).
- Optional **`IDENTITY_LINK_SECRET`**: when set, `POST /identity/link` requires header **`X-Balbes-Identity-Link-Secret`**.
