# IC-Parent

Unofficial [Infinite Campus](https://www.infinitecampus.com/) poller for [Home Assistant](https://www.home-assistant.io/). It logs in as a parent, reads the portal JSON the mobile app uses, and publishes per-student sensors: today's schedule, missing work, due today / tomorrow, recent scores, and recent grades.

This is **not** an Infinite Campus product, **not** a HACS integration, and **not** affiliated with Infinite Campus or any school district. It talks to an undocumented parent-portal API. Districts differ. Microsoft / SSO logins are not supported.

Keep Infinite Campus credentials and your Home Assistant token on the machine that runs the container. Do not commit `secrets.env`.

## What you get

At 06:00 and 18:00 in `TZ` (and once on container start), the poller writes:

| Entity | State | Useful attributes |
|---|---|---|
| `sensor.campus_sync_status` | `ok` / `needs_credentials` / `error` / `no_match` | `last_success`, `kids`, `detail` |
| `sensor.<slug>_schedule_today` | next period, `no school`, or `done` | `periods` (period, time, course, teacher, room) |
| `sensor.<slug>_assignments_missing` | count | `assignments` |
| `sensor.<slug>_assignments_due_today` | count | `assignments` |
| `sensor.<slug>_assignments_due_tomorrow` | count | `assignments` |
| `sensor.<slug>_recent_scores` | count (14-day scored work) | `assignments` |
| `sensor.<slug>_recent_grades` | count (14-day course grades) | `grades` |
| `binary_sensor.<slug>_has_missing` | `on` / `off` | `device_class: problem` |

`<slug>` is a slugified display name (`Sam` → `sam`, `Ann Marie` → `ann_marie`). By default every student on the parent account is published. Set `CAMPUS_KIDS` to limit or rename them.

REST-created sensors disappear after a Home Assistant restart until the next poll. Restart the container or run `python poller.py --once` to refill them.

A Lovelace School view, notify automations, and a more-info period table live under [`examples/`](examples/).

## Repository layout

| Path | Description |
|---|---|
| `poller.py` | Infinite Campus poller. Logs in, reads portal JSON, POSTs Home Assistant states. |
| `Dockerfile` / `docker-compose.yml` | Run the poller next to Home Assistant (`network_mode: host`). |
| `secrets.env.example` | Infinite Campus + Home Assistant credential template. Copy to `secrets.env`. |
| `www/school-schedule.js` | Lovelace more-info period table for `sensor.*_schedule_today`. |
| `examples/` | Sample School dashboard, automations, and HA YAML snippets. |

## Requirements

- Docker with Compose, on the same host as Home Assistant (or any host that can reach HA's REST API)
- An Infinite Campus parent account that uses **local username + password** (no Microsoft / SAML button on the login form)
- A Home Assistant [long-lived access token](https://www.home-assistant.io/docs/authentication/#your-account-profile)

Python 3.13 without Docker also works: `pip install -r requirements.txt`.

## Find your district URL and `appName`

1. Open the Infinite Campus parent login page in a browser.
2. `IC_BASE_URL` is the origin only, for example `https://campus.yourdistrict.edu` — no `/campus/...` path.
3. View source or inspect the login form. The hidden input named `appName` is `IC_DISTRICT`.

Some hosted districts use `https://<id>.infinitecampus.com`. State consortium portals use the same `/campus/verify.jsp` login; the origin and `appName` still come from that page.

## Install

```bash
git clone https://github.com/xmzkjwxp5f-prog/IC-Parent.git
cd IC-Parent
cp secrets.env.example secrets.env
chmod 600 secrets.env
```

Edit `secrets.env`:

```bash
IC_BASE_URL=https://campus.yourdistrict.edu
IC_DISTRICT=your_appName
IC_USERNAME=your_parent_username
IC_PASSWORD=your_parent_password
HA_BASE_URL=http://127.0.0.1:8123
HA_TOKEN=your_long_lived_token
```

Optional:

```bash
# Only publish some students, and set their HA names.
# Left side = Campus first name (case-insensitive). Right side = display name.
CAMPUS_KIDS=alex:Alex,sam:Sam

TZ=America/New_York
CAMPUS_POLL_HOURS=6,18
```

Create a Home Assistant token: profile (your name, lower left) → **Long-lived access tokens** → create. Paste it as `HA_TOKEN`. The token never needs to leave the host that runs this container.

Then:

```bash
docker compose up -d --build
docker compose logs -f
```

`network_mode: host` assumes Home Assistant is on the same machine at `http://127.0.0.1:8123`. If HA is elsewhere, drop `network_mode: host` and set `HA_BASE_URL` to that API (for example `http://homeassistant.local:8123`).

Check `sensor.campus_sync_status` in Developer Tools. You want `ok`. `needs_credentials` means `secrets.env` is incomplete. `no_match` means `CAMPUS_KIDS` did not match any first name on the account (`seen` lists what Campus returned).

`docker compose restart` does **not** reload `env_file`. After changing `secrets.env`:

```bash
docker compose up -d --force-recreate
```

## Home Assistant snippets

1. Copy the period-table script into HA:

   ```bash
   mkdir -p /path/to/homeassistant/config/www/campus-parent
   cp www/school-schedule.js /path/to/homeassistant/config/www/campus-parent/
   ```

2. Merge [`examples/configuration.yaml`](examples/configuration.yaml) into `configuration.yaml` (frontend module + 24-hour stale sensor). Restart Home Assistant.

3. Add the School view from [`examples/school-dashboard.yaml`](examples/school-dashboard.yaml). Swap the sample slugs for yours. For colored missing/score chips, use [`examples/kid-card.md`](examples/kid-card.md).

4. Optional notifies: [`examples/automations.yaml`](examples/automations.yaml). Point `notify.notify` at your phone.

Clicking **Today's Schedule** opens more-info with a period / time / course / teacher / room table, once the frontend module is loaded. Hard-refresh the browser (or force-stop the Companion app) after adding the script.

## Limitations

- **Unofficial API.** Portal JSON can change without notice. There is no vendor support.
- **Local login only.** If the district login page is Microsoft / Google / SAML, this poller cannot sign in.
- **Do not iframe the portal.** Infinite Campus sends `X-Frame-Options: SAMEORIGIN`.
- **Poll sparingly.** Default is twice a day. Do not drop this to every few minutes; districts can lock parent accounts.
- **Not HACS.** This is a Docker sidecar that POSTs HA states. A config-flow integration would be a separate project.
- **SSO, 2FA, and student (not parent) accounts** are untested.

Do not log assignment titles, scores, or student names to public issue trackers. Redact `docker compose logs` before sharing.

## Related projects

- [schwartzpub/ic_parent_api](https://github.com/schwartzpub/ic_parent_api) — Python parent API used by an older HA custom component that publishes raw blobs rather than per-student dashboard sensors.
- [schwartzpub/infinite_campus_hassio](https://github.com/schwartzpub/infinite_campus_hassio) — YAML/custom_component wrapper around that API.

## License

MIT. See [LICENSE](LICENSE).
