#!/bin/bash
set -e

echo "Installing Manim for macOS using Miniconda..."

# Ensure a conda installation exists
if ! command -v conda &> /dev/null; then
    echo "Conda not found on PATH. Checking for Miniconda in default locations..."
    if [ -f "$HOME/miniconda3/bin/conda" ]; then
        CONDA_BIN="$HOME/miniconda3/bin/conda"
        CONDA_PATH="$HOME/miniconda3"
    elif [ -f "$HOME/opt/miniconda3/bin/conda" ]; then
        CONDA_BIN="$HOME/opt/miniconda3/bin/conda"
        CONDA_PATH="$HOME/opt/miniconda3"
    else
        echo "=================================================="
        echo "Conda could not be found."
        echo "Manim on macOS requires complex dependencies (cairo, ffmpeg, pango) that are"
        echo "best managed via conda-forge to avoid homebrew permission issues."
        echo ""
        echo "Please install Miniconda first:"
        echo "  curl -O https://repo.anaconda.com/miniconda/Miniconda3-latest-MacOSX-arm64.sh"
        echo "  bash Miniconda3-latest-MacOSX-arm64.sh -b -p \$HOME/miniconda3"
        echo "=================================================="
        exit 1
    fi
else
    CONDA_BIN=$(command -v conda)
    CONDA_PATH=$(dirname $(dirname $CONDA_BIN))
fi

ENV_NAME="techfig_manim"

echo "Creating new conda environment: $ENV_NAME (Python 3.11)..."
$CONDA_BIN create -y -n $ENV_NAME python=3.11

echo "Activating environment and installing Manim via conda-forge..."
source "$CONDA_PATH/bin/activate" $ENV_NAME
conda install -y -c conda-forge manim

echo "Installing techfig into the new environment..."
# Assuming script is run from project root, or install current directory
cd "$(dirname "$0")/.."
pip install -e "."

echo ""
echo "✅ Manim installation complete!"
echo "To use the Manim fallback engine, simply activate the environment:"
echo "  source $CONDA_PATH/bin/activate $ENV_NAME"
echo ""
echo "Try running:"
echo "  techfig animation --input examples/manim_spec.json --output test.mp4"
