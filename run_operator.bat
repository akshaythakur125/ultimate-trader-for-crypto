@echo off
echo ========================================================================
echo  Starting Daily Operator...
echo ========================================================================
python -m production_replay.operator
if %ERRORLEVEL% NEQ 0 (
    echo.
    echo  WARNING: Operator encountered an error. Check output above.
)
echo.
echo ========================================================================
echo  Operator finished. Press any key to close.
echo ========================================================================
pause >nul
