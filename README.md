# Parametric_3D_CAD

Parametric bridge modeling app built with pythonOCC and PySide6.

## First-Time Setup

Use Conda for the easiest and most reliable install of pythonOCC.

### 1) Clone and enter the project

macOS/Linux/Windows (PowerShell):

git clone https://github.com/OmPathania21/Parametric_3D_CAD.git
cd paran3d

### 2) Create a fresh environment

macOS/Linux:

conda create -n param3d python=3.11 -y
conda activate param3d

Windows (PowerShell):

conda create -n param3d python=3.11 -y
conda activate param3d

### 3) Install dependencies

conda install -c conda-forge pythonocc-core pyside6 -y

### 4) Run the application

From the repository root:

python param3d/ui_app.py

## Optional: Run the script mode

This builds/exports using bridge_model.py. Add --no-viewer if you do not want the OCC viewer window.

python param3d/bridge_model.py
python param3d/bridge_model.py --no-viewer

## Quick Troubleshooting

- If you see ModuleNotFoundError for OCC or PySide6, your conda environment is not active. Run:

conda activate param3d

- If you already had another environment active, deactivate it first:

conda deactivate
conda activate param3d