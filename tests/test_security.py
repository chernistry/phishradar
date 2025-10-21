import pytest

from app.security import assert_safe_url


def test_assert_safe_url_allows_public_https():
    assert_safe_url("https://example.com/path")  # should not raise


@pytest.mark.parametrize(
    "url",
    [
        "file:///etc/passwd",
        "http://127.0.0.1/x",
        "http://localhost/x",
        "http://10.0.0.1/x",
        "http://172.16.0.5/x",
        "http://192.168.1.10/x",
        "http://169.254.0.10/x",
        "http://[::1]/x",
    ],
)
def test_assert_safe_url_blocks_private_and_file(url):
    with pytest.raises(ValueError):
        assert_safe_url(url)

