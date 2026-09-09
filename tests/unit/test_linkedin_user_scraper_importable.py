"""계정 수집기를 다른 파일이 불러다 쓸 수 있는지 본다.

종전에는 모듈 최상단에서 `parse_args()` 를 실행해, 이 파일을 import 하는 순간
부르는 쪽의 명령줄 인자를 읽고 죽었다. 그래서 벤치마킹 러너가 계정마다 별도
프로세스를 띄울 수밖에 없었다(계정 5개 = 브라우저 5회).
이 테스트가 실패하면 그 구조로 되돌아간 것이다.
계획: _docs/20260909_01 (W6-6)
"""

import inspect

import linkedin_scrap_by_user as by_user


def test_module_imports_without_command_line_arguments():
    # import 자체가 이 테스트다 - pytest 의 argv 에는 --user 가 없다.
    assert by_user.LinkedinUserScraper is not None


def test_scraper_takes_settings_as_constructor_arguments():
    signature = inspect.signature(by_user.LinkedinUserScraper.__init__)
    names = set(signature.parameters)

    for expected in ("user_id", "limit", "duration", "after", "needs_human_login"):
        assert expected in names, f"{expected} 가 생성자 인자가 아니다"


def test_instances_do_not_share_settings():
    """계정 둘을 한 프로세스에서 돌릴 수 있어야 한다.

    종전에는 값이 모듈 전역이라 두 번째 계정이 첫 번째의 설정을 그대로 썼다.
    """
    first = by_user.LinkedinUserScraper("first-slug", limit=3)
    second = by_user.LinkedinUserScraper("second-slug", limit=7)

    assert first.user_id == "first-slug"
    assert second.user_id == "second-slug"
    assert first.target_limit == 3
    assert second.target_limit == 7
    assert first.target_url != second.target_url
    assert first.user_data_dir != second.user_data_dir


def test_module_exposes_shared_browser_helpers():
    """브라우저를 밖에서 열어 넘길 수 있어야 계정들이 하나를 공유한다."""
    assert callable(by_user.launch_linkedin_browser)
    assert callable(by_user.new_linkedin_context)
    assert callable(by_user.LinkedinUserScraper.run_with_page)
