import pydantic
import yaml

from .config import load_scenario


def validate_scenario_yaml(file_path: str) -> list[str]:
    """Validates scenario YAML and returns schema errors."""
    errors = []
    try:
        load_scenario(file_path)
    except yaml.YAMLError as err:
        errors.append(f"YAML parsing error: {err}")
    except pydantic.ValidationError as err:
        for error in err.errors():
            loc = ".".join(str(l) for l in error["loc"])
            msg = error["msg"]
            errors.append(f"{loc}: {msg}")
    except ValueError as err:
        errors.append(str(err))
    except Exception as err:
        errors.append(f"Unexpected error: {err}")
    return errors
