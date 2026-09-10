import tomllib


def load_config(path):
    if not path:
        return {}

    with open(
        path,
        "rb",
    ) as file:
        return tomllib.load(
            file
        )


def as_list(value):
    if value is None:
        return []
    if isinstance(value, list):
        return value
    return [value]
