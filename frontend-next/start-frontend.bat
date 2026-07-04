@echo off
echo Starting HIVE OS Frontend (Next.js)...
echo.
echo Make sure the HIVE backend is running on port 8000
echo Frontend will be at http://localhost:3000
echo.
node_modules\.bin\next dev --webpack --port 3000
