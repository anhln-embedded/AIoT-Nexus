# XiaoZhi Registration Tool

GUI helper for generating a random XiaoZhi-compatible `Device-Id` and `Client-Id`,
setting the registration device name, requesting an activation code from the
official OTA endpoint, and copying the resulting `.env` block into AIoT-Nexus.

Run from the project root:

```powershell
.\.venv\Scripts\python.exe .\tools\xiaozhi_registration_tool.py
```

Use the generated activation code on `xiaozhi.me`, then copy the `.env` block
into the project `.env`.
