import unittest
from utils.common import clean_text

class TestCommonUtils(unittest.TestCase):
    def test_clean_text_threads(self):
        # Threads 특화 로직 테스트: username 제거 및 메타데이터 필터링
        raw = "gb_jeong\n2시간\nAI Threads\n본문 내용입니다.\n답글"
        cleaned = clean_text(raw, platform='threads', username='gb_jeong')
        self.assertEqual(cleaned, "본문 내용입니다.")

    def test_clean_text_twitter(self):
        # Twitter 특화 로직 테스트: 줄바꿈을 공백으로 대체
        raw = "첫 번째 줄\n두 번째 줄\n\n\n세 번째 줄"
        cleaned = clean_text(raw, platform='twitter')
        # \n{3,} -> \n\n 처리 후 \n -> ' ' 처리 및 연속 공백 제거
        self.assertEqual(cleaned, "첫 번째 줄 두 번째 줄 세 번째 줄")

    def test_clean_text_linkedin(self):
        # LinkedIn 특화 로직 테스트: …더보기 제거 및 공백 정규화
        raw = "링크드인 본문입니다.…더보기\n  공백이 있는 줄  "
        cleaned = clean_text(raw, platform='linkedin')
        self.assertEqual(cleaned, "링크드인 본문입니다.\n공백이 있는 줄")

    def test_clean_text_default(self):
        # 기본 클리닝 테스트
        raw = "  일반 텍스트  \n\n2024-03-10\n끝"
        cleaned = clean_text(raw)
        self.assertEqual(cleaned, "일반 텍스트\n끝")

if __name__ == '__main__':
    unittest.main()
