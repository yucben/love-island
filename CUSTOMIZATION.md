# 本机灵动岛定制版

基于 MIT 项目 [Dynamic-Island-Plasma-Wayland](https://github.com/teodorgross/Dynamic-Island-Plasma-Wayland)，固定上游 v1.0.1 / `50dec690461fb1519f349a85ba62c8e503228992`。上游许可证保留于 LICENSE。

本版增加常驻胶囊、播放时常驻媒体与点击控制、内置通知中心、FIFO 通知队列与仅前台倒计时、音量/亮度抢占后恢复、UPower 接电提示、KWin 全屏检测、锁屏抑制、KScreen 主屏跟随及 KDE 勿扰设置联动。显示文字使用中文，黑色主体覆盖顶部面板中央空白处，不为窗口另留空间。

源码部署执行 `bash tools/session.sh install`，实际安装目录是 `~/.local/share/dynamic-island-app`。系统包安装与管理见 README。不要直接用上游 git pull 覆盖本版。

## 使用

- 空闲胶囊：鼠标悬停展开通知中心，移开自动收起。
- 音乐胶囊：鼠标悬停展开上一首、播放/暂停和下一首，移开自动收起；悬停期间保持展开。
- 任意状态右键：将活动通知收入历史并打开通知中心，移开自动收起。
- 通知：悬停展开、移开收起，悬停时暂停倒计时；点击打开来源应用或默认操作，按钮执行应用提供的操作，中键或上滑关闭。新通知仍会自动短暂展示。
- 全屏与锁屏：岛隐藏；期间到达的通知只进入历史，之后不补弹。
- KDE 勿扰开启后：消息只进入历史；手动调节音量/亮度仍反馈。全屏或锁屏优先隐藏一切。
- 多屏：只跟随 KScreen 优先级最高的启用输出，约三秒内更新。

## 管理

```bash
~/.local/bin/island-session status
~/.local/bin/island-session restore
~/.local/bin/island-session start
```

`restore` 关闭登录自启动，恢复原始 OSD 设置并让 Plasma 重新接管通知，保留历史。`start` 重新启用登录自启动和灵动岛。应用菜单也提供“灵动岛”和“恢复 KDE 默认通知”入口。

服务启动失败或崩溃时，退出钩子恢复原 OSD 设置并请求 Plasma 重新接管通知，避免留下没有通知服务的会话。图形会话退出期间不额外拉起 Plasma。

原始配置记录与各次部署备份位于 `~/.local/state/dynamic-island/`。依赖使用 CachyOS 软件仓库的系统 PySide6、python-dbus、layer-shell-qt；不使用自带另一套 Qt 的 PyPI PySide6。

## 边界

- 历史支持查看、清空及打开来源应用；已消失的卡片不保留操作按钮或内联回复。
- 播放器需要提供 MPRIS；多个播放器优先正在播放的播放器，再按最近更新选择。
- 动态音柱是播放状态的视觉提示，不是音频频谱测量。
- 文件复制进度继续由 KDE 原有进度界面处理。
- 暂停后三秒收回空闲胶囊；鼠标仍悬停时保留控制，便于恢复播放。
- 外屏物理插拔、真实插拔充电器与退出登录再登录，需要实机操作才可完整验收。

## 验证

在宿主使用系统 Python：

```bash
PYTHONPATH=src /usr/bin/python -m unittest discover -s tests -v
```

该检查使用独立临时配置与历史，在离屏窗口验证通知顺序、计时、勿扰、隐藏与真实 QML 的悬停展开/移开收起、媒体按钮及通知按钮交互，不影响当前桌面通知。

## 高刷新率

胶囊与通知控件使用连续补间动画，避开 Qt SpringAnimation 约 62 FPS 的离散步进上限；展开宽/高为 340/300ms，收起宽/高为 450/430ms，另有悬停防抖。原生单实例采样中位帧间隔为 7–9ms，仍有偶发长帧，尚未达到持续稳定 144 FPS。详情见 `docs/island-performance.md`。
