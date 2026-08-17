from caption_cache import signed_caption_request


def test_signed_caption_request_is_stable():
    assert signed_caption_request("secret", "123", '{"videoId":"abcdefghijk"}') == (
        "93e8b283e736d29f31cd00048f8139e666d6bfd38096231f2646f0b81f337929"
    )
