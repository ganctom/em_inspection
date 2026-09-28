# Installation & Quick Start

`em_inspection` uses [Pixi](https://pixi.sh) to manage Python, C/C++, and linear algebra dependencies reproducibly across platforms.

---

## System Requirements

- **Operating System**: macOS (Apple Silicon `osx-arm64` supported natively via Metal/Accelerate) or Linux (`linux-64`).
- **Memory (RAM)**: 
  - Minimum: 16 GB RAM for interactive inspection.
  - Recommended: 64 GB+ RAM for high-throughput multi-threaded section warping and dense optical flow calculations.
- **Storage**: Fast local NVMe SSD storage recommended for processing directories and DuckDB scratch builds.

---

## 1. Install Pixi

If Pixi is not already installed on your system, install it via the official installer:

=== "macOS / Linux"

    ```bash
    curl -fsSL https://pixi.sh/install.sh | bash
    ```

=== "Homebrew (macOS)"

    ```bash
    brew install pixi
    ```

Verify the installation:
```bash
pixi --version
```

---

## 2. Clone Repository & Setup Environment

Clone the `em_inspection` repository and install all dependencies automatically:

```bash
git clone https://github.com/ganctom/em_inspection.git
cd em_inspection
pixi install
```

Pixi creates an isolated virtual environment containing Python 3.13, JAX, OpenCV, DuckDB, Dash Bootstrap Components, SOFIMA, and all microscopy alignment libraries.

---

## 3. Launching the Interactive Inspector

Start the Dash web application locally:

```bash
pixi run python src/em_inspection/interactive_inspector/index.py
```

Open your web browser and navigate to:
👉 **`http://localhost:8050`** (or `http://<your-machine-ip>:8050` for access across the local lab network).

---

## 4. Useful Pixi Tasks

The project defines standard development tasks in `pyproject.toml`:

=== "Run Unit Tests"

    ```bash
    pixi run test
    ```

=== "Serve Documentation Locally"

    ```bash
    pixi run docs-serve
    ```
    View the live documentation at `http://127.0.0.1:8000`.

=== "Build Documentation"

    ```bash
    pixi run docs-build
    ```

=== "Code Linting & Formatting"

    ```bash
    pixi run lint
    pixi run format
    ```
