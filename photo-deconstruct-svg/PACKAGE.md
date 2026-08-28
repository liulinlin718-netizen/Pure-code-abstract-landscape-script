# Photo Deconstruct SVG package

This package converts JPG, PNG, or WebP photographs into deterministic, editable SVG abstractions. Image analysis runs locally with NumPy and Pillow; it does not call an image model, an LLM, or a network API.

## Install the command-line package

Requires Python 3.10 or newer.

```bash
python3 -m venv .venv
source .venv/bin/activate
python3 -m pip install photo_deconstruct_svg-0.1.0-py3-none-any.whl
```

On Windows PowerShell, activate the environment with `.venv\Scripts\Activate.ps1`.

Convert a photograph:

```bash
photo-deconstruct-svg input.jpg output.svg
```

Validate the SVG and its adjacent analysis file:

```bash
photo-deconstruct-validate output.svg --analysis output.json
```

The wheel records NumPy and Pillow as dependencies. `pip` may download them during the first installation. After installation, conversion is fully offline and consumes no model tokens.

## Use the Skill ZIP without installation

Extract `photo-deconstruct-svg-0.1.0.zip`, install the included requirements, and run the script directly:

```bash
python3 -m pip install -r photo-deconstruct-svg/requirements.txt
python3 photo-deconstruct-svg/scripts/deconstruct_photo.py input.jpg output.svg
python3 photo-deconstruct-svg/scripts/validate_svg.py output.svg --analysis output.json
```

The ZIP also contains `SKILL.md`, agent metadata, and the visual references needed to install or inspect the folder as an Agent Skill.
