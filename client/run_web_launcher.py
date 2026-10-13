"""Windows EXE: --install registers URL scheme, else starts ticket-based monitoring."""
import sys

def self_test():
    """Exercise dependencies INSIDE the finished Windows EXE, no network/game/GUI."""
    from acr_daily import settings, saveslot, rallyweekend, telemetry, names, rallyclub
    from club_local import web_launch, monitor, integrity, web_install, launcher_control, trace_sender
    launcher_control.self_test(web_launch.parse_launch_link)
    from club_local import read_only_memory, memory_diagnostics
    read_only_memory.self_test()
    if __import__('os').name == 'nt':
        assert memory_diagnostics.snapshot(), 'Windows memory counters unavailable'
    assert callable(trace_sender.TraceSender)
    assert callable(launcher_control.serve_connection)
    assert callable(settings.load)
    assert callable(saveslot.game_running)
    assert callable(rallyweekend.read_weekend)
    assert callable(rallyclub.apply_club_weekend)
    assert callable(web_launch.configured_server)
    assert callable(monitor.baseline_counts)
    return 0


if __name__ == '__main__':
    if len(sys.argv) == 2 and sys.argv[1] == '--self-test':
        try:
            sys.exit(self_test())
        except Exception:
            import traceback
            traceback.print_exc()
            sys.exit(1)
    elif len(sys.argv) == 1 or (len(sys.argv) == 2 and sys.argv[1] == '--install'):
        from club_local.web_install import install, installed_message
        try:
            from club_local.version import VERSION
            target, cfg = install(sys.executable)
            installed_message('ACR Rally Club — zainstalowano',
                f'Launcher V{VERSION} zainstalowany:\n{target}\n\nSerwer:\n{cfg}\n\nMożesz kliknąć RUN na stronie klubu.')
        except Exception as exc:
            installed_message('ACR Rally Club — błąd',str(exc))
            sys.exit(1)
    elif len(sys.argv) == 2:
        from club_local.web_launch import main
        try:
            main(sys.argv[1])
        except Exception as exc:
            from club_local.web_install import installed_message
            installed_message('ACR Rally Club — błąd',str(exc))
            sys.exit(1)
    else:
        from club_local.web_install import installed_message
        installed_message('ACR Rally Club',
            'Uruchom launcher ze strony klubu (przycisk RUN).')
