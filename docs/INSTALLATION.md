# Desktop Installation Guide

Install and run Life Money Simulator without Python or command-line tools.

## Safety & Authenticity Warning

- **Official `main` Releases Only**: Download Life Money Simulator exclusively from [DontKwo/time-is-money-sim Releases](https://github.com/DontKwo/time-is-money-sim/releases/latest).
- **Fork Warning**: Never download builds from forked repositories unless you have verified the source code yourself and know they do not contain malware. Only official `main` releases are maintained by the author, and I make no promises.
- **Bypassing Security Prompts**: Because independent open-source executables do not carry paid commercial signing certificates, Windows and macOS will warn that the app is unrecognized or potentially unsafe. Bypassing these warnings is strictly at your own discretion, and the software is provided "AS IS" with zero liability.

---

## Windows

1. Download `TimeIsMoneySim-Windows.exe` from [Latest Releases](https://github.com/DontKwo/time-is-money-sim/releases/latest).
2. Double-click `TimeIsMoneySim-Windows.exe` to open the desktop application.
3. If **Microsoft Defender SmartScreen** displays *"Windows protected your PC"*:
   - Click **More info**.
   - Confirm the download came from `DontKwo/time-is-money-sim`, then click **Run anyway** at your own discretion.
4. Alternative unblock method: Right-click `TimeIsMoneySim-Windows.exe` -> **Properties** -> check **Unblock** under Security -> click **Apply** and **OK**.

---

## macOS

1. Download `TimeIsMoneySim-macOS.zip` from [Latest Releases](https://github.com/DontKwo/time-is-money-sim/releases/latest).
2. Unzip the archive and drag **`TimeIsMoneySim.app`** into **Applications**.
3. On macOS Sonoma and Sequoia, approve independently published apps in **System Settings**:
   - Double-click **`TimeIsMoneySim`** once so macOS registers the blocked prompt, then click **OK** (or **Done**).
   - Open **System Settings** -> **Privacy & Security** -> **Security** -> click **Open Anyway** and confirm with your password or Touch ID.
4. Developer Terminal Alternative: run `xattr -cr /Applications/TimeIsMoneySim.app`, then launch normally.

---

## Linux

1. Download `TimeIsMoneySim-Linux.tar.gz` from [Latest Releases](https://github.com/DontKwo/time-is-money-sim/releases/latest).
2. Extract the archive (`tar -xzf TimeIsMoneySim-Linux.tar.gz`).
3. Ensure executable permissions (`chmod +x TimeIsMoneySim-Linux`) and launch the binary.

---

## Related Documentation

- [Project Overview](../README.md)
- [User Guide](USER_GUIDE.md)
- [Frequently Asked Questions](FAQ.md)
- [Developer Guide](DEVELOPMENT.md)
- [Security Policy](../SECURITY.md)
- [MIT License](../LICENSE)
