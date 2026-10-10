# Administration and hosting

Club: https://acr-rally-club.onrender.com/

Render service: https://dashboard.render.com/web/srv-db5588ad0e5s73e8d0f0

Workspace: **Mateusz's workspace**. Service: **acr-rally-club**.
Deployment branch: **rally-club**. Database: **acr_club** on Neon.

## First administrator sign-in

1. Sign in to Render and open the service's **Environment** tab.
2. Reveal `ACR_ADMIN_PATH`, `ADMIN_HTTP_PASSWORD` and `ACR_ADMIN_KEY`.
3. Append `ACR_ADMIN_PATH` to the club's base URL. The value starts with `/`.
4. In the browser authentication dialog, use username `admin` and the value of
   `ADMIN_HTTP_PASSWORD` as the password.
5. On the administrator page, enter the value of `ACR_ADMIN_KEY`.

Keep these values private. Do not commit them, include them in client builds or
send them in public messages. The private panel has both HTTP authentication and
an application session. API routes require both layers as well.

## Create a championship

1. Open the season panel and create a season with opening and closing dates.
2. Set overall, division and Power Stage points, plus the team scoring mode.
3. Create rallies in the rally panel, choosing a car class, allowed cars, stages,
   weather, start times, service stops, damage and penalty rules.
4. Add the rallies to the season calendar in the required order and save it.
5. Create divisions and teams if needed. Assign registered club members.
6. Check the public rally and standings pages before announcing the event.

Dates use a fixed **UTC+2** offset. This differs from Polish winter time by one
hour. The supported limits are 100 rallies per season, 10 divisions and up to
10 drivers per team; rallies have 2–40 stages.

Players can register before a rally opens. RUN is available during the event
window and requires a division assignment when the season uses divisions.
Configuration and assignments are locked once relevant attempts have begun.
Points are finalized after the rally closes. DNF earns zero points, including
Power Stage points. The default Power Stage awards are 5, 4, 3, 2, 1, based on the
final stage's official time including penalties.

## Hosting and updates

To move to another provider, use the [hosting and migration guide](HOSTING.md).
The two administrator credentials are different: browser password first,
application key second. Incognito is useful for troubleshooting cached browser
credentials; it is not required for normal use.


The Render container runs the Python backend on loopback port 8790 behind Caddy,
which binds Render's public port. Render provides HTTPS. Club data is stored in
Neon PostgreSQL, rather than in the container's temporary filesystem.

Required environment variables:

| Variable | Purpose |
| --- | --- |
| `DATABASE_URL` | Pooled Neon PostgreSQL connection string |
| `ACR_ADMIN_PATH` | Private administrator route |
| `ACR_ADMIN_KEY` | Application administrator sign-in key |
| `ADMIN_HTTP_PASSWORD` | HTTP authentication password for `admin` |
| `ACR_GATEWAY_SECRET` | Trusted reverse-proxy secret |
| `ACR_LAUNCHER_DOWNLOAD_URL` | Public GitHub Release installer URL |
| `ACR_MIN_LAUNCHER_VERSION` | Minimum accepted client version, currently `0.2.0` (legacy 6.3.1 remains compatible) |

`RENDER_EXTERNAL_URL` supplies the public origin automatically.

After updating `rally-club`, check **Deploys** in Render. If no deployment starts,
select **Manual Deploy → Deploy latest commit**. Automatic deployments require
a working repository integration, not just the Auto-Deploy setting.
Do not restart or update the service during a live rally: active attempts may be
interrupted. A launcher change requires a separate Windows build and release.

Free services may sleep, restart or be suspended when quotas are exhausted.
Monitor usage in Render and Neon. Keep private database backups before major
changes; Neon's free instant-restore window is short. Do not run two club server
instances against the same database. Never expose the backend port directly.
