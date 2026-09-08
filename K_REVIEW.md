# K Review contract

K · CV Review is the human-in-the-loop review surface for tailored CV packs.

## State

- data/k_requests.csv is the input queue.
- data/k_review_packages.csv is the durable registry of generated packages and their Library links.
- data/k_review_settings.csv stores the complete global K master context, separate from position-specific feedback.
- data/k_review_messages.csv stores the ordered review thread. author=user rows are user feedback; author=ai rows are replies written by the K generator.
- data/k_review_attachments.csv may remain for legacy compatibility, but screenshots are not required by the current review flow.

## Review loop

1. The user opens a package and previews its linked job, CV PDF, CV DOCX and cover letter.
2. The position-specific feedback field starts empty on every new version.
3. The user submits text feedback for that specific position. The app writes a user message and marks the package Revision requested.
4. K consumes the full thread plus the global master context, produces the next CV version, and appends an ai message describing the response and changes.
5. The user replies in the same package thread. No feedback needs to be copied into the general ChatGPT conversation.
6. Older versions remain preserved and the newest version is registered as the current package.

## Rules

- Use MASTER(3) as the sole starting document.
- Preserve the Master formatting exactly; do not redesign.
- Do not invent experience or metrics.
- Keep the PwC energy-sector secondment as a separate Selected Project Experience item when relevant.
- Keep global context out of the position-specific feedback field.
- Handle individual CV work in K Review rather than the general chat.
