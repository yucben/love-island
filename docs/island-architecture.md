# 灵动岛模块边界

运行栈为 Python / PySide6 + QML。此次整理保留现有交互和收起速度，不改变系统显卡或刷新率设置，也不表示已经达到稳定 144 FPS。

## 事件流

系统适配器 → IslandController → 通知队列 / 播放状态 / 历史 → QML 展示状态 → 渲染组件。

| 模块 | 负责的规则与入口 |
| --- | --- |
| `server.py`、`media.py`、`desktop_sources.py` | 接收通知协议、MPRIS、UPower、KScreen；将系统事件转换为应用数据 |
| `desktop.py`、`qml/Platform/PlasmaSettings.qml` | 锁屏、全屏、主屏及 KDE 勿扰联动 |
| `controller.py` | `receive`、`show_status`、`attach_media`；统一抑制策略、归档、通知确认和用户操作 |
| `notification_queue.py` | `put`、`remove`、`set_paused`；FIFO、容量、仅前台倒计时与暂停恢复，不操作历史和 D-Bus |
| `playback.py` | 播放源选择结果、暂停宽限、封面缓存与播放命令；`snapshot` 提供持久媒体状态 |
| `model.py`、`history.py` | 当前通知及历史数据；`front` 直接提供队首，不由界面重复读取和拼装 |
| `IslandPresentation.qml` | `enter`、`leave`、`showHistory`、`collapse`；唯一展开状态、延时、模式选择与目标尺寸 |
| `Island.qml` | 连接数据、交互和动画，更新窗口输入区域 |
| `CompactMusic`、`MusicPlayer`、`StatusCard`、`NotificationHistory` | 接收数据并发出用户意图，不直接访问 Controller 或系统服务 |

不再通过 ExperienceController 继承并覆盖父类私有方法；不再由多个展开布尔值组合显示模式。队列和播放对象各自管理自己的计时器。

## 配置与部署

`config.py:complete_settings` 是安装和运行共用的配置迁移入口，补齐缺省值并保留用户设置与扩展字段。删除无效配置 `stackDepth`、`glowOpacity`、`strokeOpacity`、`mediaHideWhenFocused`、`mediaTimeout`。

动画常量集中在 `Theme.qml`。展开宽/高 340/300ms，收起宽/高 450/430ms；悬停防抖单独计时。几何设置从配置传入展示状态。

`tools/session.sh` 将运行源码和两个服务管理文件部署到稳定安装路径，备份旧版本与配置。测试和 `diagnostics/` 不进入运行目录。旧上游安装器和设置面板不包含在本发布目录中。

## 验证边界

宿主系统 Python 执行 `PYTHONPATH=src /usr/bin/python -m unittest discover -s tests -v`，当前 26 项。测试通过公开事件入口、真实 QML 交互和独立临时配置验证队列、播放、抑制、展开模式与配置迁移。

`diagnostics/check-session.py` 验证运行中的原生勿扰、主屏和媒体接口；`measure-animation.py` 测应用帧就绪和形状更新。实际屏幕呈现须使用原生 presentation feedback；两类数据不能互相替代。物理插拔和重新登录仍需实机验证。
