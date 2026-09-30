# -*- coding: utf-8 -*-
"""一键发布到 GitHub 并取回云编译的 IPA.
用法: GH_TOKEN=<pat> python tools/ios_publish.py [仓库名]
前置: fine-grained PAT, Repository access=All repositories,
      权限勾 Administration/Actions/Contents/Workflows 四项 Read and write.
"""
import base64, json, os, re, sys, time, urllib.request, urllib.error

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
TOK  = os.environ.get("GH_TOKEN") or sys.exit("缺 GH_TOKEN 环境变量")
API  = "https://api.github.com"
HDR  = {"Authorization": "Bearer " + TOK, "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28", "User-Agent": "ios-publish"}

def req(method, url, body=None, raw=False, headers=None):
    h = dict(HDR)
    if headers: h.update(headers)
    data = None
    if body is not None:
        data = body if isinstance(body, bytes) else json.dumps(body).encode()
        h.setdefault("Content-Type", "application/json")
    r = urllib.request.Request(url, data=data, headers=h, method=method)
    try:
        with urllib.request.urlopen(r) as resp:
            b = resp.read()
            return resp.status, (b if raw else (json.loads(b) if b else {}))
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode("utf-8", "replace")

def gh_user():
    st, j = req("GET", API + "/user")
    return j.get("login")

def _git_proxy_args():
    """本机直连 github.com:443 经常被运营商/防火墙掐断，先看有没有活着的本地代理。

    实测：Clash Verge Rev 的混合端口 7897 可用；之前记的 60592 隧道经常没在监听。
    返回要插到 `git` 后面的参数列表（无代理就是空列表，行为不变）。
    """
    import socket
    for port in (7897, 60592, 7890, 10809, 1080):
        s = socket.socket()
        s.settimeout(0.6)
        try:
            s.connect(("127.0.0.1", port))
        except OSError:
            continue
        finally:
            s.close()
        print("git: 使用本机代理 127.0.0.1:%d" % port)
        return ["-c", "http.proxy=http://127.0.0.1:%d" % port,
                "-c", "https.proxy=http://127.0.0.1:%d" % port]
    return []


def push_repo(user, repo):
    import subprocess
    gproxy = _git_proxy_args()
    subprocess.run(["git", "init", "-b", "main"], cwd=ROOT, check=True, capture_output=True)
    subprocess.run(["git", "add", "-A"], cwd=ROOT, check=True, capture_output=True)
    subprocess.run(["git", "commit", "-m", "MiniMax iOS shell"], cwd=ROOT,
                   check=False, capture_output=True)   # 无改动会失败, 忽略
    url = "https://x-access-token:%s@github.com/%s/%s.git" % (TOK, user, repo)
    subprocess.run(["git", "-c", "credential.helper=", "remote", "remove", "origin"],
                   cwd=ROOT, capture_output=True)
    subprocess.run(["git", "-c", "credential.helper=", "remote", "add", "origin", url],
                   cwd=ROOT, check=True, capture_output=True)
    subprocess.run(["git", "-c", "credential.helper="] + gproxy +
                   ["push", "-u", "origin", "main"],
                   cwd=ROOT, check=True, capture_output=True)
    print("pushed ->", user + "/" + repo)
    # 回退 2s 保险: 之后 wait_run 只认这个时刻之后创建的运行
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(time.time() - 2))

def wait_run(user, repo, since=None, timeout=900):
    """等待 Actions 运行完成.

    since: ISO8601 时间戳(本次 push 的时间). 传了就只认这个时刻之后创建的运行,
           否则会误抓到上一次已经 success 的旧运行 -> 下载到旧 IPA.
    """
    print("等待 Actions 运行 ...")
    t0 = time.time()
    seen = {}
    while time.time() - t0 < timeout:
        st, j = req("GET", "%s/repos/%s/%s/actions/runs?per_page=5" % (API, user, repo))
        for r in (j.get("workflow_runs") or []):
            if since and r.get("created_at", "") < since:
                continue                      # 本次 push 之前的旧运行, 跳过
            seen[r["id"]] = r
            if r["status"] == "completed":
                if r["conclusion"] == "success":
                    return r
                print("运行失败:", r["html_url"])
                sys.exit("云编译失败, 把日志贴回来修")
        print("  ...运行中 (%d 个候选)" % len(seen))
        time.sleep(10)
    sys.exit("超时")

def fetch_artifact(user, repo, run_id, out):
    st, j = req("GET", "%s/repos/%s/%s/actions/runs/%d/artifacts" % (API, user, repo, run_id))
    arts = j.get("artifacts") or []
    if not arts: sys.exit("无 artifact")
    url = arts[0]["archive_download_url"]
    # 401 坑: 302 到 Azure 签名 URL 后不能带 Bearer -> 手动两跳
    r = urllib.request.Request(url, headers=HDR, method="GET")
    opener = urllib.request.build_opener(NoRedirect())
    try:
        resp = opener.open(r)
        loc = None
    except urllib.error.HTTPError as e:
        loc = e.headers.get("Location")
        if not loc: raise
    r2 = urllib.request.Request(loc, headers={"User-Agent": "ios-publish"})
    with urllib.request.urlopen(r2) as resp, open(out, "wb") as fh:
        fh.write(resp.read())
    print("artifact ->", out, os.path.getsize(out), "bytes")

class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *a, **kw): return None


def verify_ipa(zippath):
    """解压 artifact zip, 校验里面的 .ipa 是真 arm64 Mach-O 且带 Info.plist."""
    import zipfile
    outdir = os.path.join(ROOT, "ipa_out")
    os.makedirs(outdir, exist_ok=True)
    with zipfile.ZipFile(zippath) as z:
        z.extractall(outdir)
    ipas = [f for f in os.listdir(outdir) if f.lower().endswith(".ipa")]
    if not ipas: sys.exit("zip 里没有 .ipa")
    ipa = os.path.join(outdir, ipas[0])
    with zipfile.ZipFile(ipa) as z:
        names = z.namelist()
        exe = [n for n in names if n.endswith("/MiniMaxStudio") and ".app/" in n]
        plist = "Payload/MiniMaxStudio.app/Info.plist"
        if not exe or plist not in names:
            sys.exit("ipa 结构异常: %s" % names[:10])
        magic = z.read(exe[0])[:4]
        if magic != b"\xcf\xfa\xed\xfe":
            sys.exit("可执行文件不是 arm64 Mach-O, magic=%s" % magic.hex())
        p = z.read(plist).decode("utf-8", "replace")
    ver = re.search(r"CFBundleShortVersionString</key>\s*<string>([^<]+)", p)
    minos = re.search(r"MinimumOSVersion</key>\s*<string>([^<]+)", p)
    print("IPA 校验通过: %s | 版本 %s | 最低 iOS %s | arm64 Mach-O OK"
          % (os.path.basename(ipa), ver.group(1) if ver else "?", minos.group(1) if minos else "?"))
    return ipa

def main():
    repo = sys.argv[1] if len(sys.argv) > 1 else "minimax-studio-ios"
    user = gh_user() or sys.exit("token 无效")
    print("账号:", user)
    st, _ = req("POST", API + "/user/repos", {"name": repo, "private": False, "auto_init": False})
    if st not in (201, 422):
        sys.exit("建仓库失败 %s: %s" % (st, _))
    since = push_repo(user, repo)
    run = wait_run(user, repo, since=since)
    zp = os.path.join(ROOT, "MiniMaxStudio-ipa.zip")
    fetch_artifact(user, repo, run["id"], zp)
    ipa = verify_ipa(zp)
    print("\n完成: %s" % ipa)
    print("传到 iPhone -> 文件App长按 -> 分享 -> TrollStore -> Install")

if __name__ == "__main__":
    main()
