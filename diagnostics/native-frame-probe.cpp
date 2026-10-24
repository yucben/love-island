// Minimal native reference: distinguish PySide/UI cost from Qt/Wayland pacing.
#include <QGuiApplication>
#include <QQmlApplicationEngine>
#include <QQuickWindow>
#include <QQuickItem>
#include <QScreen>
#include <QTimer>
#include <QElapsedTimer>
#include <QJsonDocument>
#include <QJsonObject>
#include <QTextStream>
#include <QOpenGLContext>
#include <QOpenGLFunctions>
#include <QAnimationDriver>
#include <QChronoTimer>
#include <QtGui/qguiapplication_platform.h>
#include <qpa/qplatformnativeinterface.h>
#include <qpa/qplatformwindow_p.h>
#include <wayland-client.h>
#include "island-presentation-time.h"
#include <algorithm>
#include <vector>

static QJsonObject summary(std::vector<double> values) {
    if (values.empty()) return {};
    std::sort(values.begin(), values.end());
    return {{"count", int(values.size())}, {"p50_ms", values[values.size()/2]},
            {"p95_ms", values[int((values.size()-1)*.95)]},
            {"p99_ms", values[int((values.size()-1)*.99)]}, {"max_ms", values.back()}};
}
class PreciseDriver : public QAnimationDriver {
    QElapsedTimer clock;
    QChronoTimer timer;
public:
    PreciseDriver() {
        timer.setTimerType(Qt::PreciseTimer);
        timer.setInterval(std::chrono::milliseconds(6));
        QObject::connect(&timer, &QChronoTimer::timeout, this, [this](){ advanceAnimation(); });
    }
    qint64 elapsed() const override { return clock.isValid() ? clock.elapsed() : 0; }
protected:
    void start() override { clock.restart(); QAnimationDriver::start(); timer.start(); }
    void stop() override { timer.stop(); QAnimationDriver::stop(); }
};
struct PresentationProbe {
    wl_display *display=nullptr;
    wl_event_queue *queue=nullptr;
    wp_presentation *presentation=nullptr;
    QElapsedTimer *clock=nullptr;
    std::vector<std::pair<double,double>> presented;
    int requestedCount=0, discardedCount=0, surfaceCount=0;
    static void clockId(void*,wp_presentation*,uint32_t){}
    static void registry(void *data, wl_registry *registry, uint32_t name, const char *interface, uint32_t version) {
        auto self=static_cast<PresentationProbe*>(data);
        if(QByteArray(interface)=="wp_presentation") {
            self->presentation=static_cast<wp_presentation*>(wl_registry_bind(registry,name,&wp_presentation_interface,1));
            static const struct wp_presentation_listener listener={PresentationProbe::clockId};
            wp_presentation_add_listener(self->presentation,&listener,self);
        }
    }
    static void removed(void*,wl_registry*,uint32_t){}
    struct Feedback { PresentationProbe* probe; double requested; };
    static void output(void*,struct wp_presentation_feedback*,wl_output*){}
    static void shown(void *data, struct wp_presentation_feedback *feedback, uint32_t hi, uint32_t lo, uint32_t ns,
                      uint32_t,uint32_t,uint32_t,uint32_t) {
        auto request=static_cast<Feedback*>(data);
        double time=(double((uint64_t(hi)<<32)|lo)*1000)+(double(ns)/1e6);
        request->probe->presented.emplace_back(request->requested,time);
        wp_presentation_feedback_destroy(feedback); delete request;
    }
    static void discarded(void*data,struct wp_presentation_feedback*feedback) {
        static_cast<Feedback*>(data)->probe->discardedCount++;
        wp_presentation_feedback_destroy(feedback); delete static_cast<Feedback*>(data);
    }
    void init(QGuiApplication &app, QElapsedTimer &timer) {
        clock=&timer;
        display=app.nativeInterface<QNativeInterface::QWaylandApplication>()->display();
        queue=wl_display_create_queue(display);
        auto registry=wl_display_get_registry(display);
        wl_proxy_set_queue(reinterpret_cast<wl_proxy*>(registry),queue);
        static const wl_registry_listener listener={PresentationProbe::registry,PresentationProbe::removed};
        wl_registry_add_listener(registry,&listener,this);
        wl_display_roundtrip_queue(display,queue);
        wl_registry_destroy(registry);
    }
    void request(QWindow *window) {
        if(!presentation) return;
        auto native=window->nativeInterface<QNativeInterface::Private::QWaylandWindow>();
        auto surface=native ? native->surface() : nullptr;
        if(!surface) return;
        surfaceCount++; requestedCount++;
        auto feedback=wp_presentation_feedback(presentation,surface);
        auto data=new Feedback{this,clock->nsecsElapsed()/1e6};
        static const struct wp_presentation_feedback_listener listener={output,shown,discarded};
        wp_presentation_feedback_add_listener(feedback,&listener,data);
        wl_display_flush(display);
    }
};
int main(int argc, char **argv) {
    bool normal = argc > 1 && QByteArray(argv[1]) == "--normal";
    if (!normal) qputenv("QT_WAYLAND_SHELL_INTEGRATION", "layer-shell");
    QGuiApplication app(argc, argv);
    QQmlApplicationEngine engine;
    QByteArray source = R"QML(
import QtQuick
import QtQuick.Window
import org.kde.layershell as LayerShell
Window {
    visible: true; color: "transparent"; width: Screen.width; height: 360
    flags: Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.WindowTransparentForInput
    LayerShell.Window.scope: "island-native-reference"
    LayerShell.Window.layer: LayerShell.Window.LayerOverlay
    LayerShell.Window.anchors: LayerShell.Window.AnchorTop | LayerShell.Window.AnchorLeft | LayerShell.Window.AnchorRight
    LayerShell.Window.exclusionZone: -1
    Rectangle {
        objectName: "pill"
        anchors.horizontalCenter: parent.horizontalCenter
        property bool opened: false
        width: opened ? 390 : 112; height: opened ? 152 : 28
        color: "black"; radius: 20
        Behavior on width { NumberAnimation { duration: 340; easing.type: Easing.OutCubic } }
        Behavior on height { NumberAnimation { duration: 300; easing.type: Easing.OutCubic } }
    }
}
)QML";
    if (normal) {
        source.replace("import org.kde.layershell as LayerShell", "");
        auto lines=source.split('\n'); source.clear();
        for (auto line: lines) if (!line.trimmed().startsWith("LayerShell.")) source += line + '\n';
    }
    engine.loadData(source);
    if (engine.rootObjects().isEmpty()) return 2;
    auto window=qobject_cast<QQuickWindow*>(engine.rootObjects()[0]);
    auto pill=window->findChild<QQuickItem*>("pill");
    PreciseDriver driver;
    if(qEnvironmentVariableIsSet("ISLAND_PROBE_PRECISE_CLOCK")) driver.install();
    QElapsedTimer clock; clock.start();
    PresentationProbe presentation;
    presentation.init(app,clock);
    QTimer dispatch;
    dispatch.setInterval(1);
    QObject::connect(&dispatch,&QTimer::timeout,&app,[&](){wl_display_dispatch_queue_pending(presentation.display,presentation.queue);});
    dispatch.start();
    std::vector<double> frames, updates, transitions, rendered, ended;
    QString renderer, vendor;
    QObject::connect(window, &QQuickWindow::beforeRendering, window, [&](){
        if (renderer.isEmpty()) {
            if (auto context=QOpenGLContext::currentContext()) {
                renderer=QString::fromLatin1(reinterpret_cast<const char*>(context->functions()->glGetString(GL_RENDERER)));
                vendor=QString::fromLatin1(reinterpret_cast<const char*>(context->functions()->glGetString(GL_VENDOR)));
            }
        }
    }, Qt::DirectConnection);
    auto elapsed=[&](){return clock.nsecsElapsed()/1e6;};
    QObject::connect(window, &QQuickWindow::frameSwapped, &app, [&](){frames.push_back(elapsed());}, Qt::QueuedConnection);
    QObject::connect(window, &QQuickWindow::afterRendering, &app, [&](){rendered.push_back(elapsed());}, Qt::QueuedConnection);
    QObject::connect(window, &QQuickWindow::afterFrameEnd, &app, [&](){ended.push_back(elapsed());}, Qt::QueuedConnection);
    QObject::connect(pill, &QQuickItem::widthChanged, &app, [&](){updates.push_back(elapsed()); presentation.request(window);});
    for (int i=0;i<5;i++) QTimer::singleShot(500+i*1000, &app, [&,i](){
        transitions.push_back(elapsed()); pill->setProperty("opened", i%2==0);
    });
    QTimer::singleShot(5400, &app, &QGuiApplication::quit);
    app.exec();
    auto gaps=[&](const auto& times){
        std::vector<double> result;
        for (double start: transitions) {
            double previous=-1;
            for (double t:times) if(t>=start+20 && t<=start+300) {
                if(previous>=0) result.push_back(t-previous);
                previous=t;
            }
        }
        return result;
    };
    QJsonObject result{{"host", "native-c++"}, {"normal_window", normal},
        {"renderer",renderer}, {"vendor",vendor},
        {"refresh_hz", window->screen()->refreshRate()},
        {"frames", summary(gaps(frames))}, {"rendered",summary(gaps(rendered))},
        {"frameEnd",summary(gaps(ended))}, {"updates",summary(gaps(updates))}};
    std::vector<double> presentationGaps;
    for(double start: transitions) {
        double previous=-1;
        for(auto [requested,shown]:presentation.presented) if(requested>=start+20 && requested<=start+300) {
            if(previous>=0 && shown>previous+.001) presentationGaps.push_back(shown-previous);
            previous=shown;
        }
    }
    result.insert("presented",summary(presentationGaps));
    result.insert("feedback_count",int(presentation.presented.size()));
    result.insert("requests",presentation.requestedCount);
    result.insert("discarded",presentation.discardedCount);
    result.insert("presentation_protocol",bool(presentation.presentation));
    QTextStream(stdout) << QJsonDocument(result).toJson();
    window->close();
}
