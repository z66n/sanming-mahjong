# 三明麻将 (Sanming Mahjong)

三明麻将的命令行实现，三明麻将是福建麻将的一种变体，每位玩家使用16张牌。

[简体中文](README.md) | [English](README.en.md)

## 功能特性

- 完整的三明规则实现
- 丰富的控制台UI，支持彩色牌面显示
- AI对手
- 花牌处理机制
- 特殊胡牌条件（天胡、三金倒等）
- 跨平台命令行界面

## 安装

1. 克隆仓库：
   ```bash
   git clone https://github.com/z66n/sanming-mahjong.git
   cd sanming-mahjong
   ```

2. 安装依赖：
   ```bash
   pip install -r requirements.txt
   ```

## 使用方法

运行游戏：
```bash
python game_loop.py
```

控制方式：
- 输入牌的序号来出牌
- 根据屏幕提示进行吃碰杠等操作
- 按 'q' 退出游戏

## 规则说明

三明麻将的特点：
- 每位玩家16张牌（标准为13张）
- 特殊的花牌，从死墙补牌
- 独特的胡牌条件，包括天胡和金牌相关胡牌
- 庄家轮转，连庄奖励机制

详细规则请参考 [rule_sanming.md](rule_sanming.md)。

## 构建

创建独立可执行文件：
```bash
pip install pyinstaller
pyinstaller smmj.spec
```

可执行文件将在 `dist/` 目录中生成。

## 系统要求

- Python 3.8+
- Rich（控制台UI库）
- PyInstaller（构建可执行文件）

## 许可证

MIT License