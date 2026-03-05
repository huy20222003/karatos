#!/usr/bin/env bash
set -e

echo "🦂 Karatos V2.6 Automated Installer"
echo "==================================="

# Check prerequisites
command -v git >/dev/null 2>&1 || { echo >&2 "Error: git is required but it's not installed. Aborting."; exit 1; }
command -v python3 >/dev/null 2>&1 || { echo >&2 "Error: python3 is required but it's not installed. Aborting."; exit 1; }

INSTALL_DIR="${KARATOS_DIR:-karatos}"

if [ -d "$INSTALL_DIR" ]; then
    echo "Directory '$INSTALL_DIR' already exists. Please remove it or set a different KARATOS_DIR."
    exit 1
fi

echo "[1/4] Cloning repository..."
git clone https://github.com/huy20222003/karatos.git "$INSTALL_DIR"
cd "$INSTALL_DIR"

echo "[2/4] Setting up Python virtual environment..."
python3 -m venv venv
source venv/bin/activate || source venv/Scripts/activate

echo "[3/4] Installing dependencies..."
pip install --upgrade pip
if [ -f "requirements.txt" ]; then
    pip install -r requirements.txt
else
    echo "Warning: requirements.txt not found. Skipping dependency installation."
fi

echo "[4/4] Setting up default configuration..."
if [ -f ".env.example" ] && [ ! -f ".env" ]; then
    cp .env.example .env
    echo "Created .env file from .env.example"
fi

echo ""
echo "✅ Karatos installed successfully in $PWD!"
echo ""
echo "To get started:"
echo "  cd $INSTALL_DIR"
echo "  source venv/bin/activate  # Or 'venv\\Scripts\\activate' on Windows"
echo "  python main.py"
echo ""
echo "To launch the Dashboard GUI:"
echo "  python main.py --gui"
echo ""
echo "Make sure to configure your API keys in the .env file or via the Dashboard."
