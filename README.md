# ACR Rally Club 0.2.14

A web-based rally club for Assetto Corsa Rally, based on
[ACR Daily](https://github.com/khanhonthetrack/acr-daily). Manage rallies,
championships, divisions and teams in a browser. Players use a Windows launcher
to prepare Rally Weekend, read telemetry and submit official results.

**[Open the club](https://acr-rally-club.onrender.com/)** ·
**[Download the Windows installer](https://github.com/ValtteriPSR/acr-daily/releases/latest/download/ACR-Rally-Club-Setup.exe)**

Rally pages show each special stage in order, with weather, in-game start time
and service before the stage. A compact **Conditions** section shows the actual
Rally Weekend rules and fixed launcher settings.

Administrators can customize the club logo, titles and public Discord invite, edit the car/stage catalog and permanently delete rallies or seasons. Past events are collapsed in an archive. Results update after each stage; telemetry remains provisional until confirmed by the game save. Rally rules can allow breaks at service with private server save backups, or require one sitting.

The website supports Polish and English. Use **PL / EN** in the navigation bar;
the browser remembers your choice. Rally names, nicknames and team names remain
exactly as entered by their authors.

Players sign in through Steam, then choose their club display nickname. The
nickname can be edited under **My profile** without changing account identity,
rally attempts or results. Account access is restored by signing in with the
same Steam account. Steam passwords are entered
only on Steam; the club stores the verified SteamID privately.

The website's launcher button downloads the latest compiled Windows installer
directly from GitHub, without showing the release page.

Configure optional live Discord scoreboards and end-of-rally summaries in the
administrator panel using a text channel webhook. See [Discord setup](docs/DISCORD.md).

## Guides

- [Move to your own hosting](docs/HOSTING.md)
- [Administration and hosting](docs/ADMINISTRATION.md)
- [Player guide](docs/PLAYER-GUIDE.md)
- [Development, testing and releases](docs/DEVELOPMENT.md)

## Hosting

The application is portable: use Docker Compose on a Linux VPS, or the included
container on a managed host. See [Hosting and migration](docs/HOSTING.md) for
setup, secure credential generation, database preservation and domain-specific
Windows builds. Ordinary PHP/FTP hosting needs a separate Python backend.


The deployed application runs on Render Free in Frankfurt, with persistent
PostgreSQL storage on Neon Free. Administrators need no local server, Python,
Docker or Git tools. Players need Windows, the game installed through Steam and
the compiled launcher.

Render suspends idle free services after 15 minutes. The next visit may take
about a minute to load. Accounts and results stay in Neon across restarts.
Free plans have usage limits and do not guarantee uninterrupted availability.
The Neon database is separate from Render's time-limited free database product.

## Repository

`rally-club` is the default application and deployment branch. This repository
is a real fork of ACR Daily; the upstream branch and Git history remain available.
Historical duplicate guides were consolidated into the current guides
above. Previous versions can still be found in Git history.

The server is self-contained. The Windows build downloads six upstream client
modules from a pinned commit and verifies their Git blob hashes before packaging.
The precompiled installer is available in GitHub Releases and through the website.

## License and credits

Original ACR Daily: Copyright (c) 2026 Ngoc Khanh Nguyen, MIT License.
See [LICENSE](LICENSE). Upstream catalog files and client module provenance are
recorded in the build tools and release manifest.
