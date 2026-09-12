"""OpsGenome CLI Interface."""


def __getattr__(name: str):
    if name == "cli":
        from opsgenome.cli.main import cli

        return cli
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


__all__ = ["cli"]

