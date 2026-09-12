# Examples

Home Assistant snippets for the Infinite Campus poller. They use fictional
students **Alex** (`alex`) and **Sam** (`sam`). Replace those slugs with the
ones the poller creates for your household.

| File | What to do with it |
|---|---|
| `configuration.yaml` | Merge the `frontend.extra_module_url` and `template` binary sensor into your HA `configuration.yaml`. Restart HA. |
| `school-dashboard.yaml` | New Lovelace dashboard, or paste the `school` view into an existing one. |
| `kid-card.md` | Optional colored markdown card. Duplicate once per student; replace `SLUG`. |
| `automations.yaml` | Append to `automations.yaml`, then point `notify.notify` at your phone. |

After an HA restart the REST-created sensors are empty until the next poll. Run
`docker compose restart` (or `python poller.py --once`) to fill them immediately.
