# SerialStudio · 嵌入式串口调试助手

面向嵌入式单片机（STM32 / ESP32 / 51 / Arduino 等）开发的现代桌面端串口调试工具，基于 **Python + PySerial + PyWebView (Edge WebView2)** 构建，支持深色/浅色主题切换、高分屏实时波形示波器、常用校验自动追加以及快捷指令管理。

## 核心特性

- **一体化无边框现代界面**：支持深色/浅色双主题切换，自定义标题栏与窗口控制按钮，自适应深色下拉菜单。
- **完备的串口参数与流控**：支持常见及任意自定义波特率（`9600` ~ `2000000+`）、数据位、校验位、停止位、流控（`RTS/CTS`、`XON/XOFF`），以及独立的 **DTR / RTS** 引脚控制。
- **数据监视终端**：
  - ASCII / HEX 十六进制收发切换
  - 毫秒级时间戳、RX / TX / 系统消息语义高亮
  - 实时关键字过滤、暂停接收、导出 `.txt` 日志、RX/TX 字节统计
  - `Ctrl + Enter` 快捷发送、`↑ / ↓` 历史指令翻页、定时自动发送
- **自动校验追加**：发送时可选自动追加 `CRC16-Modbus`、`Sum8`、`XOR8` 校验及行尾结束符（`\r\n` / `\n` / `\r`）。
- **实时多通道波形示波器**：
  - 支持 **文本 CSV / VOFA+ FireWater**（如 `12.3, 45.6` 或 `ch0:12.3, ch1:45.6`）
  - 支持 **JustFloat 二进制协议**（小端 `float32` 数组 + 帧尾 `00 00 80 7F`）
  - 支持最多 8 通道、Y 轴自适应/手动范围、通道显隐开关、鼠标悬停十字准星读数
  - 内置**模拟串口**，无需连接硬件即可体验波形绘制与 `AT` 回环测试
- **快捷指令集**：支持增删改与一键发送，配置保存至程序同级目录的 `quick_commands.json`。

## 项目结构

```text
serial_debugger/
├── assets/
│   └── app.ico              # 应用与窗口多分辨率图标
├── ui/
│   └── index.html           # 前端界面（HTML5 / CSS3 / Canvas）
├── tests/
│   └── test_serial_utils.py # 协议解析、校验与接口单元测试
├── main.py                  # 程序入口
├── web_app.py               # PyWebView 桥接与窗口管理
├── serial_manager.py        # 串口连接、异步读取与模拟串口后端
├── serial_utils.py          # HEX 编解码、校验算法与波形帧解析
├── build_exe.ps1            # Windows 单文件 .exe 打包脚本
├── requirements.txt         # Python 依赖列表
├── .gitignore
├── LICENSE
└── README.md
```

## 从源码运行

环境要求：Windows 10/11（自带 Edge WebView2 运行时）、Python 3.10+。

```powershell
pip install -r requirements.txt
python main.py
```

## 打包为单文件 `.exe`

```powershell
pip install pyinstaller
.\build_exe.ps1
```

打包完成后可在 `dist\SerialDebugger.exe` 找到独立可执行文件。

## 运行单元测试

```powershell
python -m unittest discover -s tests -v
```
