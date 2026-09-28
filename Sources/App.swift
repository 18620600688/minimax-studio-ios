import UIKit
import WebKit

/* MiniMax生成台 · iOS 巨魔(TrollStore)版 —— WKWebView 壳
   单一界面来源: Android 工程的 app/assets/index.html (构建时由 tools/sync_res.py 拷入 Resources/)
   桥协议: 注入 window.AndroidBridge 对象(与 Android 端同名, 页面零改动);
           http 返回 Promise(页面 jfetch 已兼容同步/异步两种);
           toast 用页面同款浮层(纯 JS, 不经原生);
           HEIC/人脸转正/视频压缩 走页面自带回退路径, v1 不做。 */

let APP_NAME = "MiniMaxStudio"
let BR_NAME = "br"

class AppDelegate: NSObject, UIApplicationDelegate {
    var window: UIWindow?
    func application(_ application: UIApplication,
                     didFinishLaunchingWithOptions launchOptions: [UIApplication.LaunchOptionsKey: Any]? = nil) -> Bool {
        window = UIWindow(frame: UIScreen.main.bounds)
        window?.rootViewController = WebVC()
        window?.makeKeyAndVisible()
        return true
    }
}

class WebVC: UIViewController, WKScriptMessageHandler, WKUIDelegate {
    var web: WKWebView!

    override func viewDidLoad() {
        super.viewDidLoad()
        view.backgroundColor = UIColor(red: 0.10, green: 0.11, blue: 0.14, alpha: 1)

        let cfg = WKWebViewConfiguration()
        cfg.userContentController.add(self, name: BR_NAME)
        cfg.userContentController.addUserScript(
            WKUserScript(source: Self.injectJs(), injectionTime: .atDocumentStart, forMainFrameOnly: true))
        cfg.preferences.setValue(true, forKey: "developerExtrasEnabled")

        web = WKWebView(frame: .zero, configuration: cfg)
        web.uiDelegate = self
        web.isOpaque = false
        web.backgroundColor = view.backgroundColor
        web.scrollView.contentInsetAdjustmentBehavior = .never
        web.translatesAutoresizingMaskIntoConstraints = false
        view.addSubview(web)
        NSLayoutConstraint.activate([
            web.topAnchor.constraint(equalTo: view.safeAreaLayoutGuide.topAnchor),
            web.bottomAnchor.constraint(equalTo: view.bottomAnchor),
            web.leadingAnchor.constraint(equalTo: view.leadingAnchor),
            web.trailingAnchor.constraint(equalTo: view.trailingAnchor),
        ])

        let html = Bundle.main.url(forResource: "index", withExtension: "html")
        let dir  = Bundle.main.resourceURL
        if let h = html {
            web.loadFileURL(h, allowingReadAccessTo: dir ?? h.deletingLastPathComponent())
        }
    }

    /* ---------- 注入的桥 (document start, 页面脚本执行前) ---------- */
    static func injectJs() -> String {
        return """
        (function(){
          if (window.AndroidBridge) return;
          var pending = {}, seq = 0;
          function send(p){ p.i = ++seq; window.webkit.messageHandlers.\(BR_NAME).postMessage(p);
            return new Promise(function(res){ pending[p.i] = res; }); }
          window.__brCb = function(i, json){ var f = pending[i]; if(f){ delete pending[i]; f(json); } };
          function toast(msg){
            var d = document.createElement('div');
            d.textContent = msg;
            d.style.cssText = 'position:fixed;left:50%;bottom:90px;transform:translateX(-50%);background:#2a2e38;color:#e8eaf0;padding:10px 18px;border-radius:20px;font-size:14px;z-index:9999;box-shadow:0 2px 10px rgba(0,0,0,.4)';
            document.body.appendChild(d);
            setTimeout(function(){ d.remove(); }, 2200);
          }
          window.AndroidBridge = {
            toast: toast,
            watch: function(){}, cancelWatch: function(){}, poster: function(){},
            keepScreen: function(on){ window.webkit.messageHandlers.\(BR_NAME).postMessage({a:'keep', v: !!on}); },
            http: function(url, method, bodyB64, ct){
              return send({a:'http', u:url, m:method||'GET', b:bodyB64||'', ct:ct||''});
            },
            asset: function(name){ return send({a:'asset', u:name||''}); },
            download: function(url, filename){ return send({a:'download', u:url, n:filename||''}); }
          };
        })();
        """
    }

    /* ---------- 桥分发 ---------- */
    func userContentController(_ userContentController: WKUserContentController,
                               didReceive message: WKScriptMessage) {
        guard let msg = message.body as? [String: Any], let act = msg["a"] as? String else { return }
        switch act {
        case "http":     doHttp(msg)
        case "asset":    doAsset(msg)
        case "download": doDownload(msg)
        case "keep":
            DispatchQueue.main.async { UIApplication.shared.isIdleTimerDisabled = (msg["v"] as? Bool ?? false) }
        default: break
        }
    }

    func cb(_ id: Int, _ json: String) {
        DispatchQueue.main.async {
            self.web.evaluateJavaScript("window.__brCb(\(id), \(json));", completionHandler: nil)
        }
    }

    static func jsStr(_ s: String) -> String {
        let d = try? JSONSerialization.data(withJSONObject: [s], options: [])
        let raw = String(data: d ?? Data(), encoding: .utf8) ?? "\"\""
        return String(raw.dropFirst().dropLast())
    }

    /* ---------- HTTP 代理: 原生 URLSession, 无 CORS/ATS 限制(Info.plist 已放开明文) ---------- */
    func doHttp(_ msg: [String: Any]) {
        let id = msg["i"] as? Int ?? 0
        guard let us = URL(string: msg["u"] as? String ?? "") else {
            cb(id, "{\"status\":-1,\"err\":\"bad url\"}"); return
        }
        var req = URLRequest(url: us, timeoutInterval: 120)
        req.httpMethod = msg["m"] as? String ?? "GET"
        let ct = msg["ct"] as? String ?? ""
        if !ct.isEmpty { req.setValue(ct, forHTTPHeaderField: "Content-Type") }
        if let b64 = msg["b"] as? String, !b64.isEmpty, let data = Data(base64Encoded: b64) {
            req.httpBody = data
            if ct.isEmpty { req.setValue("application/octet-stream", forHTTPHeaderField: "Content-Type") }
        }
        URLSession.shared.dataTask(with: req) { data, resp, err in
            if let e = err {
                self.cb(id, "{\"status\":-1,\"err\":\"\(Self.jsStr(e.localizedDescription))\"}")
                return
            }
            let code = (resp as? HTTPURLResponse)?.statusCode ?? 0
            let b64 = data?.base64EncodedString() ?? ""
            self.cb(id, "{\"status\":\(code),\"body\":\"\(b64)\"}")
        }.resume()
    }

    /* ---------- asset: 读 bundle 内文件 (模板兜底, 正常走 TPL_PACK 用不到) ---------- */
    func doAsset(_ msg: [String: Any]) {
        let id = msg["i"] as? Int ?? 0
        let name = msg["u"] as? String ?? ""
        let base = (name as NSString).deletingPathExtension
        let ext  = (name as NSString).pathExtension
        guard let url = Bundle.main.url(forResource: base, withExtension: ext.isEmpty ? "json" : ext),
              let txt = try? String(contentsOf: url, encoding: .utf8) else {
            cb(id, "{\"err\":\"asset not found: \(Self.jsStr(name))\"}"); return
        }
        let b64 = Data(txt.utf8).base64EncodedString()
        cb(id, "{\"body\":\"\(b64)\"}")
    }

    /* ---------- download: 下载到 tmp → 系统分享面板(可存相册/文件) ---------- */
    func doDownload(_ msg: [String: Any]) {
        let id = msg["i"] as? Int ?? 0
        guard let us = URL(string: msg["u"] as? String ?? "") else {
            cb(id, "{\"err\":\"bad url\"}"); return
        }
        let name = msg["n"] as? String ?? us.lastPathComponent
        let task = URLSession.shared.downloadTask(with: us) { loc, resp, err in
            if err != nil || loc == nil {
                self.cb(id, "{\"err\":\"\(Self.jsStr(err?.localizedDescription ?? "download failed"))\"}")
                return
            }
            let dst = FileManager.default.temporaryDirectory.appendingPathComponent(name)
            try? FileManager.default.removeItem(at: dst)
            do { try FileManager.default.moveItem(at: loc!, to: dst) }
            catch { self.cb(id, "{\"err\":\"move failed\"}"); return }
            self.cb(id, "{\"ok\":true}")
            DispatchQueue.main.async { self.share(dst) }
        }
        task.resume()
    }

    func share(_ url: URL) {
        guard let scene = UIApplication.shared.connectedScenes.first(where: { $0.activationState == .foregroundActive }) as? UIWindowScene,
              let root = scene.windows.first(where: { $0.isKeyWindow })?.rootViewController else { return }
        let av = UIActivityViewController(activityItems: [url], applicationActivities: nil)
        av.popoverPresentationController?.sourceView = root.view
        av.popoverPresentationController?.sourceRect = CGRect(x: root.view.bounds.midX, y: 50, width: 1, height: 1)
        root.present(av, animated: true)
    }

    /* ---------- JS alert/confirm/prompt ---------- */
    func webView(_ webView: WKWebView, runJavaScriptAlertPanelWithMessage message: String,
                 initiatedByFrame frame: WKFrameInfo, completionHandler: @escaping () -> Void) {
        simpleAlert(message) { completionHandler() }
    }
    func webView(_ webView: WKWebView, runJavaScriptConfirmPanelWithMessage message: String,
                 initiatedByFrame frame: WKFrameInfo, completionHandler: @escaping (Bool) -> Void) {
        let ac = UIAlertController(title: nil, message: message, preferredStyle: .alert)
        ac.addAction(UIAlertAction(title: "取消", style: .cancel) { _ in completionHandler(false) })
        ac.addAction(UIAlertAction(title: "确定", style: .default) { _ in completionHandler(true) })
        present(ac, animated: true)
    }
    func webView(_ webView: WKWebView, runJavaScriptTextInputPanelWithPrompt prompt: String,
                 defaultText: String?, initiatedByFrame frame: WKFrameInfo,
                 completionHandler: @escaping (String?) -> Void) {
        let ac = UIAlertController(title: nil, message: prompt, preferredStyle: .alert)
        ac.addTextField { $0.text = defaultText }
        ac.addAction(UIAlertAction(title: "取消", style: .cancel) { _ in completionHandler(nil) })
        ac.addAction(UIAlertAction(title: "确定", style: .default) { _ in completionHandler(ac.textFields?.first?.text) })
        present(ac, animated: true)
    }
    func simpleAlert(_ msg: String, done: @escaping () -> Void) {
        let ac = UIAlertController(title: nil, message: msg, preferredStyle: .alert)
        ac.addAction(UIAlertAction(title: "好", style: .default) { _ in done() })
        present(ac, animated: true)
    }
}
