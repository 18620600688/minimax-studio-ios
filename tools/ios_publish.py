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

def push_repo(user, repo):
    import subprocess
    subprocess.run(["git", "init", "-b", "main"], cwd=ROOT, check=True, capture_output=True)
    subprocess.run(["git", "add", "-A"], cwd=ROOT, check=True, capture_output=True)
    subprocess.run(["git", "commit", "-m", "MiniMax iOS shell"], cwd=ROOT,
                   check=False, capture_output=True)   # 无改动会失败, 忽略
    url = "https://x-access-token:%s@github.com/%s/%s.git" % (TOK, user, repo)
    subprocess.run(["git", "-c", "credential.helper=", "remote", "remove", "origin"],
                   cwd=ROOT, capture_output=True)
    subprocess.run(["git", "-c", "credential.helper=", "remote", "add", "origin", url],
                   cwd=ROOT, check=True, capture_output=True)
    subprocess.run(["git", "-c", "credential.helper=", "push", "-u", "origin", "main"],
                   cwd=ROOT, check=True, capture_output=True)
    print("pushed ->", user + "/" + repo)

def wait_run(user, repo, timeout=900):
    print("等待 Actions 运行 ...")
    t0 = time.time()
    while time.time() - t0 < timeout:
        st, j = req("GET", "%s/repos/%s/%s/actions/runs?per_page=3" % (API, user, repo))
        for r in (j.get("workflow_runs") or []):
            if r["status"] == "completed":
                if r["conclusion"] == "success":
                    return r
                print("运行失败:", r["html_url"])
                sys.exit("云编译失败, 把日志贴回来修")
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

def main():
    repo = sys.argv[1] if len(sys.argv) > 1 else "minimax-studio-ios"
    user = gh_user() or sys.exit("token 无效")
    print("账号:", user)
    st, _ = req("POST", API + "/user/repos", {"name": repo, "private": False, "auto_init": False})
    if st not in (201, 422):
        sys.exit("建仓库失败 %s: %s" % (st, _))
    push_repo(user, repo)
    run = wait_run(user, repo)
    fetch_artifact(user, repo, run["id"], os.path.join(ROOT, "MiniMaxStudio-ipa.zip"))
    print("\n完成: 解压 zip 得 .ipa, 传到 iPhone -> 文件App长按 -> 分享 -> TrollStore -> Install")

if __name__ == "__main__":
    main()
