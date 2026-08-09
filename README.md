# Professional Dashboard

Personal opportunity intelligence system for discovering, reviewing, and managing jobs and broader professional opportunities.

The first product focus is full-time job sourcing. The application will gradually expand to company monitoring, tenders, consulting/freelance opportunities, expert work, and experimental discovery channels.

## Run locally

```powershell
python -m pip install -r requirements.txt
streamlit run app.py
```

## Deploy

The repository is structured for Streamlit Community Cloud:

- repository: `ORosa10/ProfessionalDashboard`
- branch: `main`
- entry point: `app.py`

Every push to the connected branch will trigger an automatic app update.

Company ratings, contact strength, and notes can be saved from the Streamlit interface directly to
the repository. See [GITHUB_SAVE_SETUP.md](GITHUB_SAVE_SETUP.md) for the one-time setup.

See [PRODUCT_BLUEPRINT.md](PRODUCT_BLUEPRINT.md) for the product direction and [CURRENT_STATE.md](CURRENT_STATE.md) for the current implementation status. The personal SearchProfile is intentionally kept outside the public repository.
