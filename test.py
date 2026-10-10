#!/usr/bin/env python3

import re
import ssl
import sys
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from html import unescape
from http.cookies import SimpleCookie
from urllib.error import HTTPError
from urllib.parse import urlencode, urljoin, urlparse
from urllib.request import HTTPRedirectHandler, HTTPSHandler, Request, build_opener

import truststore


HOST = "online.transport.wa.gov.au"
BASE = f"https://{HOST}"
LOGIN_URL = f"{BASE}/tso/selfservice/public/login.jsf"

USERNAME = "YourUserName"
PASSWORD = "YourPassword"

TIMEOUT = 30


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


class TransportSession:
    def __init__(self):
        self.cookies = {}
        self.cookie_seq = 0

        context = truststore.SSLContext(ssl.PROTOCOL_TLS_CLIENT)

        self.opener = build_opener(
            NoRedirect(),
            HTTPSHandler(context=context),
        )

    @staticmethod
    def _default_path(url):
        path = urlparse(url).path or "/"

        if path == "/":
            return "/"

        pos = path.rfind("/")
        return "/" if pos <= 0 else path[:pos]

    @staticmethod
    def _expired(cookie):
        expires = cookie.get("expires")

        if not expires:
            return False

        try:
            dt = parsedate_to_datetime(expires)

            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)

            return dt <= datetime.now(timezone.utc)

        except Exception:
            return False

    def _save_cookie(self, cookie, source):
        key = (
            cookie["name"],
            cookie["domain"],
            cookie["path"],
        )

        old = self.cookies.get(key)

        if old:
            cookie["seq"] = old["seq"]
        else:
            self.cookie_seq += 1
            cookie["seq"] = self.cookie_seq

        self.cookies[key] = cookie

        if old is None:
            print(
                f"Cookie + {cookie['name']} "
                f"Path={cookie['path']}"
            )

        elif old["value"] != cookie["value"]:
            print(
                f"Cookie ↻ {cookie['name']} "
                f"Path={cookie['path']}"
            )

    def _read_set_cookies(self, headers, response_url):
        host = urlparse(response_url).hostname.lower()

        for raw in headers.get_all("Set-Cookie") or []:
            parsed = SimpleCookie()

            try:
                parsed.load(raw)
            except Exception:
                continue

            for name, item in parsed.items():
                domain = (
                    item["domain"].lstrip(".").lower()
                    if item["domain"]
                    else host
                )

                path = (
                    item["path"]
                    or self._default_path(response_url)
                )

                cookie = {
                    "name": name,
                    "value": item.value,
                    "domain": domain,
                    "path": path,
                    "host_only": not bool(item["domain"]),
                    "secure": bool(item["secure"]),
                    "expires": item["expires"] or None,
                }

                key = (name, domain, path)

                delete = False

                if item["max-age"]:
                    try:
                        delete = int(item["max-age"]) <= 0
                    except ValueError:
                        pass

                if self._expired(cookie):
                    delete = True

                if delete:
                    self.cookies.pop(key, None)
                    continue

                self._save_cookie(cookie, response_url)

    def _matching_cookies(self, url):
        parsed = urlparse(url)

        host = parsed.hostname.lower()
        path = parsed.path or "/"
        scheme = parsed.scheme

        result = []

        for key, cookie in list(self.cookies.items()):
            if self._expired(cookie):
                self.cookies.pop(key, None)
                continue

            domain = cookie["domain"]

            if cookie["host_only"]:
                if host != domain:
                    continue
            elif host != domain and not host.endswith("." + domain):
                continue

            cookie_path = cookie["path"]

            if not path.startswith(cookie_path):
                continue

            if cookie["secure"] and scheme != "https":
                continue

            result.append(cookie)

        # /tso 的 JSESSIONID 会排在 / 的 JSESSIONID 前面
        result.sort(
            key=lambda c: (
                -len(c["path"]),
                c["seq"],
            )
        )

        return result

    def _cookie_header(self, url):
        return "; ".join(
            f"{c['name']}={c['value']}"
            for c in self._matching_cookies(url)
        )

    @staticmethod
    def _response_text(headers, body):
        try:
            charset = headers.get_content_charset() or "utf-8"
        except Exception:
            charset = "utf-8"

        return body.decode(charset, errors="replace")

    @staticmethod
    def _jsf_redirect(text):
        match = re.search(
            r'<redirect\s+url=["\']([^"\']+)["\']',
            text,
            re.I,
        )

        if match:
            return unescape(match.group(1))

        match = re.search(
            r"<redirect[^>]*>(?:<!\[CDATA\[)?(.*?)(?:\]\]>)?</redirect>",
            text,
            re.I | re.S,
        )

        return unescape(match.group(1).strip()) if match else None

    @staticmethod
    def _get_headers(headers, referer):
        cleaned = {
            k: v
            for k, v in headers.items()
            if k.lower()
            not in {
                "faces-request",
                "x-requested-with",
                "content-type",
                "content-length",
                "origin",
            }
        }

        cleaned.update({
            "Accept": (
                "text/html,application/xhtml+xml,"
                "application/xml;q=0.9,*/*;q=0.8"
            ),
            "Referer": referer,
            "Sec-Fetch-Site": "same-origin",
            "Sec-Fetch-Mode": "navigate",
            "Sec-Fetch-Dest": "document",
        })

        return cleaned

    def _send(self, method, url, headers=None, body=None):
        if urlparse(url).hostname != HOST:
            raise RuntimeError(f"拒绝访问外部域名：{url}")

        req_headers = {
            "User-Agent": (
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/150.0.0.0 Safari/537.36"
            ),
            "Accept-Language": "en-US,en;q=0.9,zh-CN;q=0.8,zh;q=0.7",
            "Accept-Encoding": "identity",
        }

        if headers:
            req_headers.update(headers)

        cookie = self._cookie_header(url)

        if cookie:
            req_headers["Cookie"] = cookie

        print(f"\n{method} {url}")

        if cookie:
            jsessions = [
                c for c in self._matching_cookies(url)
                if c["name"] == "JSESSIONID"
            ]

            print(f"发送 JSESSIONID：{len(jsessions)} 个")

            for c in jsessions:
                print(f"  Path={c['path']}")

        req = Request(
            url,
            data=body,
            headers=req_headers,
            method=method,
        )

        try:
            response = self.opener.open(req, timeout=TIMEOUT)
        except HTTPError as exc:
            response = exc

        status = response.code
        final_url = response.geturl()
        response_headers = response.headers
        response_body = response.read()
        response.close()

        self._read_set_cookies(
            response_headers,
            final_url,
        )

        text = self._response_text(
            response_headers,
            response_body,
        )

        print(f"HTTP {status}")

        location = response_headers.get("Location")

        if location:
            print(f"Location: {location}")

        print("Response:")
        print(text)

        return {
            "status": status,
            "url": final_url,
            "headers": response_headers,
            "body": response_body,
            "text": text,
        }

    def request(self, method, url, headers=None, body=None):
        method = method.upper()
        headers = dict(headers or {})

        for _ in range(10):
            result = self._send(
                method,
                url,
                headers,
                body,
            )

            # HTTP 301 / 302 / 303 / 307 / 308
            if result["status"] in (301, 302, 303, 307, 308):
                location = result["headers"].get("Location")

                if not location:
                    return result

                next_url = urljoin(url, location)

                print(f"HTTP {result['status']} → {next_url}")

                old_url = url

                if (
                    result["status"] == 303
                    or (
                        result["status"] in (301, 302)
                        and method == "POST"
                    )
                ):
                    method = "GET"
                    body = None
                    headers = self._get_headers(
                        headers,
                        old_url,
                    )

                url = next_url
                continue

            # JSF:
            # <partial-response>
            #   <redirect url="../overview.jsf"/>
            # </partial-response>
            jsf_target = self._jsf_redirect(
                result["text"]
            )

            if jsf_target:
                old_url = url
                url = urljoin(url, jsf_target)

                print(f"JSF redirect → {url}")

                method = "GET"
                body = None

                headers = self._get_headers(
                    headers,
                    old_url,
                )

                continue

            return result

        raise RuntimeError("跳转次数超过限制")

    def get_login_page(self):
        result = self.request(
            "GET",
            LOGIN_URL,
            headers={
                "Accept": (
                    "text/html,application/xhtml+xml,"
                    "application/xml;q=0.9,*/*;q=0.8"
                ),
                "Sec-Fetch-Site": "none",
                "Sec-Fetch-Mode": "navigate",
                "Sec-Fetch-Dest": "document",
            },
        )

        patterns = [
            (
                r'name=["\']javax\.faces\.ViewState["\']'
                r'[^>]*value=["\']([^"\']+)'
            ),
            (
                r'value=["\']([^"\']+)["\']'
                r'[^>]*name=["\']javax\.faces\.ViewState["\']'
            ),
        ]

        for pattern in patterns:
            match = re.search(
                pattern,
                result["text"],
                re.I,
            )

            if match:
                return unescape(
                    match.group(1)
                )

        return "stateless"

    def login(self, username, password, view_state):
        form = {
            "javax.faces.partial.ajax": "true",
            "javax.faces.source": "loginForm:loginButton",
            "javax.faces.partial.execute": "@all",
            "javax.faces.partial.render": "loginForm:messages",
            "loginForm:loginButton": "loginForm:loginButton",
            "loginForm": "loginForm",
            "loginForm:userId": username,
            "loginForm:password": password,
            "javax.faces.ViewState": view_state,
        }

        headers = {
            "Faces-Request": "partial/ajax",
            "X-Requested-With": "XMLHttpRequest",
            "Accept": "application/xml,text/xml,*/*; q=0.01",
            "Content-Type": (
                "application/x-www-form-urlencoded; charset=UTF-8"
            ),
            "Origin": BASE,
            "Referer": LOGIN_URL,
            "Sec-Fetch-Site": "same-origin",
            "Sec-Fetch-Mode": "cors",
            "Sec-Fetch-Dest": "empty",
        }

        return self.request(
            "POST",
            LOGIN_URL,
            headers,
            urlencode(form).encode("utf-8"),
        )

    def show_sessions(self):
        sessions = [
            c
            for c in self.cookies.values()
            if c["name"] == "JSESSIONID"
        ]

        sessions.sort(
            key=lambda c: -len(c["path"])
        )

        print(
            f"\n当前 JSESSIONID："
            f"{len(sessions)} 个"
        )

        for i, cookie in enumerate(
            sessions,
            1,
        ):
            print(
                f"{i}. Path={cookie['path']} "
                f"Value={cookie['value']}"
            )


def main():
    if (
        USERNAME == "YOUR_USERNAME"
        or PASSWORD == "YOUR_PASSWORD"
    ):
        print("请先填写 USERNAME 和 PASSWORD")
        return 1

    session = TransportSession()

    try:
        view_state = session.get_login_page()

        print(
            f"\nViewState: {view_state}"
        )

        result = session.login(
            USERNAME,
            PASSWORD,
            view_state,
        )

        session.show_sessions()

        print(
            "\n最终状态：",
            result["status"],
        )

        print(
            "最终 URL：",
            result["url"],
        )

    except KeyboardInterrupt:
        print("\n已停止")

    except Exception as exc:
        print(
            f"\n错误：{exc}",
            file=sys.stderr,
        )

        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())