for /f "delims=" %%f in ('dir /b "iTestRepeat*.exe" 2^>nul') do "%%f" --stop
timeout /t 10