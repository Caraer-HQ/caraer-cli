"""Export the published CLI's command/option tree without invoking commands."""
import json
from typer.main import get_command
from caraer_cli.main import app


def tree(command):
    return {'options': sorted({option for param in command.params for option in getattr(param,'opts',[]) + getattr(param,'secondary_opts',[])}),
            'commands': {name:tree(child) for name,child in getattr(command,'commands',{}).items()}}


if __name__=='__main__':
    print(json.dumps(tree(get_command(app)),indent=2))
