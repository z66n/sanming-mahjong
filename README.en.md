# Sanming Mahjong

A command-line implementation of Sanming Mahjong (三明麻将), a variant of Fujian Mahjong played with 16 tiles per player.

[简体中文](README.md) | [English](README.en.md)

## Features

- Complete Sanming rules implementation
- Rich console UI with colored tiles
- AI opponents
- Flower tile handling
- Special winning conditions (Heavenly Hand, Three Golds, etc.)
- Cross-platform CLI interface

## Installation

1. Clone the repository:
   ```bash
   git clone https://github.com/z66n/sanming-mahjong.git
   cd sanming-mahjong
   ```

2. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```

## Usage

Run the game:
```bash
python game_loop.py
```

Controls:
- Enter tile numbers to discard
- Follow on-screen prompts for melds and special actions
- Press 'q' to quit

## Rules

Sanming Mahjong is played with:
- 16 tiles per player (vs standard 13)
- Special flower tiles that are drawn from the dead wall
- Unique winning conditions including Heavenly Hand and Gold-related wins
- Dealer rotation with consecutive dealer bonuses

For detailed rules, see [rule_sanming.md](rule_sanming.md).

## Building

To create a standalone executable:
```bash
pip install pyinstaller
pyinstaller smmj.spec
```

The executable will be in the `dist/` directory.

## Requirements

- Python 3.8+
- Rich (for console UI)
- PyInstaller (for building executables)

## License

MIT License