# Enable direct saving from Streamlit

The app stores company rating, contact strength, and notes in `data/company_ratings.csv` in this repository.

One-time setup:

1. Create a fine-grained GitHub personal access token.
2. Limit repository access to `ORosa10/ProfessionalDashboard` only.
3. Grant repository permission `Contents: Read and write`; no other write permission is needed.
4. In Streamlit Community Cloud, open the app's **Settings → Secrets** and add:

```toml
[github]
token = "PASTE_THE_FINE_GRAINED_TOKEN_HERE"
```

Never commit the token to the repository. Once this setting is saved, the Companies page shows a **Save feedback to GitHub** button and no download/upload step is needed.
