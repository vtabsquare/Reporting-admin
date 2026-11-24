$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
python "$scriptDir\push_admin.py" @args
if ($LASTEXITCODE -ne 0) {
    exit $LASTEXITCODE
}
