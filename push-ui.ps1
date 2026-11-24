$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
python "$scriptDir\..\push_gui.py" --app admin @args
