import UIKit
import WebKit
import AVKit

// SAUDI.TV for iPhone (owner, 25 Nov 2026). The screens are the web app (/tv) inside the app; the video is played by
// the phone's own player, straight from the provider over http, from the customer's own internet. A web page in
// Safari cannot do that (https page, http video), and the providers refuse every server in between.

@main
final class AppDelegate: UIResponder, UIApplicationDelegate {
    var window: UIWindow?
    func application(_ application: UIApplication, didFinishLaunchingWithOptions launchOptions: [UIApplication.LaunchOptionsKey: Any]?) -> Bool {
        try? AVAudioSession.sharedInstance().setCategory(.playback, mode: .moviePlayback)
        let w = UIWindow(frame: UIScreen.main.bounds)
        w.rootViewController = MainController()
        w.backgroundColor = .black
        w.makeKeyAndVisible()
        window = w
        return true
    }
}

final class MainController: UIViewController, WKScriptMessageHandler, WKNavigationDelegate {
    static let site = URL(string: "https://saudi1.1saifsaudi.workers.dev/tv?app=ios")!
    private var web: WKWebView!
    private var player: AVPlayer?
    private var statusWatch: NSKeyValueObservation?
    private var timeWatch: Any?
    private var key = ""

    override var preferredStatusBarStyle: UIStatusBarStyle { .lightContent }

    override func loadView() {
        let c = WKWebViewConfiguration()
        c.allowsInlineMediaPlayback = true
        c.mediaTypesRequiringUserActionForPlayback = []
        c.applicationNameForUserAgent = "SAUDI1-iOS/1"
        c.userContentController.add(self, name: "play")
        web = WKWebView(frame: .zero, configuration: c)
        web.navigationDelegate = self
        web.isOpaque = false
        web.backgroundColor = .black
        web.scrollView.backgroundColor = .black
        web.allowsBackForwardNavigationGestures = false
        view = web
        web.load(URLRequest(url: Self.site, cachePolicy: .reloadIgnoringLocalCacheData))
    }

    // no internet at start: try again every 5 s
    func webView(_ w: WKWebView, didFailProvisionalNavigation n: WKNavigation!, withError e: Error) { retry() }
    func webView(_ w: WKWebView, didFail n: WKNavigation!, withError e: Error) { retry() }
    private func retry() {
        let html = "<body style='background:#0b0e14;color:#fff;font:17px -apple-system;display:flex;align-items:center;justify-content:center;height:90vh;text-align:center'>No internet connection<br>trying again…</body>"
        web.loadHTMLString(html, baseURL: nil)
        DispatchQueue.main.asyncAfter(deadline: .now() + 5) { [weak self] in self?.web.load(URLRequest(url: Self.site)) }
    }

    // the page asks for a video: {url, title, live, from (ms), key}
    func userContentController(_ u: WKUserContentController, didReceive m: WKScriptMessage) {
        guard let d = m.body as? [String: Any], let s = d["url"] as? String, let url = URL(string: s) else { return }
        let live = (d["live"] as? Bool) ?? false
        let from = (d["from"] as? Double) ?? 0
        key = (d["key"] as? String) ?? ""
        let asset = AVURLAsset(url: url, options: ["AVURLAssetHTTPHeaderFieldsKey": ["User-Agent": "Lavf/60.3.100"]])
        let item = AVPlayerItem(asset: asset)
        item.preferredForwardBufferDuration = live ? 8 : 30
        let p = AVPlayer(playerItem: item)
        p.automaticallyWaitsToMinimizeStalling = true
        player = p
        statusWatch = item.observe(\.status, options: [.new]) { [weak self] it, _ in
            guard it.status == .failed else { return }
            let why = (it.error as NSError?).map { "\($0.domain) \($0.code)" } ?? "unknown"
            DispatchQueue.main.async { self?.closePlayer(error: why) }
        }
        // films and episodes: the place reached is kept by the page (continue watching)
        if !live && !key.isEmpty {
            timeWatch = p.addPeriodicTimeObserver(forInterval: CMTime(seconds: 10, preferredTimescale: 1), queue: .main) { [weak self] t in
                guard let self = self, t.seconds > 60 else { return }
                self.web.evaluateJavaScript("window.nativePos && window.nativePos(\(self.js(self.key)), \(Int(t.seconds * 1000)))")
            }
        }
        let pv = AVPlayerViewController()
        pv.player = p
        pv.allowsPictureInPicturePlayback = true
        pv.modalPresentationStyle = .fullScreen
        if from > 0 && !live { p.seek(to: CMTime(seconds: from / 1000, preferredTimescale: 1000)) }
        present(pv, animated: true) { p.play() }
        pv.presentationController?.delegate = nil
        NotificationCenter.default.addObserver(forName: .AVPlayerItemDidPlayToEndTime, object: item, queue: .main) { [weak self] _ in
            guard let self = self else { return }
            self.web.evaluateJavaScript("window.nativeEnded && window.nativeEnded(\(self.js(self.key)))")
            self.dismiss(animated: true) { self.stop() }
        }
    }

    override func viewDidAppear(_ animated: Bool) {
        super.viewDidAppear(animated)
        // back from the full-screen player (swiped down or Done): stop the video
        if presentedViewController == nil { stop() }
    }

    private func closePlayer(error: String) {
        web.evaluateJavaScript("window.nativeFail && window.nativeFail(\(js(error)))")
        if presentedViewController != nil { dismiss(animated: true) { self.stop() } } else { stop() }
    }

    private func stop() {
        if let t = timeWatch { player?.removeTimeObserver(t); timeWatch = nil }
        statusWatch = nil
        player?.pause()
        player?.replaceCurrentItem(with: nil)
        player = nil
    }

    private func js(_ s: String) -> String {
        let d = try? JSONSerialization.data(withJSONObject: [s])
        let a = d.flatMap { String(data: $0, encoding: .utf8) } ?? "[\"\"]"
        return String(a.dropFirst().dropLast())
    }
}
