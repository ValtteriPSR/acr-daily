# Discord notifications

This integration posts as **ACR Rally Club** using an incoming channel webhook. It requires no bot token, Developer Portal application or local program. A Discord server invite alone cannot authorize posting.

1. In Discord, create or choose an ordinary text channel such as `rally-results`.
2. Open **Edit Channel → Integrations → Webhooks → New Webhook**. You need permission to manage webhooks.
3. Name it **ACR Rally Club** and copy its webhook URL.
4. Open the ACR Rally Club administrator panel and find **Discord notifications**. Paste the URL, enable notifications, choose live standings, summaries and Polish or English, then save.
5. Click **Send test message**. Check both the channel and the delivery status in the panel.

The webhook URL is a secret: enter it only in the administrator panel. Leaving its input blank keeps the saved value. Unchecking **Enable Discord notifications** stops automatic posting. Only rally display nicknames, stage progress, participant statuses and rally times are posted; Steam identities, login tokens and recovery codes are never included.

One live scoreboard per rally is updated when its data changes, normally within about 15 seconds. Telemetry times are explicitly unverified; official times become available after the launcher submits a complete, validated rally. Tables show the first 20 participants and link to the complete website standings. A separate summary is posted after the closing time and after remaining active/verification attempts finish or time out. Registered drivers who did not start remain marked as registered. Historical rallies closed before the integration was enabled are not reposted.

Settings, message IDs and pending retries persist in the application database across deployments. Rate limits delay retries without blocking gameplay. If a live scoreboard was deleted, it is recreated after the retry delay. Use one server process/instance for the notifier; multi-instance hosting requires a single designated notifier. Set `ACR_DISCORD_NOTIFIER=0` on every other instance.

On Render Free, the process can sleep while the website has no activity. During sleep no notifications are sent. The persisted state is processed on the next wake-up, including summaries due during sleep. A paid always-running service is needed for guaranteed background execution at the scheduled closing time.

The download button now resolves the configured GitHub repository to `releases/latest/download/ACR-Rally-Club-Setup.exe`. Keep that asset name stable and build the latest release for the website's public origin. Whether a save dialog opens or the download saves automatically is controlled by the participant's browser.
