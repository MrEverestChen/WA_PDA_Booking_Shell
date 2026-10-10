#!/usr/bin/env python3

import argparse
import re
import ssl
import sys
import time
from datetime import datetime
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urljoin
from urllib.request import (
    HTTPRedirectHandler,
    HTTPSHandler,
    Request,
    build_opener,
)

import certifi


# ============================================================
# 基础配置
# ============================================================

BASE_ORIGIN = "https://online.transport.wa.gov.au"

WICKET_BASE = (
    "https://online.transport.wa.gov.au"
    "/pdabooking/manage/wicket/"
)

# 5 分钟
DEFAULT_INTERVAL = 300


# ============================================================
# 第一次手动填写 Wicket Listener 地址
#
# 例如浏览器抓包中的：
#
# POST /pdabooking/manage/wicket/page?1-1.0-...
#
# 把完整 path 填到这里。
# ============================================================

INITIAL_WICKET_PATH = (
    "/pdabooking/manage/wicket/"
    "page?1-5.0-layout-layout_body-requestForm-"
    "searchBookingContainer-search"
)


# ============================================================
# 把你当前有效的 Cookie 粘贴进去。
#
# 第一行 API 地址已经拆掉，使用 __WICKET_PATH__ 占位。
# ============================================================

RAW_REQUEST = r"""POST __WICKET_PATH__ HTTP/1.1
Host: online.transport.wa.gov.au
Connection: keep-alive
sec-ch-ua-platform: "macOS"
sec-ch-ua: "Not;A=Brand";v="8", "Chromium";v="150", "Google Chrome";v="150"
sec-ch-ua-mobile: ?0
Wicket-Ajax: true
Wicket-Ajax-BaseURL: wicket/page?1
X-Requested-With: XMLHttpRequest
User-Agent: Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/150.0.0.0 Safari/537.36
Accept: application/xml, text/xml, */*; q=0.01
Content-Type: application/x-www-form-urlencoded; charset=UTF-8
Wicket-FocusedElementId: id3
Origin: https://online.transport.wa.gov.au
Sec-Fetch-Site: same-origin
Sec-Fetch-Mode: cors
Sec-Fetch-Dest: empty
Referer: https://online.transport.wa.gov.au/pdabooking/manage/wicket/page?1
Accept-Language: en-US,en;q=0.9,zh-CN;q=0.8,zh;q=0.7
Cookie: _fbp=fb.3.1774147389472.496760408616262100; _hjSessionUser_2394170=eyJpZCI6IjUwNjdkZmQ1LWNmZTAtNWFlMi1iMTYwLWI5OTgwODk0YmE2NSIsImNyZWF0ZWQiOjE3NzQxNDczODg2MjgsImV4aXN0aW5nIjp0cnVlfQ==; __utmz=113595737.1782808810.1.1.utmccn=(direct)|utmcsr=(direct)|utmcmd=(none); _gcl_au=1.1.1670261476.1784721368; _ga=GA1.1.1835981135.1774147389; __utmc=113595737; cebs=1; _ce.clock_data=-26%2C112.213.228.0%2C1%2C4fc07ba599f9d84ac2c5f3d36be5aadf%2CChrome%2CAU%2CDirect%20Traffic%2C; cebsp_=2; _ce.seg.targeting=NoRgNA3gRA7FBc0B2BXAtgIwKYCcEAYwoBjFHHLJYgTwSgFUBlAESgF82xUAbbrlXv14BdIA; _ga_YKCLSZV8M0=GS2.1.s1789470716$o13$g1$t1789470968$j60$l0$h0; _ce.s=v~958b96d5fa2c5ad2336214a81641364208d008e8~vir~returning~lva~1789470717374~vpv~5~as~19.476942405749575~v11ls~43e8f520-b0f6-11f1-882d-9dcd0eafb1e6~v11.cs~410165~v11.s~43e8f520-b0f6-11f1-882d-9dcd0eafb1e6~v11.vs~958b96d5fa2c5ad2336214a81641364208d008e8~v11.sla~1789470967635~v11.wss~1789470717299~v11.fs~1~v11r~1%2Cuniform~v11nv~1~gtrk.la~mu2kt87g~lcw~1789470968994; SS_BEARER_TOKEN=eyJhbGciOiJSUzUxMiJ9.eyJkb3RjbiI6Ijg4Mzc3NzEiLCJzdWIiOiJtcmV2ZXJlc3RjaGVuIiwiYXVkIjoiRE9URElSRUNUX1dFQiIsIm5iZiI6MTc4OTQ3MDk4OSwiaXNzIjoidHJhbnNwb3J0LndhLmdvdi5hdSIsImV4cCI6MTc4OTQ3Mjc4OSwiaWF0IjoxNzg5NDcwOTg5LCJqdGkiOiJjNzBiYjJiZS05MWYzLTQ0ZGUtOGZhNC0yYjliODk5NjM5NjUifQ.dMkgTdOxcA_ApU4fmxqgmh6hC3vNq13E7hysO0JYFdCzFOmT4cTfb1xmXpFleRKjfgCTziZ6_Q-GO4EzoqjQeMAgCG2M5hSOzMhH1a8s0fRakmujUdnUGQqO7lD_zA9J0QYV1sI0Kwdi-0K5FeZ4oqJ-fCFU2o22GhC2ONj0YiM_bZ8nrQAW1mMTB_t439EKOjkTe8fY_UYKvh4mUdLmDki0G0-Xw_Bylstfl0DoKGhKyGzyRJFgMbsVqsZ3zjWoFtDvf60wXIQZNyqK7OwbhHgzwPmWjuYA-blvpoPe33E-RpcegtbdLTtZHwHFgZ7JkgrYJugYKIIscT-MF0D4fr_TiWXT2jRrDOD_kZnBT6s68cdCpCamiUrN27-ZEnNH51Nrn7t-Ot3loXouvsXAkdlR4NqdFDOvOewma7NXYFvgbs5sMUxUr8Wn7BvAJYtfd85w8VC2Qf1tMJvnUsASpxpNRbXlso-8VCXQoKmegFIqSZrztVo71GVZNfZxpOBohaOC6tyhLCUfrel88nKu_xNw5hx6Jqb4Mr7gQqhyw18QnJXncLF97sg7cGxnBl3AEIt7LRFCDve9Hci6X4pI8DOadSWftv2_W2j5WDAjTOeIMxk1OGG9SLb9ThytSQyJslJEz3ApHB2T7hvkiD1FyHB63rkb8rcG8LOw94Gp9Bc; JSESSIONID=gbKkyIlaK8UtMzbNXQ9D6nw89B8x02kqQdwVhGyWUQWJfBhSKOcB!-166630566!231691486; __utma=113595737.1905255001.1782808810.1789458718.1789471001.10; __utmb=113595737; AWSALBTG=eKGCHO6F4AsK+++a9n0myzJHfUufJXJmLuEWBYK+zvdi3EHF84DAMYh9RSk5YNP3BPhIoYSBBG5uuHXw9wpA8VLZgYtArEUOieR0VAjdQySxgeh5zu1d8KYHGSMOOvPOo0D0mMIIYwu3b3svNLOB1ow5QWGUq+AzYQ8UeHJqNNqyeH/yuVnSmRRH5Cr+bo3dJbN1ViYhikOBhIULclBkZnVKcNFCi4/DvCMLcSaPIpIyM5iA/u+c5aWUBeeCQ8k2nNans8eMqX7KfQ==; AWSALBTGCORS=eKGCHO6F4AsK+++a9n0myzJHfUufJXJmLuEWBYK+zvdi3EHF84DAMYh9RSk5YNP3BPhIoYSBBG5uuHXw9wpA8VLZgYtArEUOieR0VAjdQySxgeh5zu1d8KYHGSMOOvPOo0D0mMIIYwu3b3svNLOB1ow5QWGUq+AzYQ8UeHJqNNqyeH/yuVnSmRRH5Cr+bo3dJbN1ViYhikOBhIULclBkZnVKcNFCi4/DvCMLcSaPIpIyM5iA/u+c5aWUBeeCQ8k2nNans8eMqX7KfQ==; AWSALB=m4e0JLC0KNLB0mQsPuffjXig03dHfS9PJY4pEhLn0KXiQwhrg1+fT8ChY6s991HDTIndZOceNXuqqvQQEnvZwOxPGjtl28pyeERDBCI1ITLmplnTf50yW6wRM7GfmrowLrKERr8STvcDWDP/ZGbNNTMHRfkHoqo2zKBIc2uc8uz9lfCdFEXjVpDrIGbARA==; AWSALBCORS=m4e0JLC0KNLB0mQsPuffjXig03dHfS9PJY4pEhLn0KXiQwhrg1+fT8ChY6s991HDTIndZOceNXuqqvQQEnvZwOxPGjtl28pyeERDBCI1ITLmplnTf50yW6wRM7GfmrowLrKERr8STvcDWDP/ZGbNNTMHRfkHoqo2zKBIc2uc8uz9lfCdFEXjVpDrIGbARA==; TS012ba7f5=01becb1e5bd7d531c9946f92261b881bb75af5da418ab01c9e456a08f1ddb7c2be46e53a8913b45ac3d0435b950e26a1d92012156a16fb93966341605b8f53baeb62ac6d34eb6bad0b7ac80d8c33336dc343e3cb1b9996ad5a7edbf8c84c4f2cf4f09bc31e6eb13cf26a33567f4bcec702eaa9eed825a46a4d7c329551076ad9f59903e847befa85403576230e42ce3cc312b0abc3

searchBookingContainer%3AsiteRegion=REGIONAL&searchBookingContainer%3AfromDate=23%2F09%2F2026&searchBookingContainer%3AtoDate=30%2F09%2F2026&searchBookingContainer%3AsiteList=AUSO&searchBookingContainer%3AsiteList=BRIO&searchBookingContainer%3AsiteList=BNY&searchBookingContainer%3AsiteList=BSN&searchBookingContainer%3AsiteList=DNBO&searchBookingContainer%3AsiteList=ESPDP&searchBookingContainer%3AsiteList=HARO&searchBookingContainer%3AsiteList=NANO&searchBookingContainer%3AsiteList=WARO&searchBookingContainer%3Asearch=1"""


class NoRedirect(HTTPRedirectHandler):

    def redirect_request(
        self,
        req,
        fp,
        code,
        msg,
        headers,
        newurl,
    ):
        return None


def now():
    return datetime.now().strftime(
        "%Y-%m-%d %H:%M:%S"
    )


def build_ssl_context():

    return ssl.create_default_context(
        cafile=certifi.where()
    )


def parse_raw_request(raw):

    raw = raw.replace(
        "\r\n",
        "\n",
    )

    head, sep, body = raw.partition(
        "\n\n"
    )

    if not sep:
        raise ValueError(
            "请求头与正文之间缺少空行"
        )

    lines = head.splitlines()

    if not lines:
        raise ValueError(
            "请求为空"
        )

    method, target, _ = (
        lines[0].split(
            maxsplit=2
        )
    )

    headers = {}

    for line in lines[1:]:

        if not line.strip():
            continue

        if ":" not in line:
            raise ValueError(
                f"无法解析请求头：{line!r}"
            )

        key, value = line.split(
            ":",
            1,
        )

        key = key.lower().strip()
        value = value.strip()

        # urllib HTTP Header 必须可 latin-1 编码
        try:
            value.encode("latin-1")

        except UnicodeEncodeError:

            raise ValueError(
                f"请求头 {key!r} "
                f"包含不能发送的字符："
                f"{value!r}"
            )

        headers[key] = value

    body = body.rstrip(
        "\r\n"
    )

    return (
        method,
        target,
        headers,
        body,
    )


def extract_next_wicket_path(text):
    """
    从返回内容：

    Wicket.Ajax.ajax({
        "u":"./page?1-4.0-..."
    })

    中获取下一次搜索 URL。
    """

    pattern = (
        r'"u"\s*:\s*"'
        r'([^"]*'
        r'searchBookingContainer-search'
        r')"'
    )

    match = re.search(
        pattern,
        text,
        re.IGNORECASE,
    )

    if not match:
        return None

    relative_path = (
        match.group(1)
    )

    absolute_url = urljoin(
        WICKET_BASE,
        relative_path,
    )

    if not absolute_url.startswith(
        BASE_ORIGIN
    ):
        return None

    return absolute_url[
        len(BASE_ORIGIN):
    ]


def extract_redirect(text):
    """
    提取：

    <redirect>
        <![CDATA[./page?1]]>
    </redirect>
    """

    match = re.search(
        r"<redirect>\s*"
        r"<!\[CDATA\[(.*?)\]\]>"
        r"\s*</redirect>",
        text,
        re.IGNORECASE
        | re.DOTALL,
    )

    if not match:
        return None

    return (
        match
        .group(1)
        .strip()
    )


def send_search(
    opener,
    wicket_path,
    headers,
    body,
    timeout,
):
    """
    发送一次 PDA 搜索。
    """

    url = (
        BASE_ORIGIN
        + wicket_path
    )

    request = Request(
        url,
        data=body.encode(
            "utf-8"
        ),
        headers=headers,
        method="POST",
    )

    try:

        response = opener.open(
            request,
            timeout=timeout,
        )

    except HTTPError as exc:

        response = exc

    with response:

        status = response.code

        content_type = (
            response.headers.get(
                "Content-Type",
                "unknown",
            )
        )

        result = response.read()

    text = result.decode(
        "utf-8",
        errors="replace",
    )

    return (
        status,
        content_type,
        result,
        text,
    )


def try_resync(
    opener,
    redirect_path,
    headers,
    timeout,
):
    """
    如果 Wicket 返回：

        <redirect>./page?1</redirect>

    尝试 GET 该页面，
    从新的 HTML 中重新获得 Search Listener URL。
    """

    page_url = urljoin(
        WICKET_BASE,
        redirect_path,
    )

    print(
        f"[{now()}] 尝试重新同步 Wicket..."
    )

    print(
        f"[{now()}] GET {page_url}"
    )

    # GET 页面时去掉 AJAX POST 专用 Header
    get_headers = headers.copy()

    for key in (
        "content-type",
        "wicket-ajax",
        "x-requested-with",
        "wicket-focusedelementid",
    ):
        get_headers.pop(
            key,
            None,
        )

    get_headers["accept"] = (
        "text/html,"
        "application/xhtml+xml,"
        "application/xml;q=0.9,"
        "*/*;q=0.8"
    )

    request = Request(
        page_url,
        headers=get_headers,
        method="GET",
    )

    try:

        response = opener.open(
            request,
            timeout=timeout,
        )

    except HTTPError as exc:

        response = exc

    with response:

        status = response.code
        result = response.read()

    text = result.decode(
        "utf-8",
        errors="replace",
    )

    print(
        f"[{now()}] 同步页面 HTTP {status}"
    )

    if not (
        200 <= status < 300
    ):
        return None

    new_path = (
        extract_next_wicket_path(
            text
        )
    )

    if new_path:

        print(
            f"[{now()}] "
            "Wicket 已重新同步："
        )

        print(
            new_path
        )

    else:

        print(
            f"[{now()}] "
            "页面中没有找到新的 "
            "Search Listener URL。"
        )

    return new_path


def sleep_until_next(interval):
    """
    等待下一次查询。
    """

    next_time = (
        datetime.now().timestamp()
        + interval
    )

    next_text = (
        datetime
        .fromtimestamp(next_time)
        .strftime("%H:%M:%S")
    )

    print()
    print(
        f"[{now()}] "
        f"下一次查询：{next_text}"
    )

    print(
        "按 Ctrl+C 可停止。"
    )

    time.sleep(
        interval
    )


def main():

    parser = argparse.ArgumentParser(
        description=(
            "持续检查 WA Transport "
            "PDA Booking"
        )
    )

    parser.add_argument(
        "--timeout",
        type=float,
        default=30,
    )

    parser.add_argument(
        "--interval",
        type=int,
        default=DEFAULT_INTERVAL,
        help=(
            "查询间隔秒数，"
            "默认 300 秒"
        ),
    )

    parser.add_argument(
        "--output",
        type=Path,
        default=Path(
            "response.xml"
        ),
    )

    args = parser.parse_args()

    if args.interval < 60:

        print(
            "查询间隔至少设置为 60 秒。",
            file=sys.stderr,
        )

        return 2

    try:

        (
            method,
            target,
            headers,
            body,
        ) = parse_raw_request(
            RAW_REQUEST
        )

        if method.upper() != "POST":

            raise ValueError(
                "请求必须为 POST"
            )

        if target != "__WICKET_PATH__":

            raise ValueError(
                "RAW_REQUEST 第一行必须是：\n"
                "POST __WICKET_PATH__ HTTP/1.1"
            )

        # 交给 urllib 自己生成
        for key in (
            "host",
            "content-length",
            "connection",
            "accept-encoding",
        ):

            headers.pop(
                key,
                None,
            )

        headers[
            "accept-encoding"
        ] = "identity"

        ssl_context = (
            build_ssl_context()
        )

        opener = build_opener(
            NoRedirect(),
            HTTPSHandler(
                context=ssl_context
            ),
        )

        # ================================================
        # 第一次使用手动填写的地址
        # ================================================

        current_wicket_path = (
            INITIAL_WICKET_PATH
        )

        query_number = 0

        print("=" * 72)
        print(
            "WA Transport PDA Booking Monitor"
        )
        print("=" * 72)

        print(
            f"查询间隔："
            f"{args.interval} 秒"
        )

        print(
            "第一次 Wicket URL："
        )

        print(
            current_wicket_path
        )

        print(
            "\n程序会持续运行，"
            "Ctrl+C 停止。"
        )

        # ================================================
        # 持续运行
        # ================================================

        while True:

            query_number += 1

            print()
            print("=" * 72)

            print(
                f"[{now()}] "
                f"第 {query_number} 次查询"
            )

            print("=" * 72)

            print(
                "当前 Wicket URL："
            )

            print(
                current_wicket_path
            )

            try:

                (
                    status,
                    content_type,
                    result,
                    response_text,
                ) = send_search(
                    opener=opener,
                    wicket_path=(
                        current_wicket_path
                    ),
                    headers=headers,
                    body=body,
                    timeout=args.timeout,
                )

                # 保存最新响应
                args.output.parent.mkdir(
                    parents=True,
                    exist_ok=True,
                )

                args.output.write_bytes(
                    result
                )

                print()
                print(
                    f"HTTP {status}"
                )

                print(
                    f"Content-Type: "
                    f"{content_type}"
                )

                print(
                    f"响应大小："
                    f"{len(result)} bytes"
                )

                print(
                    f"最新响应："
                    f"{args.output.resolve()}"
                )

                response_lower = (
                    response_text.lower()
                )

                # ========================================
                # HTTP 登录/权限问题
                # ========================================

                if status in (
                    401,
                    403,
                ):

                    print()
                    print(
                        "⚠️ 登录认证可能已经过期。"
                    )

                    print(
                        "Cookie / Bearer Token "
                        "可能需要重新获取。"
                    )

                    sleep_until_next(
                        args.interval
                    )

                    continue

                # ========================================
                # Wicket AJAX Redirect
                # ========================================

                redirect_path = (
                    extract_redirect(
                        response_text
                    )
                )

                if redirect_path:

                    print()
                    print(
                        "⚠️ Wicket 返回 redirect："
                    )

                    print(
                        redirect_path
                    )

                    # 自动尝试重新 GET 页面同步
                    new_path = try_resync(
                        opener=opener,
                        redirect_path=(
                            redirect_path
                        ),
                        headers=headers,
                        timeout=args.timeout,
                    )

                    if new_path:

                        current_wicket_path = (
                            new_path
                        )

                        print(
                            f"[{now()}] "
                            "已恢复 Wicket 状态。"
                        )

                    else:

                        print(
                            f"[{now()}] "
                            "本轮无法自动恢复。"
                        )

                    sleep_until_next(
                        args.interval
                    )

                    continue

                # ========================================
                # 查询结果
                # ========================================

                if (
                    "there are no bookings available"
                    in response_lower
                ):

                    print()
                    print(
                        "❌ 当前没有可预约时段。"
                    )

                else:

                    print()
                    print(
                        "⚠️ 响应中没有出现 "
                        "\"no bookings available\"。"
                    )

                    print(
                        "请检查 response.xml，"
                        "可能出现了预约结果或其他页面状态。"
                    )

                # ========================================
                # 获取服务器返回的下一代 Wicket URL
                # ========================================

                next_wicket_path = (
                    extract_next_wicket_path(
                        response_text
                    )
                )

                if next_wicket_path:

                    print()
                    print(
                        "服务器返回下一次 "
                        "Wicket URL："
                    )

                    print(
                        next_wicket_path
                    )

                    # 核心：
                    # 新 URL 替换旧 URL
                    current_wicket_path = (
                        next_wicket_path
                    )

                    print()
                    print(
                        "✅ Wicket 状态已更新。"
                    )

                else:

                    print()
                    print(
                        "⚠️ 本次响应没有找到新的 "
                        "Wicket Listener URL。"
                    )

                    print(
                        "下一轮暂时继续使用"
                        "当前地址。"
                    )

            except (
                URLError,
                TimeoutError,
                OSError,
            ) as exc:

                print()
                print(
                    f"⚠️ 本轮网络请求失败："
                    f"{exc}"
                )

                print(
                    "程序不会退出，"
                    "下一轮继续尝试。"
                )

            # ============================================
            # 等待 5 分钟
            # ============================================

            sleep_until_next(
                args.interval
            )

    except KeyboardInterrupt:

        print()
        print()
        print(
            f"[{now()}] "
            "监控已手动停止。"
        )

        return 0

    except (
        ValueError,
        OSError,
    ) as exc:

        print(
            f"启动失败：{exc}",
            file=sys.stderr,
        )

        return 2


if __name__ == "__main__":

    sys.exit(
        main()
    )