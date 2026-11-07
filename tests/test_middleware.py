import django
from django.conf import settings

if not settings.configured:
    settings.configure(DEFAULT_CHARSET="utf-8", USE_TZ=True)
    django.setup()

from django.http import HttpResponse, StreamingHttpResponse  # noqa: E402

from netbox_isc_dhcp.middleware import inject_badge  # noqa: E402


def html(body='<html><body><div class="container-fluid tab-content py-3"><p>x</p></div></body></html>'):
    return HttpResponse(body, content_type="text/html; charset=utf-8")


def test_badge_inserted_before_body_end_and_length_updated():
    r = html()
    r["Content-Length"] = str(len(r.content))
    out = inject_badge(r)
    text = out.content.decode()
    assert text.index("tab-content") < text.index("isc-dhcp-version") < text.index("<p>x</p>")
    assert "text-end" in text
    assert "ISC DHCP v" in text
    assert out["Content-Length"] == str(len(out.content))


def test_badge_not_added_twice():
    out = inject_badge(inject_badge(html()))
    assert out.content.decode().count("isc-dhcp-version") == 1


def test_non_html_and_errors_untouched():
    assert b"isc-dhcp" not in inject_badge(HttpResponse("{}", content_type="application/json")).content
    assert b"isc-dhcp" not in inject_badge(HttpResponse("<body></body>", status=403, content_type="text/html")).content
    assert not hasattr(inject_badge(StreamingHttpResponse(["a"])), "content")


def test_unknown_layout_falls_back_to_body_end():
    out = inject_badge(html("<html><body><p>x</p></body></html>")).content.decode()
    assert out.index("isc-dhcp-version") < out.index("</body>")


def test_page_without_body_untouched():
    assert b"isc-dhcp" not in inject_badge(html("<p>fragment</p>")).content
