import os
from dataclasses import dataclass


@dataclass(frozen=True)
class Settings:
    livekit_url: str
    livekit_api_key: str
    livekit_api_secret: str
    agent_name: str

    @classmethod
    def from_env(cls) -> "Settings":
        values = {
            "livekit_url": os.environ.get("LIVEKIT_URL", ""),
            "livekit_api_key": os.environ.get("LIVEKIT_API_KEY", ""),
            "livekit_api_secret": os.environ.get("LIVEKIT_API_SECRET", ""),
        }
        missing = [
            env_name
            for env_name, value in (
                ("LIVEKIT_URL", values["livekit_url"]),
                ("LIVEKIT_API_KEY", values["livekit_api_key"]),
                ("LIVEKIT_API_SECRET", values["livekit_api_secret"]),
            )
            if not value
        ]
        if missing:
            raise RuntimeError(f"Missing required settings: {', '.join(missing)}")
        return cls(**values, agent_name=os.environ.get("LIVEKIT_AGENT_NAME", ""))
