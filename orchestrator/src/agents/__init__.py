# Import all agent subpackages to trigger @register_agent decorators
import src.agents.public_records  # noqa: F401
import src.agents.social_media  # noqa: F401
import src.agents.breach  # noqa: F401
import src.agents.web  # noqa: F401
import src.agents.analysis  # noqa: F401
