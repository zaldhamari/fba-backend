#!/bin/bash
set -e

echo "Setting up FBA Assistant..."

python3 -m venv venv
source venv/bin/activate

pip install -r requirements.txt
playwright install chromium

echo ""
echo "✅ Setup complete!"
echo ""
echo "To start the app:"
echo "  source venv/bin/activate"
echo "  python3 run.py"
echo ""
echo "Then open http://localhost:8000 in your browser."
