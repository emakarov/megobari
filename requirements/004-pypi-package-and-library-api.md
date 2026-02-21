# REQ-004: PyPI Package and Library API

## Problem

Megobari currently only works as a standalone clone-and-configure project.
Configuration requires a `.env` file, and there's no way to use it as a
library inside other Python projects.

## Goals

1. Publish to PyPI so users can `pip install megobari`
2. Support multiple config sources: env vars, `.env` file, CLI args, programmatic
3. Expose a clean library API for embedding in other codebases

## Design

### Configuration priority (highest to lowest)

1. Programmatic (kwargs passed to `MegobariBot()`)
2. CLI arguments (`megobari --bot-token=... --allowed-user=...`)
3. Environment variables (`BOT_TOKEN`, `ALLOWED_USER`)
4. `.env` file (loaded via python-dotenv)

### Library API

```python
from megobari import MegobariBot

bot = MegobariBot(
    bot_token="123:ABC",
    allowed_user="12345",       # user ID or @username
    working_dir="/path/to/project",
)
bot.run()
```

Minimal usage -- just needs token and user:

```python
from megobari import MegobariBot

bot = MegobariBot(
    bot_token="123:ABC",
    allowed_user="@myusername",
)
bot.run()
```

### CLI usage

```bash
# With env vars or .env file
megobari

# With explicit args
megobari --bot-token=123:ABC --allowed-user=12345

# With custom working directory
megobari --cwd /path/to/project
```

### Config class

Replace global variables in config.py with a `Config` dataclass:

```python
@dataclass
class Config:
    bot_token: str
    allowed_user_id: int | None = None
    allowed_username: str | None = None
    working_dir: str = field(default_factory=os.getcwd)
    sessions_dir: Path | None = None  # defaults to .megobari/sessions

    @classmethod
    def from_env(cls) -> Config: ...

    @classmethod
    def from_args(cls, args) -> Config: ...
```

### PyPI metadata

- Package name: `megobari`
- Entry point: `megobari` CLI command (already configured)
- License: MIT
- Python: >=3.10
- Keywords: telegram, claude, bot, assistant

## Implementation notes

- Config must remain backward compatible -- existing `.env` setups keep working
- The library API should not require `.env` or env vars at all
- `bot.py` and `claude_bridge.py` must accept Config instead of importing globals
- Discovery mode (no ALLOWED_USER) should still work for CLI usage
