# Installation Guide

## Using Pixi (Recommended)

`em_inspection` uses [Pixi](https://pixi.sh) to manage Python and C++ dependencies reproducibly.

1. Install Pixi:
   ```bash
   curl -fsSL https://pixi.sh/install.sh | bash
   ```

2. Clone and set up environment:
   ```bash
   git clone https://github.com/ganctom/em_inspection.git
   cd em_inspection
   pixi install
   ```

3. Run tasks:
   ```bash
   pixi run test
   ```
