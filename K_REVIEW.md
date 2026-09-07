# K Review contract

`K · CV Review` is the human-in-the-loop review surface for tailored CV packs.

## State

- `data/k_requests.csv` remains the input queue; it may be cleared after generation.
- `data/k_review_packages.csv` is the durable registry of generated packages and their Library links.
- `data/k_review_settings.csv` stores the global K context, separate from position-specific feedback.
- `data/k_review_messages.csv` stores the ordered review thread. `author=user` rows are user feedback; `author=ai` rows are replies written by the K generator.
- `data/k_review_attachments.csv` maps screenshots to messages. The image bytes live under `data/k_review_attachments/<package>/`.

## Review loop

1. The user opens a package and previews its linked outputs.
2. The position-specific text box starts empty on every new version.
3. The user submits text and/or screenshots. The app writes a `user` message, stores attachments, and marks the request `Revision requested`.
4. The K generator consumes the full thread plus global context, produces the next CV version, and appends an `ai` message describing the response and changes.
5. The user replies in the same package thread. No feedback needs to be copied into the ChatGPT conversation.

Screenshots are committed to the public repository because the current v0 persistence layer is GitHub-backed. Do not upload unrelated private documents or sensitive material that should not be public.
