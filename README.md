# em_inspection

[![Tests](https://github.com/ganctom/em_inspection/actions/workflows/test.yml/badge.svg)](https://github.com/ganctom/em_inspection/actions/workflows/test.yml)
[![Docs](https://github.com/ganctom/em_inspection/actions/workflows/docs.yml/badge.svg)](https://ganctom.github.io/em_inspection/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

A Python application for interactive inspection, coarse offset estimation, and processing of **Serial Block-Face Electron Microscopy (SBEM)** datasets.

---

## 🌟 Features

- 🔬 **SBEM Dataset Parsing**: High-performance parsing and alignment verification for electron microscopy section datasets.
- ⚡ **Interactive Inspection**: Modern Dash-based dashboard for interactive visualization of section overlaps and tiles.
- 📐 **Coarse & Fine Alignment**: Automated coarse offset calculation and outlier filtering.
- 🛠️ **Pixi Managed Environment**: Fast, reproducible Conda & PyPI dependency management via [Pixi](https://pixi.sh).

---

## 🚀 Quick Start

### Prerequisites

Install `pixi` (if you haven't already):
```bash
curl -fsSL https://pixi.sh/install.sh | bash
```

### Installation

Clone the repository and install dependencies automatically:
```bash
git clone https://github.com/ganctom/em_inspection.git
cd em_inspection
pixi install
```

### Running Tests

Run the test suite using `pixi`:
```bash
pixi run test
```

### Running the Documentation Locally

Serve the MkDocs documentation site:
```bash
pixi run docs-serve
```

---

## 📖 Documentation

For detailed manuals, tutorials, and API reference, visit our online documentation:
👉 **[https://ganctom.github.io/em_inspection/](https://ganctom.github.io/em_inspection/)**

---

## 📄 License

This project is licensed under the [MIT License](LICENSE).
