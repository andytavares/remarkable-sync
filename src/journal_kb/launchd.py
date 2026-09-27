import plistlib
from pathlib import Path

LAUNCH_AGENTS = Path.home() / "Library" / "LaunchAgents"


def plists(cfg, executable: str, config_path: str) -> dict[str, bytes]:
    logs = cfg.state_dir / "logs"
    base = [executable, "--config", config_path]

    def job(label: str, command: str, schedule: dict) -> bytes:
        return plistlib.dumps(
            {
                "Label": label,
                "ProgramArguments": [*base, command],
                "StandardOutPath": str(logs / f"{command}.log"),
                "StandardErrorPath": str(logs / f"{command}.err.log"),
                **schedule,
            }
        )

    weekdays = [{"Weekday": d, "Hour": 7, "Minute": 0} for d in range(1, 6)]
    return {
        "com.journal-kb.ingest": job("com.journal-kb.ingest", "run", {"StartInterval": 300}),
        "com.journal-kb.digest": job("com.journal-kb.digest", "digest", {"StartCalendarInterval": weekdays}),
    }
